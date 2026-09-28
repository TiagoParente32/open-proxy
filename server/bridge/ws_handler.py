import sys
import json
import ssl
import asyncio
import threading
import urllib.request

from server import system_helpers
from server.scripting import DEFAULT_SCRIPT
from server.updater import check_for_updates, apply_update, _friendly_update_error


class WsHandlerMixin:
    """The single WebSocket connection handler: sends initial state to a newly
    connected UI client, then dispatches every incoming message by `type` to
    the right mixin method (Android/iOS setup, macOS proxy, scripting,
    map local/remote, breakpoints, WireGuard, updates, ...)."""

    async def websocket_handler(self, websocket):
        self.connected_clients.add(websocket)
        try:
            await websocket.send(json.dumps({
                "type": "SYSTEM_INFO",
                "data": {
                    "ip": system_helpers.LOCAL_IP,
                    "port": self.proxy_port,
                    "platform": sys.platform,
                    "mac_proxy_active": self.is_mac_proxy_set,
                }
            }))

            if self.pending_update_info:
                await websocket.send(json.dumps({"type": "UPDATE_AVAILABLE", "data": self.pending_update_info}))
                self.pending_update_info = None

            await websocket.send(json.dumps({"type": "SCRIPTS_LIST", "data": {"scripts": self.scripts_manager.state_list()}}))

            async for message in websocket:
                payload = json.loads(message)

                if payload.get("type") == "UPDATE_MAP_LOCAL_RULES":
                    self.map_local_rules = payload.get("rules", [])

                elif payload.get("type") == "UPDATE_THROTTLE":
                    self.throttle_profile = payload.get("profile", "None")

                elif payload.get("type") == "TOGGLE_PROXY":
                    self.is_recording = payload.get("is_recording")

                elif payload.get("type") == "TOGGLE_CACHE":
                    self.disable_cache = payload.get("disable_cache")

                elif payload.get("type") == "UPDATE_PROXY_OPTIONS":
                    if self._master:
                        opts = {}
                        if "http2" in payload:
                            opts["http2"] = bool(payload["http2"])
                        if "upstream_cert" in payload:
                            opts["upstream_cert"] = bool(payload["upstream_cert"])
                        if "ignore_hosts" in payload:
                            hosts = payload["ignore_hosts"]
                            opts["ignore_hosts"] = [h for h in hosts if h.strip()]
                        if "allow_hosts" in payload:
                            hosts = payload["allow_hosts"]
                            opts["allow_hosts"] = [h for h in hosts if h.strip()]
                        if opts:
                            self._master.options.update(**opts)
                            n_ignore = len(opts.get('ignore_hosts', []))
                            n_allow  = len(opts.get('allow_hosts', []))
                            print(f"[Proxy] Options updated: http2={opts.get('http2', '?')} upstream_cert={opts.get('upstream_cert', '?')} ignore_hosts={n_ignore} allow_hosts={n_allow}")

                elif payload.get("type") == "UPDATE_MAP_REMOTE_RULES":
                    self.map_remote_rules = payload.get("rules", [])

                elif payload.get("type") == "LIST_ADB_DEVICES":
                    asyncio.create_task(self.handle_list_adb_devices(websocket))

                # ---- List AVDs (including offline ones) and boot them on demand ----
                elif payload.get("type") == "LIST_AVDS":
                    asyncio.create_task(self.handle_list_avds(websocket))

                elif payload.get("type") == "BOOT_AVD":
                    avd_name = payload.get("name")
                    if avd_name:
                        asyncio.create_task(self.boot_avd(websocket, avd_name))

                elif payload.get("type") == "SETUP_ANDROID_DEVICE":
                    serial = payload.get("serial")
                    device_type = payload.get("device_type", "emulator")
                    if serial:
                        asyncio.create_task(self.setup_android_device(websocket, serial, device_type))

                # Kept for backward compatibility with older UI builds that
                # only ever targeted the default emulator, not a specific serial.
                elif payload.get("type") == "SETUP_ANDROID":
                    asyncio.create_task(self.setup_android_device(websocket, "emulator-5554", "emulator"))

                elif payload.get("type") == "REVERT_ANDROID_DEVICE":
                    serial = payload.get("serial")
                    if serial:
                        asyncio.create_task(self.revert_android_device(websocket, serial))

                # ---- Push the CA cert straight into the device's Downloads folder ----
                elif payload.get("type") == "PUSH_CERT_TO_DOWNLOADS":
                    serial = payload.get("serial")
                    print(f"[WS] Received PUSH_CERT_TO_DOWNLOADS serial={serial!r}", flush=True)
                    if serial:
                        asyncio.create_task(self.push_cert_to_downloads(websocket, serial))
                    else:
                        print("[WS] PUSH_CERT_TO_DOWNLOADS ignored: no serial provided", flush=True)

                elif payload.get("type") == "LIST_IOS_SIMULATORS":
                    asyncio.create_task(self.handle_list_ios_simulators(websocket))

                elif payload.get("type") == "BOOT_IOS_SIMULATOR":
                    udid = payload.get("udid")
                    if udid:
                        asyncio.create_task(self.boot_ios_simulator(websocket, udid))

                elif payload.get("type") == "SETUP_IOS_SIMULATOR":
                    udid = payload.get("udid")
                    if udid:
                        asyncio.create_task(self.setup_ios_simulator(websocket, udid))

                elif payload.get("type") == "REVERT_IOS_SIMULATOR":
                    udid = payload.get("udid")
                    if udid:
                        asyncio.create_task(self.revert_ios_simulator(websocket, udid))

                elif payload.get("type") == "REPEAT_REQUEST":
                    req_data = payload.get("request", {})

                    def _replay():
                        try:
                            url = req_data.get("url")
                            if not url or url == "https://":
                                print("[WARNING] Invalid URL in composer.")
                                return

                            method = req_data.get("method", "GET").upper()
                            req = urllib.request.Request(url, method=method)

                            raw_headers = req_data.get("req_headers", {})
                            if isinstance(raw_headers, str):
                                try:
                                    raw_headers = json.loads(raw_headers)
                                except Exception:
                                    raw_headers = {}

                            for k, v in raw_headers.items():
                                if k.lower() not in ["host", "content-length", "accept-encoding"]:
                                    req.add_header(k, str(v))

                            body = req_data.get("req_body")
                            if body and method in ["POST", "PUT", "PATCH"]:
                                if not req_data.get("req_is_image") and not str(body).startswith("//"):
                                    req.data = body.encode('utf-8')
                                    req.add_header('Content-Length', str(len(req.data)))

                            proxy_handler = urllib.request.ProxyHandler({
                                'http': f'http://127.0.0.1:{self.proxy_port}',
                                'https': f'http://127.0.0.1:{self.proxy_port}'
                            })

                            ctx = ssl.create_default_context()
                            ctx.check_hostname = False
                            ctx.verify_mode = ssl.CERT_NONE

                            opener = urllib.request.build_opener(proxy_handler, urllib.request.HTTPSHandler(context=ctx))
                            opener.open(req, timeout=300)
                            print(f"[INFO] Successfully injected {method} to {url}")

                        except Exception as e:
                            print(f"[ERROR] Replay failed: {e}")

                    threading.Thread(target=_replay, daemon=True).start()

                elif payload.get("type") == "TOGGLE_BREAKPOINTS":
                    self.breakpoints_enabled = payload.get("enabled", True)

                elif payload.get("type") == "UPDATE_BREAKPOINT_RULES":
                    self.breakpoint_rules = payload.get("rules", [])

                elif payload.get("type") == "TOGGLE_MAP_LOCAL":
                    self.map_local_enabled = payload.get("enabled", True)

                elif payload.get("type") == "TOGGLE_MAP_REMOTE":
                    self.map_remote_enabled = payload.get("enabled", True)

                elif payload.get("type") == "RESOLVE_BREAKPOINT":
                    flow_id = payload.get("id")
                    action = payload.get("action")
                    mod_data = payload.get("modified_data", {})

                    if flow_id in self.paused_flows:
                        flow_dict = self.paused_flows.pop(flow_id)
                        flow = flow_dict["flow"]

                        if action == "drop":
                            flow.kill()
                        elif action == "execute":
                            if payload.get("phase") == "request":
                                flow.request.method = mod_data.get("method", flow.request.method)
                                flow.request.url = mod_data.get("url", flow.request.url)
                                for k, v in mod_data.get("headers", {}).items():
                                    flow.request.headers[k] = v
                                flow.request.text = mod_data.get("body", "")
                            else:
                                flow.response.status_code = int(mod_data.get("status", flow.response.status_code))
                                for k, v in mod_data.get("headers", {}).items():
                                    flow.response.headers[k] = v
                                flow.response.text = mod_data.get("body", "")

                        flow_dict["event"].set()

                elif payload.get("type") == "TOGGLE_WG_MODE":
                    self.wg_enabled = payload.get("enabled", False)
                    port = payload.get("port")
                    if port:
                        self.wg_port = int(port)

                    if not self._master:
                        self.wg_enabled = False
                        await websocket.send(json.dumps({
                            "type": "WG_STATUS",
                            "data": {"status": "error", "enabled": False,
                                     "error": "Proxy is not running."},
                        }))
                    elif self.wg_enabled:
                        # Dynamically add WireGuard - no restart, port 9090 stays bound
                        await websocket.send(json.dumps({
                            "type": "WG_STATUS",
                            "data": {"status": "starting", "enabled": True},
                        }))
                        self._master.options.update(
                            mode=["regular", f"wireguard@{self.wg_port}"]
                        )
                        # Poll until the WireGuard server is live (up to 5s)
                        conf = None
                        for _ in range(20):
                            await asyncio.sleep(0.25)
                            conf = self._get_wg_client_conf()
                            if conf or not self._master:
                                break
                        if conf:
                            await self.broadcast_to_ui("WG_STATUS", {
                                "status": "ready", "enabled": True,
                                "port": self.wg_port, "config": conf,
                            })
                        elif self._master:
                            # Still running but WG didn't come up in time
                            self.wg_enabled = False
                            await self.broadcast_to_ui("WG_STATUS", {
                                "status": "error", "enabled": False,
                                "error": self._last_startup_error or "WireGuard timed out.",
                            })
                        # else: master crashed - SystemExit handler broadcasts the error
                    else:
                        # Dynamically remove WireGuard - no restart needed
                        self._master.options.update(mode=["regular"])
                        await self.broadcast_to_ui("WG_STATUS", {
                            "status": "disabled", "enabled": False,
                        })

                elif payload.get("type") == "GET_WG_CLIENT_CONF":
                    conf = self._get_wg_client_conf()
                    if conf:
                        await websocket.send(json.dumps({
                            "type": "WG_STATUS",
                            "data": {
                                "status": "ready",
                                "enabled": self.wg_enabled,
                                "port": self.wg_port,
                                "config": conf,
                            },
                        }))
                    else:
                        await websocket.send(json.dumps({
                            "type": "WG_STATUS",
                            "data": {
                                "status": "error" if self.wg_enabled else "disabled",
                                "enabled": self.wg_enabled,
                                "error": "WireGuard server is not running." if self.wg_enabled else "",
                            },
                        }))

                elif payload.get("type") == "SET_MAC_PROXY":
                    await self._toggle_macos_proxy(websocket, enable=True)

                elif payload.get("type") == "UNSET_MAC_PROXY":
                    await self._toggle_macos_proxy(websocket, enable=False)

                elif payload.get("type") == "CHECK_CERT_TRUST":
                    asyncio.create_task(self.handle_check_cert_trust(websocket))

                elif payload.get("type") == "TRUST_CERT":
                    asyncio.create_task(self.handle_trust_cert(websocket))

                elif payload.get("type") == "SCRIPT_SAVE":
                    self.scripts_manager.save_script(
                        payload.get("id", ""),
                        payload.get("name", "Script"),
                        payload.get("content", DEFAULT_SCRIPT),
                        bool(payload.get("enabled", False)),
                    )
                    await self._broadcast_scripts_list()

                elif payload.get("type") == "SCRIPT_TOGGLE":
                    self.scripts_manager.toggle_script(
                        payload.get("id", ""),
                        bool(payload.get("enabled", False)),
                    )
                    await self._broadcast_scripts_list()

                elif payload.get("type") == "SCRIPT_NEW":
                    self.scripts_manager.new_script(payload.get("name", "New Script"))
                    await self._broadcast_scripts_list()

                elif payload.get("type") == "SCRIPT_DELETE":
                    self.scripts_manager.delete_script(payload.get("id", ""))
                    await self._broadcast_scripts_list()

                elif payload.get("type") == "SCRIPT_RENAME":
                    sid = payload.get("id", "")
                    for s in self.scripts_manager._scripts:
                        if s["id"] == sid:
                            s["name"] = payload.get("name", s["name"])
                            self.scripts_manager._save_meta()
                            break
                    await self._broadcast_scripts_list()

                elif payload.get("type") == "SCRIPTS_IMPORT":
                    self.scripts_manager.import_all(payload.get("scripts", []))
                    await self._broadcast_scripts_list()

                elif payload.get("type") == "CHECK_FOR_UPDATES":
                    async def _check():
                        try:
                            info = await asyncio.get_event_loop().run_in_executor(None, check_for_updates)
                        except Exception as e:
                            await websocket.send(json.dumps({
                                "type": "UPDATE_CHECK_ERROR",
                                "data": {"error": _friendly_update_error(e)},
                            }))
                            return
                        if info:
                            await websocket.send(json.dumps({"type": "UPDATE_AVAILABLE", "data": info}))
                        else:
                            await websocket.send(json.dumps({"type": "UP_TO_DATE"}))
                    asyncio.create_task(_check())

                elif payload.get("type") == "APPLY_UPDATE":
                    download_url = payload.get("download_url")
                    if download_url:
                        bridge = self
                        loop = asyncio.get_event_loop()

                        def _run_update():
                            try:
                                def progress(pct):
                                    asyncio.run_coroutine_threadsafe(
                                        bridge.broadcast_to_ui("UPDATE_PROGRESS", {"pct": pct}), loop
                                    )

                                apply_update(download_url, progress_cb=progress)

                                asyncio.run_coroutine_threadsafe(
                                    bridge.broadcast_to_ui("UPDATE_READY", {}), loop
                                )
                            except Exception as e:
                                print(f"[Update] apply_update failed: {e}")
                                asyncio.run_coroutine_threadsafe(
                                    bridge.broadcast_to_ui("UPDATE_ERROR", {"error": str(e)}), loop
                                )

                        threading.Thread(target=_run_update, daemon=True).start()

        finally:
            self.connected_clients.remove(websocket)
