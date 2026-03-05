import os
import sys
import threading
import asyncio
import webview
import websockets
from mitmproxy import http
from mitmproxy.tools.dump import DumpMaster
from mitmproxy.options import Options
import json
import re           # NEW IMPORT
import mimetypes    # NEW IMPORT

def get_asset_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class ProxyUIBridge:
    def __init__(self):
        self.connected_clients = set()
        self.map_local_rules = []
        self.is_recording = True 

    def request(self, flow: http.HTTPFlow):
        if not self.is_recording: return

        req_body = flow.request.get_text(strict=False) or ""
        
        request_data = {
            "id": flow.id,
            "method": flow.request.method,
            "url": flow.request.pretty_url,
            "status": "...", 
            "time": flow.request.timestamp_start, # Capture start time
            "req_bytes": len(flow.request.raw_content) if flow.request.raw_content else 0,
            "duration": 0,
            "res_bytes": 0,
            "req_headers": dict(flow.request.headers),
            "req_body": req_body,
            "res_headers": {},
            "res_body": ""
        }
        
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.broadcast_to_ui("NEW_REQUEST", request_data))
        except RuntimeError:
            pass

        # 2. IN-APP MAP LOCAL LOGIC
        for rule in self.map_local_rules:
            if rule.get("active") and re.search(rule.get("pattern", ""), flow.request.pretty_url):
                try:
                    # Get the data straight from the Vue UI
                    status_code = int(rule.get("status", 200))
                    body_text = rule.get("body", "").encode('utf-8')
                    
                    # Parse the headers JSON string from Vue
                    headers_dict = {}
                    try:
                        if rule.get("headers"):
                            headers_dict = json.loads(rule.get("headers"))
                    except json.JSONDecodeError:
                        headers_dict = {"Content-Type": "text/plain"}

                    headers_dict["X-Map-Local"] = "Active"

                    # Hijack the response!
                    flow.response = http.Response.make(status_code, body_text, headers_dict)
                    print(f"Mapped via Editor: {flow.request.pretty_url}")
                    return 
                except Exception as e:
                    print(f"Map Local Error: {e}")
                    flow.response = http.Response.make(500, f"Editor Error: {e}".encode())
                    return

    def response(self, flow: http.HTTPFlow):
        if not self.is_recording: return

        flow.response.decode(strict=False) 
        res_body = flow.response.get_text(strict=False) or ""
        
        duration_ms = (flow.response.timestamp_end - flow.request.timestamp_start) * 1000 if flow.response.timestamp_end else 0
        
        update_data = {
            "id": flow.id,
            "status": flow.response.status_code,
            "duration": round(duration_ms),
            "res_bytes": len(flow.response.raw_content) if flow.response.raw_content else 0,
            "res_headers": dict(flow.response.headers),
            "res_body": res_body
        }
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.broadcast_to_ui("UPDATE_REQUEST", update_data))
        except RuntimeError:
            pass

    async def broadcast_to_ui(self, msg_type, data):
        if not self.connected_clients: return
        message = json.dumps({"type": msg_type, "data": data})
        await asyncio.gather(*(client.send(message) for client in self.connected_clients), return_exceptions=True)

    async def websocket_handler(self, websocket):
        self.connected_clients.add(websocket)
        try:
            async for message in websocket:
                payload = json.loads(message)
                if payload.get("type") == "UPDATE_MAP_LOCAL_RULES":
                    self.map_local_rules = payload.get("rules", [])
                # NEW: Listen for the Pause/Play command
                elif payload.get("type") == "TOGGLE_PROXY":
                    self.is_recording = payload.get("is_recording")
        finally:
            self.connected_clients.remove(websocket)

async def run_proxy_and_ws():
    bridge = ProxyUIBridge()
    ws_server = await websockets.serve(bridge.websocket_handler, "127.0.0.1", 8765)
    
    opts = Options(listen_host='127.0.0.1', listen_port=8080)
    m = DumpMaster(opts, with_termlog=False, with_dumper=False)
    m.addons.add(bridge)
    
    await m.run()

def start_backend():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_proxy_and_ws())

if __name__ == '__main__':
    backend_thread = threading.Thread(target=start_backend, daemon=True)
    backend_thread.start()

    html_file = get_asset_path(os.path.join('ui', 'dist', 'index.html'))
    webview.create_window('My Beautiful Proxy', url=f'file://{html_file}', width=1280, height=800)
    webview.start(private_mode=False)