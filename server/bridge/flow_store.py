"""Bounded in-memory history of completed flows.

The UI keeps its own flow list in the Vue store, so nothing on the Python side
ever needed to remember traffic — hooks broadcast and forget. Automation clients
(the MCP server) can't work that way: they connect *after* the interesting
traffic happened, and they need to ask "what did the app send after I mocked
that endpoint?" long after the broadcast went out.

Two design notes worth knowing before changing this:

* Entries carry a monotonic `seq`. Agents mark a watermark before triggering an
  action, then ask for flows after it — far more reliable than wall-clock
  timestamps for "what happened as a result of what I just did".
* Bodies are capped hard (and binary/image bodies dropped entirely). A 2000-flow
  buffer holding 1MB bodies would be multi-gigabyte, and an agent has no use for
  a base64 PNG anyway — it only costs it context.
"""

import re
import time
import asyncio
from collections import deque

# Deliberately smaller than the UI's live list: this buffer is for answering
# questions about recent traffic, not for being a second copy of the session.
DEFAULT_HISTORY_LIMIT = 1000

# Per-body cap. Anything longer is truncated with a marker so the consumer can
# tell "the body was big" apart from "the body ended there".
MAX_STORED_BODY = 32 * 1024

_TRUNCATED = "\n// [truncated by OpenProxy flow store]"


def _match(pattern: str, value: str) -> bool:
    """Glob when the pattern has a `*`, case-insensitive substring otherwise.

    Substring is the forgiving default because agents tend to pass a bare path
    ("/api/login") rather than a fully-anchored URL pattern.
    """
    if not pattern:
        return True
    if "*" in pattern:
        regex = "^" + ".*".join(re.escape(p) for p in pattern.split("*")) + "$"
        return re.search(regex, value, re.IGNORECASE) is not None
    return pattern.lower() in value.lower()


def _clip_body(text, is_image, is_binary):
    """Keep text bodies (capped); replace binary/image payloads with a marker."""
    if is_image:
        return "// [image body omitted]"
    if is_binary:
        return "// [binary body omitted]"
    if not text:
        return ""
    if len(text) > MAX_STORED_BODY:
        return text[:MAX_STORED_BODY] + _TRUNCATED
    return text


class FlowStore:
    """Ring buffer of flows, keyed by mitmproxy flow id, ordered by `seq`."""

    def __init__(self, maxlen=DEFAULT_HISTORY_LIMIT):
        self._flows = deque(maxlen=maxlen)
        self._by_id = {}
        self._seq = 0
        self._waiters = []

    # ---- recording -------------------------------------------------------

    def watermark(self) -> int:
        """Current sequence number. Flows recorded later have a higher `seq`."""
        return self._seq

    def record_request(self, flow_id, method, url, client_ip, headers,
                       body, is_image=False, is_binary=False, req_bytes=0):
        self._seq += 1
        entry = {
            "seq": self._seq,
            "id": flow_id,
            "method": method,
            "url": url,
            "client_ip": client_ip,
            "status": None,
            "started_at": time.time(),
            "duration_ms": None,
            "req_bytes": req_bytes,
            "res_bytes": 0,
            "req_headers": dict(headers),
            "req_body": _clip_body(body, is_image, is_binary),
            "res_headers": {},
            "res_body": "",
            "mocked": False,
            "error": None,
        }

        # deque drops the oldest item silently once full — pull the id out
        # first so _by_id doesn't leak entries the buffer no longer holds.
        if len(self._flows) == self._flows.maxlen and self._flows:
            self._by_id.pop(self._flows[0]["id"], None)

        self._flows.append(entry)
        self._by_id[flow_id] = entry
        return entry

    def record_response(self, flow_id, status, headers, body,
                        is_image=False, is_binary=False, res_bytes=0,
                        duration_ms=None, mocked=False):
        entry = self._by_id.get(flow_id)
        if entry is None:
            # Response with no recorded request: the request arrived while
            # recording was paused, or before this store existed.
            return None
        entry["status"] = status
        entry["res_headers"] = dict(headers)
        entry["res_body"] = _clip_body(body, is_image, is_binary)
        entry["res_bytes"] = res_bytes
        entry["duration_ms"] = duration_ms
        entry["mocked"] = mocked
        self._resolve_waiters()
        return entry

    def record_error(self, flow_id, message):
        entry = self._by_id.get(flow_id)
        if entry is None:
            return None
        entry["error"] = message
        self._resolve_waiters()
        return entry

    # ---- reading ---------------------------------------------------------

    def summary(self, entry):
        """The compact shape returned by list queries — no bodies, no headers.

        Agents page through summaries and then fetch the one flow they care
        about; sending every body inline would blow up their context for nothing.
        """
        return {
            "seq": entry["seq"],
            "id": entry["id"],
            "method": entry["method"],
            "url": entry["url"],
            "status": entry["status"],
            "duration_ms": entry["duration_ms"],
            "req_bytes": entry["req_bytes"],
            "res_bytes": entry["res_bytes"],
            "client_ip": entry["client_ip"],
            "mocked": entry["mocked"],
            "error": entry["error"],
            "started_at": entry["started_at"],
        }

    def list(self, url_pattern=None, method=None, status=None,
             since_seq=None, only_completed=False, limit=50):
        out = []
        # Newest first: an agent asking for "the last 20 requests" wants the
        # most recent ones, not the oldest still in the buffer.
        for entry in reversed(self._flows):
            if since_seq is not None and entry["seq"] <= since_seq:
                # seq is ascending, so everything further back is older too.
                break
            if not self._matches(entry, url_pattern, method, status, only_completed):
                continue
            out.append(self.summary(entry))
            if len(out) >= limit:
                break
        out.reverse()
        return out

    def get(self, flow_id):
        return self._by_id.get(flow_id)

    def clear(self):
        """Drop history. `seq` deliberately keeps counting so watermarks held
        by an in-flight agent call never silently start matching old flows."""
        self._flows.clear()
        self._by_id.clear()

    def stats(self):
        return {
            "count": len(self._flows),
            "capacity": self._flows.maxlen,
            "watermark": self._seq,
        }

    def _matches(self, entry, url_pattern, method, status, only_completed):
        if only_completed and entry["status"] is None and entry["error"] is None:
            return False
        if method and entry["method"].upper() != method.upper():
            return False
        if status is not None and entry["status"] != status:
            return False
        if url_pattern and not _match(url_pattern, entry["url"]):
            return False
        return True

    # ---- waiting ---------------------------------------------------------

    async def wait_for(self, url_pattern=None, method=None, status=None,
                       since_seq=None, count=1, timeout=30.0):
        """Block until `count` matching flows complete, or `timeout` elapses.

        Returns whatever matched, even on timeout — a partial result ("the app
        sent one retry, not the three you expected") is a finding, not a
        failure, so this never raises.
        """
        existing = self.list(
            url_pattern=url_pattern, method=method, status=status,
            since_seq=since_seq, only_completed=True, limit=count,
        )
        if len(existing) >= count:
            return {"matched": existing, "timed_out": False}

        loop = asyncio.get_running_loop()
        waiter = {
            "future": loop.create_future(),
            "url_pattern": url_pattern,
            "method": method,
            "status": status,
            "since_seq": since_seq,
            "count": count,
        }
        self._waiters.append(waiter)
        try:
            matched = await asyncio.wait_for(waiter["future"], timeout=timeout)
            return {"matched": matched, "timed_out": False}
        except asyncio.TimeoutError:
            # Re-query rather than returning empty: flows may have landed that
            # didn't reach the requested count.
            partial = self.list(
                url_pattern=url_pattern, method=method, status=status,
                since_seq=since_seq, only_completed=True, limit=count,
            )
            return {"matched": partial, "timed_out": True}
        finally:
            if waiter in self._waiters:
                self._waiters.remove(waiter)

    def _resolve_waiters(self):
        if not self._waiters:
            return
        for waiter in list(self._waiters):
            if waiter["future"].done():
                self._waiters.remove(waiter)
                continue
            matched = self.list(
                url_pattern=waiter["url_pattern"],
                method=waiter["method"],
                status=waiter["status"],
                since_seq=waiter["since_seq"],
                only_completed=True,
                limit=waiter["count"],
            )
            if len(matched) >= waiter["count"]:
                waiter["future"].set_result(matched)
                self._waiters.remove(waiter)
