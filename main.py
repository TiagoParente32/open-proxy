import json
import asyncio
import re
import socket
import subprocess
import threading
import websockets
import webview
from mitmproxy import http, options
from mitmproxy.tools.dump import DumpMaster
import asyncio
import base64
import urllib.request
import ssl

# --- 1. NETWORK HELPERS ---
def get_local_ip():
    """Hacks a UDP socket to discover the computer's true LAN IP."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

LOCAL_IP = get_local_ip()
PROXY_PORT = 8080

# --- 2. CORE BRIDGE LOGIC ---
class ProxyUIBridge:
    def __init__(self):
        self.connected_clients = set()
        self.map_local_rules = []
        self.is_recording = True
        self.disable_cache = False
        self.bg_tasks = set()
        self.breakpoint_rules = []
        self.paused_flows = {} # Maps flow.id -> asyncio.Event
        self.breakpoints_enabled = True
        self.map_remote_rules = []

    async def request(self, flow: http.HTTPFlow):
        # 1. Respect the Pause/Play button
        if not self.is_recording:
            return

        # --- 1. AGGRESSIVE CACHE BUSTING (REQUEST) ---
        if self.disable_cache:
            flow.request.headers.pop("If-Modified-Since", None)
            flow.request.headers.pop("If-None-Match", None)
            flow.request.headers["Cache-Control"] = "no-cache"
            flow.request.headers["Pragma"] = "no-cache"

        # --- 2. SAFE BODY EXTRACTION (REQUEST) ---
        req_body = ""
        req_is_image = False
        content_type = flow.request.headers.get("Content-Type", "").lower()

        if flow.request.raw_content:
            if len(flow.request.raw_content) > 1000000 and not content_type.startswith("image/"):
                req_body = "// [Request Body too large to display (Over 1MB)]"
            elif content_type.startswith("image/"):
                try:
                    # Convert raw image bytes to a base64 string that HTML can read
                    b64_data = base64.b64encode(flow.request.raw_content).decode('utf-8')
                    req_body = f"data:{content_type};base64,{b64_data}"
                    req_is_image = True
                except Exception:
                    req_body = "// [Error encoding image data]"
            else:
                req_body = flow.request.get_text(strict=False) or "// [Binary or unreadable data]"
        
        # Now update your request_data dictionary to include the new flag!
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
            "req_is_image": req_is_image, # <-- NEW FLAG
            "res_headers": {},
            "res_body": "",
            "res_is_image": False         # <-- NEW FLAG (placeholder for now)
        }
        
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(self.broadcast_to_ui("NEW_REQUEST", request_data)) # Or "UPDATE_REQUEST"
            self.bg_tasks.add(task)
            task.add_done_callback(self.bg_tasks.discard)
        except RuntimeError:
            pass
        
        # --- MAP REMOTE (REWRITE) LOGIC ---
        for rule in self.map_remote_rules:
            if rule.get("active"):
                try:
                    pattern = rule.get("pattern", "")
                    target = rule.get("target", "")
                    # If the URL matches the pattern...
                    if re.search(pattern, flow.request.pretty_url):
                        # Replace the matched part of the URL with the target!
                        new_url = re.sub(pattern, target, flow.request.pretty_url)
                        flow.request.url = new_url
                        
                        # Crucial: Update the Host header so the destination server doesn't reject it
                        flow.request.headers["Host"] = flow.request.host
                except re.error:
                    pass

        # 3. Handle Map Local (Mocking)
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
                
        if self.breakpoints_enabled:
            for rule in self.breakpoint_rules:
                if rule.get("active") and rule.get("is_request"):
                    try:
                        # Safe regex check
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
                        # If the user typed an invalid regex like "*google", ignore the rule so we don't crash
                        print(f"⚠️ Invalid regex in breakpoint rule: {rule.get('pattern')}")
                        pass

    async def response(self, flow: http.HTTPFlow):
        # 1. Respect the Pause/Play button
        if not self.is_recording:
            return

        # --- 1. AGGRESSIVE CACHE BUSTING (RESPONSE) ---
        if self.disable_cache:
            flow.response.headers.pop("ETag", None)
            flow.response.headers.pop("Last-Modified", None)
            flow.response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            flow.response.headers["Expires"] = "0"

        # --- 2. SAFE BODY EXTRACTION (RESPONSE) ---
        res_body = ""
        res_is_image = False
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
                res_body = flow.response.get_text(strict=False) or "// [Binary or unreadable data]"
        
        duration_ms = (flow.response.timestamp_end - flow.request.timestamp_start) * 1000 if flow.response.timestamp_end else 0
        
        # Update your update_data dictionary
        update_data = {
            "id": flow.id,
            "status": flow.response.status_code,
            "duration": round(duration_ms),
            "res_bytes": len(flow.response.raw_content) if flow.response.raw_content else 0,
            "res_headers": dict(flow.response.headers),
            "res_body": res_body,
            "res_is_image": res_is_image # <-- NEW FLAG
        }
        # --- BREAKPOINT LOGIC (RESPONSE) ---
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
        # try:
        #     loop = asyncio.get_running_loop()
        #     loop.create_task(self.broadcast_to_ui("UPDATE_REQUEST", update_data))
        # except RuntimeError:
        #     pass

    async def broadcast_to_ui(self, msg_type, data):
        if not self.connected_clients: return
        message = json.dumps({"type": msg_type, "data": data})
        await asyncio.gather(*(client.send(message) for client in self.connected_clients), return_exceptions=True)

    async def websocket_handler(self, websocket):
        self.connected_clients.add(websocket)
        try:
            # Tell Vue what our real network IP is on boot
            await websocket.send(json.dumps({
                "type": "SYSTEM_INFO", 
                "data": {"ip": LOCAL_IP, "port": PROXY_PORT}
            }))

            async for message in websocket:
                payload = json.loads(message)
                
                if payload.get("type") == "UPDATE_MAP_LOCAL_RULES":
                    self.map_local_rules = payload.get("rules", [])
                
                elif payload.get("type") == "TOGGLE_PROXY":
                    self.is_recording = payload.get("is_recording")
                    
                elif payload.get("type") == "TOGGLE_CACHE":
                    self.disable_cache = payload.get("disable_cache")

                elif payload.get("type") == "UPDATE_MAP_REMOTE_RULES":
                    self.map_remote_rules = payload.get("rules", [])

                elif payload.get("type") == "SETUP_ANDROID":
                    try:
                        # 1. Set the global HTTP proxy on the running emulator
                        subprocess.run(["adb", "shell", "settings", "put", "global", "http_proxy", f"{LOCAL_IP}:{PROXY_PORT}"], check=True)
                        
                        # 2. Open the magic mitmproxy cert page directly
                        subprocess.run(["adb", "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", "http://mitm.it"], check=True)
                        
                        await websocket.send(json.dumps({
                            "type": "ALERT", 
                            "message": "✅ Proxy set! The browser is opening.\n\nClick the 'Android' icon to download, then install it from your device settings."
                        }))
                    except Exception as e:
                        await websocket.send(json.dumps({"type": "ALERT", "message": f"❌ ADB Error: {e}"}))

                elif payload.get("type") == "REPEAT_REQUEST":
                    req_data = payload.get("request", {})
                    
                    def _replay():
                        try:
                            url = req_data.get("url")
                            req = urllib.request.Request(url, method=req_data.get("method"))
                            
                            # Safely copy headers, skipping ones that urllib manages automatically
                            for k, v in req_data.get("req_headers", {}).items():
                                if k.lower() not in ["host", "content-length", "accept-encoding"]:
                                    req.add_header(k, v)
                            
                            # Attach body if it's raw text/JSON
                            body = req_data.get("req_body")
                            if body and not req_data.get("req_is_image") and not str(body).startswith("//"):
                                req.data = body.encode('utf-8')
                                
                            # Route through our own mitmproxy!
                            proxy_handler = urllib.request.ProxyHandler({
                                'http': f'http://127.0.0.1:{PROXY_PORT}',
                                'https': f'http://127.0.0.1:{PROXY_PORT}'
                            })
                            
                            # Ignore SSL errors from our own proxy cert
                            ctx = ssl.create_default_context()
                            ctx.check_hostname = False
                            ctx.verify_mode = ssl.CERT_NONE
                            
                            opener = urllib.request.build_opener(proxy_handler, urllib.request.HTTPSHandler(context=ctx))
                            opener.open(req, timeout=10)
                        except Exception as e:
                            print(f"⚠️ Replay failed: {e}")

                    # Run it in a background thread so it doesn't freeze the WebSocket!
                    threading.Thread(target=_replay, daemon=True).start()

                elif payload.get("type") == "TOGGLE_BREAKPOINTS":
                    self.breakpoints_enabled = payload.get("enabled", True)

                elif payload.get("type") == "UPDATE_BREAKPOINT_RULES":
                    self.breakpoint_rules = payload.get("rules", [])

                elif payload.get("type") == "RESOLVE_BREAKPOINT":
                    flow_id = payload.get("id")
                    action = payload.get("action") # "execute" or "drop"
                    mod_data = payload.get("modified_data", {})

                    if flow_id in self.paused_flows:
                        flow_dict = self.paused_flows.pop(flow_id)
                        flow = flow_dict["flow"]
                        
                        if action == "drop":
                            flow.kill()
                        elif action == "execute":
                            # Apply modifications from the UI
                            if payload.get("phase") == "request":
                                flow.request.method = mod_data.get("method", flow.request.method)
                                flow.request.url = mod_data.get("url", flow.request.url)
                                # Update headers and body...
                                for k, v in mod_data.get("headers", {}).items():
                                    flow.request.headers[k] = v
                                flow.request.text = mod_data.get("body", "")
                            else:
                                flow.response.status_code = int(mod_data.get("status", flow.response.status_code))
                                for k, v in mod_data.get("headers", {}).items():
                                    flow.response.headers[k] = v
                                flow.response.text = mod_data.get("body", "")

                        # Resume the mitmproxy pipeline!
                        flow_dict["event"].set()
        finally:
            self.connected_clients.remove(websocket)

# --- 3. ASYNC RUNNERS ---
async def start_proxy(bridge):
    # Bind to 0.0.0.0 so external devices (like phones) can connect
    opts = options.Options(listen_host='0.0.0.0', listen_port=PROXY_PORT)
    master = DumpMaster(opts)
    master.addons.add(bridge)
    try:
        await master.run()
    except KeyboardInterrupt:
        master.shutdown()

async def start_websocket_server(bridge):
    async with websockets.serve(bridge.websocket_handler, "127.0.0.1", 8765):
        await asyncio.Future()  # Run forever

def run_async_loop(bridge):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # NEW: Assigning to variables prevents the Garbage Collector from killing them!
    proxy_task = loop.create_task(start_proxy(bridge))
    ws_task = loop.create_task(start_websocket_server(bridge))
    
    loop.run_forever()

# --- 4. STARTUP SCRIPT ---
if __name__ == "__main__":
    bridge = ProxyUIBridge()
    
    # Start proxy and websockets in a background thread
    t = threading.Thread(target=run_async_loop, args=(bridge,), daemon=True)
    t.start()

    # Create and start the UI (private_mode=False allows local storage to persist!)
    window = webview.create_window('OpenProxy', 'ui/dist/index.html', width=1200, height=800)
    webview.start(private_mode=False, debug=True)