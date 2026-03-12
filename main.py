import os
import sys
import json
import time
import socket
import asyncio
import re
import base64
import subprocess
import threading
import ssl
import urllib.request
import websockets
import webview
from mitmproxy import http, options
from mitmproxy.tools.dump import DumpMaster

# ============================================================================
# 1. NETWORK & SYSTEM HELPERS
# ============================================================================
def get_local_ip():
    """Hacks a UDP socket to discover the computer's true LAN IP."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def get_free_port(starting_port=9090):
    port = starting_port
    while port <= 65535:
        print(f"Checking port {port}")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('0.0.0.0', port))
                return port
            except OSError:
                port += 1

def get_resource_path(relative_path):
    """ Get the absolute path to a resource. Works for dev and for PyInstaller! """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

LOCAL_IP = get_local_ip()

# ============================================================================
# 2. CORE BRIDGE LOGIC (Mitmproxy -> Vue UI)
# ============================================================================
class ProxyUIBridge:
    def __init__(self, proxy_port):
        self.proxy_port = proxy_port
        self.connected_clients = set()
        self.bg_tasks = set()
        
        # State
        self.is_recording = True
        self.disable_cache = False
        self.throttle_profile = "None"
        
        # Rules & Modals
        self.map_local_enabled = True
        self.map_local_rules = []
        self.map_remote_enabled = True
        self.map_remote_rules = []
        self.breakpoints_enabled = True
        self.breakpoint_rules = []
        self.paused_flows = {}

    async def request(self, flow: http.HTTPFlow):
        if not self.is_recording:
            return
        
        if self.throttle_profile == "Slow 3G":
            await asyncio.sleep(2.0)
        elif self.throttle_profile == "Fast 3G":
            await asyncio.sleep(0.5)

        # --- CACHE BUSTING ---
        if self.disable_cache:
            flow.request.headers.pop("If-Modified-Since", None)
            flow.request.headers.pop("If-None-Match", None)
            flow.request.headers["Cache-Control"] = "no-cache"
            flow.request.headers["Pragma"] = "no-cache"

        # --- SAFE BODY EXTRACTION ---
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
                    # It's pure binary! Send it as base64 so Vue can hex-dump it
                    req_body = base64.b64encode(flow.request.raw_content).decode('utf-8')
                    req_is_binary = True
                else:
                    req_body = text        
        request_data = {
            "id": flow.id,
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
        
        # --- MAP REMOTE ---
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

        # --- MAP LOCAL ---
        if self.map_local_enabled:
            for rule in self.map_local_rules:
                if rule.get("active") and re.search(rule.get("pattern", ""), flow.request.pretty_url):
                    try:
                        status_code = int(rule.get("status", 200))
                        body_text = rule.get("body", "").encode('utf-8')
                        headers_dict = {}
                        try:
                            if rule.get("headers"):
                                headers_dict = json.loads(rule.get("headers"))
                        except json.JSONDecodeError:
                            headers_dict = {"Content-Type": "text/plain"}

                        headers_dict["X-Map-Local"] = "Active"
                        flow.response = http.Response.make(status_code, body_text, headers_dict)
                        return 
                    except Exception as e:
                        flow.response = http.Response.make(500, f"Editor Error: {e}".encode())
                        return
                
        # --- BREAKPOINTS (REQUEST) ---
        if self.breakpoints_enabled:
            for rule in self.breakpoint_rules:
                if rule.get("active") and rule.get("is_request"):
                    try:
                        if re.search(rule.get("pattern", ""), flow.request.pretty_url):
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

        # --- CACHE BUSTING ---
        if self.disable_cache:
            flow.response.headers.pop("ETag", None)
            flow.response.headers.pop("Last-Modified", None)
            flow.response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            flow.response.headers["Expires"] = "0"

        # --- SAFE BODY EXTRACTION ---
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
                    # It's pure binary! Send it as base64
                    res_body = base64.b64encode(flow.response.raw_content).decode('utf-8')
                    res_is_binary = True
                else:
                    res_body = text
        
        duration_ms = (flow.response.timestamp_end - flow.request.timestamp_start) * 1000 if flow.response.timestamp_end else 0
        
        update_data = {
            "id": flow.id,
            "status": flow.response.status_code,
            "duration": round(duration_ms),
            "res_bytes": len(flow.response.raw_content) if flow.response.raw_content else 0,
            "res_headers": dict(flow.response.headers),
            "res_body": res_body,
            "res_is_image": res_is_image,
            "res_is_binary": res_is_binary
        }

        # --- BREAKPOINTS (RESPONSE) ---
        if self.breakpoints_enabled:
            for rule in self.breakpoint_rules:
                if rule.get("active") and rule.get("is_response"):
                    try:
                        if re.search(rule.get("pattern", ""), flow.request.pretty_url):
                            pause_event = asyncio.Event()
                            self.paused_flows[flow.id] = {"event": pause_event, "flow": flow}
                            
                            bp_data = {
                                "id": flow.id,
                                "phase": "response",
                                "url": flow.request.pretty_url,
                                "status": flow.response.status_code,
                                "headers": dict(flow.response.headers),
                                "body": flow.response.get_text(strict=False) or ""
                            }
                            
                            await self.broadcast_to_ui("BREAKPOINT_HIT", bp_data)
                            await pause_event.wait()
                            break
                    except re.error:
                        pass
        
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

        if not hasattr(flow, 'messages') or not flow.messages:
            return
            
        latest_msg = flow.messages[-1]
        
        try:
            content_str = latest_msg.content.decode('utf-8')
        except UnicodeDecodeError:
            content_str = f"<Binary Data: {len(latest_msg.content)} bytes>"

        if hasattr(flow, 'handshake_flow') and flow.handshake_flow:
            target_id = str(flow.handshake_flow.id)
        else:
            target_id = str(flow.id)

        payload = {
            "type": "WS_MESSAGE",
            "id": target_id, 
            "is_client": latest_msg.from_client,
            "content": content_str,
            "size": len(latest_msg.content),
            "timestamp": time.time()
        }

        if hasattr(self, 'connected_clients') and self.connected_clients:
            for ws in self.connected_clients:
                try:
                    await ws.send(json.dumps(payload))
                except Exception:
                    pass

    async def setup_android_emulator(self, ws):
        async def update(step_id, status, msg=""):
            await ws.send(json.dumps({"type": "SETUP_PROGRESS", "step": step_id, "status": status, "message": msg}))

        try:
            await update("check_adb", "start")
            subprocess.run(["adb", "version"], check=True, capture_output=True)
            await asyncio.sleep(0.5)
            await update("check_adb", "success")

            await update("cert_prepare", "start")
            cert_path = os.path.expanduser("~/.mitmproxy/mitmproxy-ca-cert.pem")
            if not os.path.exists(cert_path):
                await update("cert_prepare", "error", "Certificate not found. Start proxy first!")
                return

            hash_proc = subprocess.run(["openssl", "x509", "-inform", "PEM", "-subject_hash_old", "-in", cert_path], capture_output=True, text=True, check=True)
            cert_hash = hash_proc.stdout.splitlines()[0].strip()
            hashed_cert_name = f"{cert_hash}.0"

            subprocess.run(["openssl", "x509", "-in", cert_path, "-inform", "PEM", "-outform", "DER", "-out", hashed_cert_name], check=True)
            await update("cert_prepare", "success")

            await update("root_emu", "start")
            subprocess.run(["adb", "root"], check=True)
            await asyncio.sleep(1.5)
            await update("root_emu", "success")

            await update("push_cert", "start")
            subprocess.run(["adb", "push", hashed_cert_name, f"/data/misc/user/0/cacerts-added/{hashed_cert_name}"], check=True)
            subprocess.run(["adb", "shell", "su", "0", "chmod", "644", f"/data/misc/user/0/cacerts-added/{hashed_cert_name}"], check=True)
            if os.path.exists(hashed_cert_name):
                os.remove(hashed_cert_name)
            await update("push_cert", "success")

            await update("set_proxy", "start")
            # --- DYNAMIC PORT INJECTED HERE ---
            subprocess.run(["adb", "shell", "settings", "put", "global", "http_proxy", f"10.0.2.2:{self.proxy_port}"], check=True)
            await asyncio.sleep(0.5)
            await update("set_proxy", "success")

            await update("done", "success")

        except Exception as e:
            await update("current_active_step", "error", str(e))

    async def broadcast_to_ui(self, msg_type, data):
        if not self.connected_clients: return
        message = json.dumps({"type": msg_type, "data": data})
        await asyncio.gather(*(client.send(message) for client in self.connected_clients), return_exceptions=True)

    async def websocket_handler(self, websocket):
        self.connected_clients.add(websocket)
        try:
            # Tell Vue what our real network IP and dynamic port are
            await websocket.send(json.dumps({
                "type": "SYSTEM_INFO", 
                "data": {"ip": LOCAL_IP, "port": self.proxy_port} # <-- Dynamic
            }))

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

                elif payload.get("type") == "UPDATE_MAP_REMOTE_RULES":
                    self.map_remote_rules = payload.get("rules", [])

                elif payload.get("type") == "SETUP_ANDROID":
                    asyncio.create_task(self.setup_android_emulator(websocket))

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
                            
                            # 1. Safely handle headers (in case Vue sent them as a JSON string)
                            raw_headers = req_data.get("req_headers", {})
                            if isinstance(raw_headers, str):
                                import json
                                try:
                                    raw_headers = json.loads(raw_headers)
                                except Exception:
                                    raw_headers = {}

                            for k, v in raw_headers.items():
                                if k.lower() not in ["host", "content-length", "accept-encoding"]:
                                    req.add_header(k, str(v))
                            
                            # 2. Safely handle the body and calculate Content-Length
                            body = req_data.get("req_body")
                            # Only attach bodies for methods that expect them
                            if body and method in ["POST", "PUT", "PATCH"]:
                                # Don't send placeholder warnings as data
                                if not req_data.get("req_is_image") and not str(body).startswith("//"):
                                    req.data = body.encode('utf-8')
                                    req.add_header('Content-Length', str(len(req.data)))
                            
                            # 3. Dynamic proxy injection
                            proxy_handler = urllib.request.ProxyHandler({
                                'http': f'http://127.0.0.1:{self.proxy_port}',
                                'https': f'http://127.0.0.1:{self.proxy_port}'
                            })
                            
                            ctx = ssl.create_default_context()
                            ctx.check_hostname = False
                            ctx.verify_mode = ssl.CERT_NONE
                            
                            opener = urllib.request.build_opener(proxy_handler, urllib.request.HTTPSHandler(context=ctx))
                            
                            # Bumped timeout to 30s so you have time to interact with breakpoints!
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

                elif payload.get("type") == "EXPORT_FILE":
                    filename = payload.get("filename", "export.json")
                    file_data = payload.get("data", "")
                    try:
                        window = webview.windows[0]
                        result = window.create_file_dialog(webview.SAVE_DIALOG, save_filename=filename)
                        if result and len(result) > 0:
                            save_path = result[0]
                            if isinstance(save_path, tuple): 
                                save_path = save_path[0]
                            with open(save_path, 'w', encoding='utf-8') as f:
                                f.write(file_data)
                    except Exception as e:
                        print(f"Failed to open save dialog: {e}")

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
        finally:
            self.connected_clients.remove(websocket)


# ============================================================================
# 3. ASYNC RUNNERS (Background Threads)
# ============================================================================
async def start_proxy(bridge, proxy_port):
    opts = options.Options(listen_host='0.0.0.0', listen_port=proxy_port)
    master = DumpMaster(opts, with_termlog=False, with_dumper=False)
    master.addons.add(bridge)
    try:
        await master.run()
    except KeyboardInterrupt:
        master.shutdown()

async def start_websocket_server(bridge):
    async with websockets.serve(bridge.websocket_handler, "127.0.0.1", 8765):
        await asyncio.Future()

def run_async_loop(bridge, proxy_port):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    proxy_task = loop.create_task(start_proxy(bridge, proxy_port))
    ws_task = loop.create_task(start_websocket_server(bridge))
    
    loop.run_forever()


# ============================================================================
# 4. APP ENTRY POINT
# ============================================================================
if __name__ == "__main__":
    # --- GET DYNAMIC PORT FIRST ---
    ACTIVE_PROXY_PORT = get_free_port(9090)
    print(f"Starting OpenProxy on port {ACTIVE_PROXY_PORT}")

    # Pass the port into our bridge
    bridge = ProxyUIBridge(proxy_port=ACTIVE_PROXY_PORT)
    
    # Start the async systems in the background
    t = threading.Thread(target=run_async_loop, args=(bridge, ACTIVE_PROXY_PORT), daemon=True)
    t.start()

    # Boot up the Vue UI Window
    html_path = get_resource_path('ui/dist/index.html')
    icon_path = get_resource_path('icon.png')
    
    window = webview.create_window(
        title='OpenProxy', 
        url=html_path, 
        width=1024, 
        height=720,
        min_size=(1024, 720),
        background_color='#1a1a1b'
    )
    
    webview.start(private_mode=False, debug=True, icon=icon_path)