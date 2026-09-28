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
from collections import Counter, deque
from urllib.parse import urlsplit

# Deliberately smaller than the UI's live list: this buffer is for answering
# questions about recent traffic, not for being a second copy of the session.
DEFAULT_HISTORY_LIMIT = 1000

# Per-body cap. Anything longer is truncated with a marker so the consumer can
# tell "the body was big" apart from "the body ended there".
MAX_STORED_BODY = 32 * 1024

_TRUNCATED = "\n// [truncated by OpenProxy flow store]"

# WebSocket frames kept per flow, and the per-frame text cap. Chatty realtime
# connections can push thousands of frames; an agent asking "what did the app
# send over the socket" wants the recent ones, not all of them.
MAX_WS_MESSAGES_PER_FLOW = 200
MAX_WS_MESSAGE_TEXT = 8 * 1024

# Batch-fetch ceiling. Each flow can carry two 32KB bodies, so this bounds a
# single reply at a few MB.
MAX_BATCH_GET = 20

# Characters of context returned either side of a search hit.
SEARCH_SNIPPET_RADIUS = 60


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
    """Keep text bodies (capped); replace binary/image payloads with a marker.

    Returns (stored_text, complete). `complete` is False whenever the stored
    text is not the bytes that went over the wire — truncated, or replaced by
    an omission marker — so consumers that *resend* a body (replay) can refuse
    rather than ship a corrupted payload.
    """
    if is_image:
        return "// [image body omitted]", False
    if is_binary:
        return "// [binary body omitted]", False
    if not text:
        return "", True
    if len(text) > MAX_STORED_BODY:
        return text[:MAX_STORED_BODY] + _TRUNCATED, False
    return text, True


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
                       body, is_image=False, is_binary=False, req_bytes=0,
                       replay_id=None):
        self._seq += 1
        req_body, req_complete = _clip_body(body, is_image, is_binary)
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
            "req_body": req_body,
            # False when req_body is not the exact bytes sent (truncated or
            # omitted). Replay checks this before resending a body.
            "req_body_complete": req_complete,
            "res_headers": {},
            "res_body": "",
            "res_body_complete": True,
            "mocked": False,
            "error": None,
            # Set when this request was injected by send/replay: lets the
            # caller find *its* flow even if the app hit the same URL at the
            # same moment.
            "replay_id": replay_id,
            "ws_messages": [],
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
        entry["res_body"], entry["res_body_complete"] = _clip_body(body, is_image, is_binary)
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

    def record_ws_message(self, flow_id, from_client, content, size):
        """Append one WebSocket frame to the flow that opened the socket.

        The upgrade handshake is an ordinary HTTP request, so the flow already
        has an entry by the time frames start flowing.
        """
        entry = self._by_id.get(flow_id)
        if entry is None:
            return None
        text = content if isinstance(content, str) else str(content)
        if len(text) > MAX_WS_MESSAGE_TEXT:
            text = text[:MAX_WS_MESSAGE_TEXT] + _TRUNCATED
        msgs = entry["ws_messages"]
        msgs.append({
            "index": len(msgs) + entry.get("ws_dropped", 0),
            "from_client": bool(from_client),
            "content": text,
            "size": size,
            "at": time.time(),
        })
        if len(msgs) > MAX_WS_MESSAGES_PER_FLOW:
            overflow = len(msgs) - MAX_WS_MESSAGES_PER_FLOW
            del msgs[:overflow]
            entry["ws_dropped"] = entry.get("ws_dropped", 0) + overflow
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
            "replay_id": entry["replay_id"],
            "ws_messages": len(entry["ws_messages"]) + entry.get("ws_dropped", 0),
        }

    def detail(self, entry):
        """The full shape returned by get queries: everything but the frame log,
        which has its own accessor (it can be large and is rarely wanted)."""
        out = {k: v for k, v in entry.items() if k not in ("ws_messages", "ws_dropped")}
        out["ws_messages"] = len(entry["ws_messages"]) + entry.get("ws_dropped", 0)
        return out

    def get_many(self, flow_ids):
        """Batch lookup. Returns (found details in request order, missing ids)."""
        found, missing = [], []
        for fid in list(flow_ids)[:MAX_BATCH_GET]:
            entry = self._by_id.get(fid)
            if entry is None:
                missing.append(fid)
            else:
                found.append(self.detail(entry))
        return found, missing

    def ws_messages(self, flow_id, offset=0, limit=100):
        entry = self._by_id.get(flow_id)
        if entry is None:
            return None
        msgs = entry["ws_messages"]
        dropped = entry.get("ws_dropped", 0)
        total = len(msgs) + dropped
        # `offset` is in absolute frame indices so a caller can page from where
        # it left off even after old frames were dropped.
        start = max(0, offset - dropped)
        page = msgs[start:start + max(1, limit)]
        return {
            "flow_id": flow_id,
            "url": entry["url"],
            "total": total,
            "dropped": dropped,
            "messages": page,
            "next_offset": (page[-1]["index"] + 1) if page else total,
        }

    def list(self, url_pattern=None, method=None, status=None,
             since_seq=None, only_completed=False, limit=50, replay_id=None):
        out = []
        # Newest first: an agent asking for "the last 20 requests" wants the
        # most recent ones, not the oldest still in the buffer.
        for entry in reversed(self._flows):
            if since_seq is not None and entry["seq"] <= since_seq:
                # seq is ascending, so everything further back is older too.
                break
            if not self._matches(entry, url_pattern, method, status, only_completed, replay_id):
                continue
            out.append(self.summary(entry))
            if len(out) >= limit:
                break
        out.reverse()
        return out

    def search(self, text, since_seq=None, url_pattern=None, limit=50):
        """Case-insensitive substring search across everything stored per flow.

        Answers "did the app send this token anywhere" in one call. Each hit
        names where the text was found and a snippet around it, so the agent
        can decide which flows deserve a full get without fetching them all.
        """
        needle = (text or "").lower()
        if not needle:
            return []
        out = []
        for entry in reversed(self._flows):
            if since_seq is not None and entry["seq"] <= since_seq:
                break
            if url_pattern and not _match(url_pattern, entry["url"]):
                continue
            hits = []
            for where, hay in self._searchable(entry):
                pos = hay.lower().find(needle)
                if pos < 0:
                    continue
                lo = max(0, pos - SEARCH_SNIPPET_RADIUS)
                hi = min(len(hay), pos + len(needle) + SEARCH_SNIPPET_RADIUS)
                hits.append({"in": where, "snippet": hay[lo:hi]})
            if hits:
                item = self.summary(entry)
                item["hits"] = hits
                out.append(item)
                if len(out) >= limit:
                    break
        out.reverse()
        return out

    @staticmethod
    def _searchable(entry):
        yield "url", entry["url"]
        for k, v in entry["req_headers"].items():
            yield f"req_headers.{k}", str(v)
        yield "req_body", entry["req_body"]
        for k, v in entry["res_headers"].items():
            yield f"res_headers.{k}", str(v)
        yield "res_body", entry["res_body"]
        for m in entry["ws_messages"]:
            yield f"ws_messages[{m['index']}]", m["content"]

    def summarize(self, since_seq=None, url_pattern=None, top=15):
        """Aggregate view of a window of traffic, grouped by host and status.

        This is what an agent actually wants after a scenario — "which hosts
        did the app talk to, how many failed, anything leak to a third party"
        — and it costs a fraction of the tokens of paging through summaries.
        """
        total = completed = mocked = errors = pending = 0
        by_host = {}
        by_status = Counter()
        by_method = Counter()
        endpoints = Counter()
        durations = []
        first_seq = last_seq = None
        for entry in self._flows:
            if since_seq is not None and entry["seq"] <= since_seq:
                continue
            if url_pattern and not _match(url_pattern, entry["url"]):
                continue
            total += 1
            first_seq = entry["seq"] if first_seq is None else first_seq
            last_seq = entry["seq"]
            parts = urlsplit(entry["url"])
            host = parts.netloc or "?"
            h = by_host.setdefault(host, {
                "count": 0, "statuses": Counter(), "mocked": 0, "errors": 0,
                "req_bytes": 0, "res_bytes": 0,
            })
            h["count"] += 1
            h["req_bytes"] += entry["req_bytes"] or 0
            h["res_bytes"] += entry["res_bytes"] or 0
            by_method[entry["method"]] += 1
            endpoints[f"{entry['method']} {host}{parts.path}"] += 1
            if entry["error"]:
                errors += 1
                h["errors"] += 1
                by_status["error"] += 1
            elif entry["status"] is None:
                pending += 1
                by_status["pending"] += 1
            else:
                completed += 1
                by_status[str(entry["status"])] += 1
                h["statuses"][str(entry["status"])] += 1
                if entry["duration_ms"] is not None:
                    durations.append(entry["duration_ms"])
            if entry["mocked"]:
                mocked += 1
                h["mocked"] += 1
        for h in by_host.values():
            h["statuses"] = dict(h["statuses"])
        durations.sort()
        return {
            "total": total,
            "completed": completed,
            "pending": pending,
            "errors": errors,
            "mocked": mocked,
            "seq_range": [first_seq, last_seq],
            "by_status": dict(by_status),
            "by_method": dict(by_method),
            "by_host": dict(sorted(by_host.items(), key=lambda kv: -kv[1]["count"])),
            "top_endpoints": [
                {"endpoint": ep, "count": n} for ep, n in endpoints.most_common(top)
            ],
            "duration_ms": {
                "p50": durations[len(durations) // 2] if durations else None,
                "max": durations[-1] if durations else None,
            },
        }

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

    def _matches(self, entry, url_pattern, method, status, only_completed, replay_id=None):
        if only_completed and entry["status"] is None and entry["error"] is None:
            return False
        if replay_id is not None and entry["replay_id"] != replay_id:
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
                       since_seq=None, count=1, timeout=30.0, replay_id=None):
        """Block until `count` matching flows complete, or `timeout` elapses.

        Returns whatever matched, even on timeout — a partial result ("the app
        sent one retry, not the three you expected") is a finding, not a
        failure, so this never raises.
        """
        existing = self.list(
            url_pattern=url_pattern, method=method, status=status,
            since_seq=since_seq, only_completed=True, limit=count, replay_id=replay_id,
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
            "replay_id": replay_id,
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
                since_seq=since_seq, only_completed=True, limit=count, replay_id=replay_id,
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
                replay_id=waiter["replay_id"],
            )
            if len(matched) >= waiter["count"]:
                waiter["future"].set_result(matched)
                self._waiters.remove(waiter)
