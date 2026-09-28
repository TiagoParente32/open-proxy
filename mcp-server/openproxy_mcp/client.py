"""WebSocket client for OpenProxy's automation surface.

OpenProxy's backend listens on 127.0.0.1:8765 and speaks two protocols on the
same socket: a fire-and-forget one for the Vue UI, and a request/response one
for automation (every message carries a `req_id`, every reply is an
`AGENT_RESULT`). This client only uses the latter, and drops everything else
the server pushes.
"""

import os
import json
import asyncio
import contextlib
from typing import Any

import websockets


def _default_url() -> str:
    """Mirrors the backend's OPENPROXY_WS_PORT override so a dev build running
    alongside the installed app can be targeted without editing MCP config."""
    if os.environ.get("OPENPROXY_WS_URL"):
        return os.environ["OPENPROXY_WS_URL"]
    port = os.environ.get("OPENPROXY_WS_PORT", "8765")
    return f"ws://127.0.0.1:{port}"


CONNECT_TIMEOUT = 5.0
DEFAULT_CALL_TIMEOUT = 30.0
# The handshake is answered synchronously by the backend, so anything slower
# than this means we're talking to a build that predates the agent API (it
# ignores unknown message types rather than erroring) — fail fast and say so.
HELLO_TIMEOUT = 5.0

CLIENT_NAME = "openproxy-mcp"

# Must match AGENT_PROTOCOL_VERSION in server/bridge/agent_api.py. Both ship in
# the same app bundle, so they only differ when an old MCP process outlives an
# update; the backend then tells us so in the handshake reply.
PROTOCOL_VERSION = 1


class OpenProxyUnavailable(RuntimeError):
    """Raised when the desktop app isn't running or isn't reachable."""


class OpenProxyError(RuntimeError):
    """The backend handled the call and returned an error."""


class OpenProxyClient:
    """One lazily-connected socket, shared by every MCP tool call.

    Reconnects on demand: the desktop app gets restarted far more often than
    the MCP server does, and a stale socket shouldn't take the tools down.
    """

    def __init__(self, url: str | None = None):
        self.url = url or _default_url()
        self._ws = None
        self._reader: asyncio.Task | None = None
        self._pending: dict[str, asyncio.Future] = {}
        self._req_counter = 0
        self._lock = asyncio.Lock()
        # Set from the handshake when the backend reports a protocol mismatch;
        # every tool result carries it until the process is restarted.
        self.protocol_warning: str | None = None

    # ---- connection ------------------------------------------------------

    async def _ensure_connected(self):
        async with self._lock:
            if self._ws is not None and not self._closed():
                return
            await self._teardown()
            try:
                self._ws = await asyncio.wait_for(
                    websockets.connect(self.url, ping_interval=20, ping_timeout=20),
                    timeout=CONNECT_TIMEOUT,
                )
            except Exception as e:
                raise OpenProxyUnavailable(
                    f"Can't reach OpenProxy at {self.url} ({type(e).__name__}). "
                    "Start the OpenProxy desktop app and try again."
                ) from e
            self._reader = asyncio.create_task(self._read_loop())

        # Identify as automation so the backend stops broadcasting the UI
        # event stream at us. Also doubles as a health check.
        try:
            hello = await self._call(
                "AGENT_HELLO", {"client": CLIENT_NAME, "protocol": PROTOCOL_VERSION},
                timeout=HELLO_TIMEOUT, reconnect=False,
            )
            self.protocol_warning = hello.get("warning") if isinstance(hello, dict) else None
        except OpenProxyError as e:
            await self._teardown()
            raise OpenProxyUnavailable(
                f"OpenProxy at {self.url} accepted the connection but did not "
                "answer the agent handshake. It is probably an older build "
                "without the agent API — update the OpenProxy desktop app."
            ) from e

    def _closed(self) -> bool:
        ws = self._ws
        if ws is None:
            return True
        # websockets renamed this across major versions; treat unknown as open.
        state = getattr(ws, "state", None)
        if state is not None:
            return getattr(state, "name", "") == "CLOSED"
        return bool(getattr(ws, "closed", False))

    async def _teardown(self):
        if self._reader is not None:
            self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._reader
            self._reader = None
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.close()
            self._ws = None
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(OpenProxyUnavailable("Connection to OpenProxy closed"))
        self._pending.clear()

    async def _read_loop(self):
        try:
            async for raw in self._ws:
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                # Everything that isn't a reply to one of our calls is UI
                # chatter (SYSTEM_INFO, SCRIPTS_LIST, ...) — ignore it.
                if payload.get("type") != "AGENT_RESULT":
                    continue
                fut = self._pending.pop(payload.get("req_id"), None)
                if fut is None or fut.done():
                    continue
                if payload.get("ok"):
                    fut.set_result(payload.get("data") or {})
                else:
                    fut.set_exception(OpenProxyError(payload.get("error") or "Unknown error"))
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        finally:
            # Whether the socket died or closed cleanly (the app quitting ends
            # the iterator without raising), nobody is going to answer these —
            # fail them now rather than letting each sit out its full timeout.
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(OpenProxyUnavailable("Connection to OpenProxy closed"))
            self._pending.clear()

    # ---- calls -----------------------------------------------------------

    async def call(self, msg_type: str, payload: dict[str, Any] | None = None,
                   timeout: float = DEFAULT_CALL_TIMEOUT) -> dict:
        await self._ensure_connected()
        return await self._call(msg_type, payload, timeout=timeout)

    async def _call(self, msg_type, payload=None, timeout=DEFAULT_CALL_TIMEOUT,
                    reconnect=True) -> dict:
        self._req_counter += 1
        req_id = f"{CLIENT_NAME}-{self._req_counter}"

        message = {"type": msg_type, "req_id": req_id}
        message.update(payload or {})

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending[req_id] = future

        try:
            await self._ws.send(json.dumps(message))
        except Exception as e:
            self._pending.pop(req_id, None)
            if reconnect:
                await self._teardown()
                raise OpenProxyUnavailable(
                    f"Lost connection to OpenProxy while sending {msg_type}"
                ) from e
            raise

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError as e:
            self._pending.pop(req_id, None)
            raise OpenProxyError(
                f"OpenProxy did not answer {msg_type} within {timeout}s"
            ) from e

    async def close(self):
        async with self._lock:
            await self._teardown()
