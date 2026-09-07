import os
import re
import json
import time
import base64
import asyncio

from mitmproxy import http
from mitmproxy.proxy.mode_servers import WireGuardServerInstance

from server import system_helpers


class ProxyHooksMixin:
    """The mitmproxy addon lifecycle hooks: running/request/response/
    websocket_message/error. mitmproxy calls these directly on the
    ProxyUIBridge instance (added as an addon in run_proxy_forever)."""

    def _get_wg_client_conf(self) -> str | None:
        """Get the WireGuard client config from the live running server instance."""
        if not self._master:
            return None
        try:
            ps = self._master.addons.get("proxyserver")
            if not ps:
                return None
            for server in ps.servers:
                if isinstance(server, WireGuardServerInstance):
                    return server.client_conf()
        except Exception as e:
            print(f"[WG] Failed to get client conf: {e}")
        return None

    async def running(self):
        """Called by mitmproxy after it has fully started. Broadcast WG status to UI."""
        if not self.wg_enabled:
            return
        # Small delay to let WireGuard server finish binding
        await asyncio.sleep(0.3)
        conf = self._get_wg_client_conf()
        if conf:
            await self.broadcast_to_ui("WG_STATUS", {
                "status": "ready",
                "enabled": True,
                "port": self.wg_port,
                "config": conf,
            })
        else:
            await self.broadcast_to_ui("WG_STATUS", {
                "status": "error",
                "enabled": True,
                "error": "WireGuard started but could not retrieve client config.",
            })

    async def request(self, flow: http.HTTPFlow):
        if not self.is_recording:
            return

        if self.throttle_profile == "Slow 3G":
            await asyncio.sleep(2.0)
        elif self.throttle_profile == "Fast 3G":
            await asyncio.sleep(0.5)

        if self.disable_cache:
            flow.request.headers.pop("If-Modified-Since", None)
            flow.request.headers.pop("If-None-Match", None)
            flow.request.headers["Cache-Control"] = "no-cache"
            flow.request.headers["Pragma"] = "no-cache"

        # User script hooks — run after built-in mutations, before recording to UI
        if self.scripts_manager.call_hooks('request', flow):
            await self._broadcast_scripts_list()

        req_body = ""
        req_is_image = False
        req_is_binary = False
        content_type = flow.request.headers.get("Content-Type", "").lower()

        if flow.request.raw_content:
            if len(flow.request.raw_content) > 1000000 and not content_type.startswith("image/"):
                req_body = "// [Request Body too large to display (Over 1MB)]"
            elif content_type.startswith("image/"):
                try:
                    b64_data = base64.b64encode(flow.request.raw_content).decode('utf-8')
                    req_body = f"data:{content_type};base64,{b64_data}"
                    req_is_image = True
                except Exception:
                    req_body = "// [Error encoding image data]"
            else:
                text = flow.request.get_text(strict=False)
                if text is None:
                    req_body = base64.b64encode(flow.request.raw_content).decode('utf-8')
                    req_is_binary = True
                else:
                    req_body = text

        raw_ip = flow.client_conn.peername[0] if flow.client_conn.peername else "Unknown"
        hostname = system_helpers._hostname_cache.get(raw_ip)  # None if not yet resolved
        if raw_ip not in system_helpers._hostname_cache and raw_ip != "Unknown":
            # Fire background resolution — result cached for future requests
            loop = asyncio.get_running_loop()
            task = loop.create_task(system_helpers._resolve_hostname_bg(raw_ip, self))
            self.bg_tasks.add(task)
            task.add_done_callback(self.bg_tasks.discard)

        request_data = {
            "id": flow.id,
            "client_ip": raw_ip,
            "client_hostname": hostname,
            "method": flow.request.method,
            "url": flow.request.pretty_url,
            "status": "...",
            "time": flow.request.timestamp_start,
            "req_bytes": len(flow.request.raw_content) if flow.request.raw_content else 0,
            "duration": 0,
            "res_bytes": 0,
            "req_headers": dict(flow.request.headers),
            "req_body": req_body,
            "req_is_image": req_is_image,
            "req_is_binary": req_is_binary,
            "res_headers": {},
            "res_body": "",
            "res_is_image": False,
            "res_is_binary": False
        }

        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(self.broadcast_to_ui("NEW_REQUEST", request_data))
            self.bg_tasks.add(task)
            task.add_done_callback(self.bg_tasks.discard)
        except RuntimeError:
            pass

        if self.map_remote_enabled:
            for rule in self.map_remote_rules:
                if rule.get("active"):
                    try:
                        pattern = rule.get("pattern", "")
                        target = rule.get("target", "")
                        if re.search(pattern, flow.request.pretty_url):
                            new_url = re.sub(pattern, target, flow.request.pretty_url)
                            flow.request.url = new_url
                            flow.request.headers["Host"] = flow.request.host
                    except re.error:
                        pass

        if self.map_local_enabled:
            for rule in self.map_local_rules:
                pattern = rule.get("pattern", "")
                strict_regex = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
                rule_method = rule.get("method", "ANY").upper()

                method_match = rule_method == "ANY" or rule_method == flow.request.method.upper()
                if rule.get("active") and method_match and re.search(strict_regex, flow.request.pretty_url):
                    try:
                        status_code = int(rule.get("status", 200))
                        headers_dict = {}
                        try:
                            if rule.get("headers"):
                                headers_dict = json.loads(rule.get("headers"))
                        except json.JSONDecodeError:
                            headers_dict = {"Content-Type": "text/plain"}

                        req_headers_mod = rule.get("req_headers_mod", {})
                        if isinstance(req_headers_mod, dict):
                            for k, v in req_headers_mod.items():
                                if k:
                                    flow.request.headers[k] = str(v)

                        file_path = rule.get("file_path", "")
                        body_source = rule.get("body_source", "inline")
                        if body_source == "file" and file_path and os.path.isfile(file_path):
                            import mimetypes
                            body_bytes = await asyncio.to_thread(lambda p=file_path: open(p, "rb").read())
                            if "Content-Type" not in headers_dict:
                                mime, _ = mimetypes.guess_type(file_path)
                                headers_dict["Content-Type"] = mime or "application/octet-stream"
                        else:
                            body_bytes = rule.get("body", "").encode("utf-8")

                        headers_dict["X-Map-Local"] = "Active"
                        flow.response = http.Response.make(status_code, body_bytes, headers_dict)
                        return
                    except Exception as e:
                        flow.response = http.Response.make(500, f"Editor Error: {e}".encode())
                        return

        if self.breakpoints_enabled:
            for rule in self.breakpoint_rules:
                if rule.get("active") and rule.get("is_request"):
                    try:
                        pattern = rule.get("pattern", "")
                        strict_regex = "^" + pattern.replace("*", ".*") + "$"

                        if re.search(strict_regex, flow.request.pretty_url):
                            pause_event = asyncio.Event()
                            self.paused_flows[flow.id] = {"event": pause_event, "flow": flow}

                            bp_data = {
                                "id": flow.id,
                                "phase": "request",
                                "url": flow.request.pretty_url,
                                "method": flow.request.method,
                                "headers": dict(flow.request.headers),
                                "body": flow.request.get_text(strict=False) or ""
                            }

                            await self.broadcast_to_ui("BREAKPOINT_HIT", bp_data)
                            await pause_event.wait()
                            try:
                                loop = asyncio.get_running_loop()
                                req_update = {
                                    "id": flow.id,
                                    "method": flow.request.method,
                                    "url": flow.request.pretty_url,
                                    "req_bytes": len(flow.request.raw_content) if flow.request.raw_content else 0,
                                    "req_headers": dict(flow.request.headers),
                                    "req_body": flow.request.get_text(strict=False) or "",
                                }
                                task = loop.create_task(self.broadcast_to_ui("UPDATE_REQUEST", req_update))
                                self.bg_tasks.add(task)
                                task.add_done_callback(self.bg_tasks.discard)
                            except RuntimeError:
                                pass
                            break
                    except re.error:
                        pass

    async def response(self, flow: http.HTTPFlow):
        if not self.is_recording:
            return

        if self.throttle_profile == "Slow 3G":
            await asyncio.sleep(2.0)
        elif self.throttle_profile == "Fast 3G":
            await asyncio.sleep(0.5)

        if self.disable_cache:
            flow.response.headers.pop("ETag", None)
            flow.response.headers.pop("Last-Modified", None)
            flow.response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            flow.response.headers["Expires"] = "0"

        if self.scripts_manager.call_hooks('response', flow):
            await self._broadcast_scripts_list()

        res_body = ""
        res_is_image = False
        res_is_binary = False
        content_type = flow.response.headers.get("Content-Type", "").lower()

        if flow.response.raw_content:
            if len(flow.response.raw_content) > 1000000 and not content_type.startswith("image/"):
                res_body = "// [Response Body too large to display (Over 1MB)]"
            elif content_type.startswith("image/"):
                try:
                    b64_data = base64.b64encode(flow.response.raw_content).decode('utf-8')
                    res_body = f"data:{content_type};base64,{b64_data}"
                    res_is_image = True
                except Exception:
                    res_body = "// [Error encoding image data]"
            else:
                flow.response.decode(strict=False)
                text = flow.response.get_text(strict=False)
                if text is None:
                    res_body = base64.b64encode(flow.response.raw_content).decode('utf-8')
                    res_is_binary = True
                else:
                    res_body = text

        duration_ms = (flow.response.timestamp_end - flow.request.timestamp_start) * 1000 if flow.response.timestamp_end else 0

        if self.breakpoints_enabled:
            for rule in self.breakpoint_rules:
                if rule.get("active") and rule.get("is_response"):
                    try:
                        pattern = rule.get("pattern", "")
                        strict_regex = "^" + pattern.replace("*", ".*") + "$"

                        if re.search(strict_regex, flow.request.pretty_url):
                            pause_event = asyncio.Event()
                            self.paused_flows[flow.id] = {"event": pause_event, "flow": flow}

                            bp_data = {
                                "id": flow.id,
                                "phase": "response",
                                "url": flow.request.pretty_url,
                                "method": flow.request.method,
                                "status": flow.response.status_code,
                                "headers": dict(flow.response.headers),
                                "body": flow.response.get_text(strict=False) or ""
                            }

                            await self.broadcast_to_ui("BREAKPOINT_HIT", bp_data)
                            await pause_event.wait()
                            # Rebuild body fields after user may have modified the response
                            res_body = flow.response.get_text(strict=False) or ""
                            res_is_image = False
                            res_is_binary = False
                            content_type = flow.response.headers.get("Content-Type", "").lower()
                            if content_type.startswith("image/") and flow.response.raw_content:
                                try:
                                    b64_data = base64.b64encode(flow.response.raw_content).decode('utf-8')
                                    res_body = f"data:{content_type};base64,{b64_data}"
                                    res_is_image = True
                                except Exception:
                                    pass
                            break
                    except re.error:
                        pass

        update_data = {
            "id": flow.id,
            "status": flow.response.status_code,
            "duration": round(duration_ms),
            "res_bytes": len(flow.response.raw_content) if flow.response.raw_content else 0,
            "req_headers": dict(flow.request.headers),
            "res_headers": dict(flow.response.headers),
            "res_body": res_body,
            "res_is_image": res_is_image,
            "res_is_binary": res_is_binary,
            "map_local": flow.response.headers.get("X-Map-Local") == "Active"
        }

        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(self.broadcast_to_ui("UPDATE_REQUEST", update_data))
            self.bg_tasks.add(task)
            task.add_done_callback(self.bg_tasks.discard)
        except RuntimeError:
            pass

    async def websocket_message(self, flow: http.HTTPFlow):
        if not self.is_recording:
            return

        if not hasattr(flow, 'websocket') or not flow.websocket or not flow.websocket.messages:
            return

        latest_msg = flow.websocket.messages[-1]

        if self.scripts_manager.call_hooks('websocket_message', flow):
            await self._broadcast_scripts_list()

        try:
            content_str = latest_msg.content.decode('utf-8')
        except UnicodeDecodeError:
            content_str = f"<Binary Data: {len(latest_msg.content)} bytes>"

        payload = {
            "type": "WS_MESSAGE",
            "id": str(flow.id),
            "is_client": latest_msg.from_client,
            "content": content_str,
            "size": len(latest_msg.content),
            "timestamp": time.time()
        }

        for ws in list(self.connected_clients):
            try:
                await ws.send(json.dumps(payload))
            except Exception as e:
                print(f"[DEBUG WS ERROR] Failed to send to UI: {e}")

    async def error(self, flow: http.HTTPFlow):
        """mitmproxy lifecycle hook — connection/protocol errors."""
        if self.scripts_manager.call_hooks('error', flow):
            await self._broadcast_scripts_list()
