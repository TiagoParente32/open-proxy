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
def get_executable_path(base_name):
    """Finds the absolute path for an executable across Windows, macOS, and Linux."""
    import shutil
    import os
    import sys

    # Windows requires .exe extensions for reliable manual path checking
    exe_name = f"{base_name}.exe" if os.name == "nt" else base_name

    # 1. Check system PATH first
    path = shutil.which(exe_name) or shutil.which(base_name)
    if path: 
        return path

    # 2. Hardcoded fallbacks for ADB
    if base_name == "adb":
        # Check Android environment variables (Works on all OS)
        android_home = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
        if android_home:
            fallback = os.path.join(android_home, "platform-tools", exe_name)
            if os.path.exists(fallback): return fallback
        
        # Check OS-specific default install locations
        if os.name == "nt": # Windows
            fallback = os.path.expandvars(rf"%LOCALAPPDATA%\Android\Sdk\platform-tools\{exe_name}")
            if os.path.exists(fallback): return fallback
            
        elif sys.platform == "darwin": # macOS
            for f in [
                os.path.expanduser("~/Library/Android/sdk/platform-tools/adb"),
                "/opt/homebrew/bin/adb",
                "/usr/local/bin/adb"
            ]:
                if os.path.exists(f): return f
                
        else: # Linux
            for f in [
                os.path.expanduser("~/Android/Sdk/platform-tools/adb"),
                "/usr/bin/adb",
                "/usr/local/bin/adb"
            ]:
                if os.path.exists(f): return f
                
    # 3. Hardcoded fallbacks for OpenSSL (Mainly for Windows users)
    if base_name == "openssl" and os.name == "nt":
        fallbacks = [
            r"C:\Program Files\Git\usr\bin\openssl.exe",
            r"C:\Program Files\OpenSSL-Win64\bin\openssl.exe",
            r"C:\Program Files (x86)\GnuWin32\bin\openssl.exe"
        ]
        for f in fallbacks:
            if os.path.exists(f): return f
            
        # Give a Windows-specific error if OpenSSL is completely missing
        raise FileNotFoundError("OpenSSL not found. On Windows, please install 'Git for Windows' (which includes OpenSSL) or install OpenSSL directly.")

    raise FileNotFoundError(f"Could not find '{base_name}'. Please ensure it is installed and in your PATH.")

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


class PyWebViewAPI:
    def __init__(self):
        self.window = None

    def save_file(self, filename, content):
        import webview
        import os

        try:
            dialog_type = webview.FileDialog.SAVE if hasattr(webview, 'FileDialog') else webview.SAVE_DIALOG
            safe_dir = os.path.expanduser('~/Desktop')

            result = self.window.create_file_dialog(
                dialog_type,
                directory=safe_dir,
                save_filename=filename
            )

            print(f"[DEBUG] Dialog result: {result}")

            # --- USER CANCEL ---
            if not result or len(result) == 0:
                print("[INFO] User cancelled save dialog")
                return False

            save_path = result[0]

            if isinstance(save_path, tuple):
                save_path = save_path[0]

            # --- 🧠 MACOS BUG HANDLING ---
            if not save_path or save_path == "/" or os.path.isdir(save_path):
                print(f"[WARNING] Invalid path from dialog: {save_path}")

                # ✅ FALLBACK (THIS SAVES YOUR APP)
                fallback_path = os.path.join(safe_dir, filename)

                if not fallback_path.endswith(".json"):
                    fallback_path += ".json"

                with open(fallback_path, 'w', encoding='utf-8') as f:
                    f.write(content)

                print(f"[INFO] Saved via fallback to {fallback_path}")
                return True

            # Ensure extension
            if not save_path.endswith(".json"):
                save_path += ".json"

            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(content)

            print(f"[INFO] Export saved to {save_path}")
            return True

        except Exception as e:
            print(f"[ERROR] API Save File failed: {e}")
            return False
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
                pattern = rule.get("pattern", "")
                
                # 1. Escape the string so dots/slashes are treated as literal characters
                # 2. Convert the escaped asterisk (\*) into a regex catch-all (.*)
                # 3. Anchor it with ^ and $ to enforce an exact match
                strict_regex = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
                
                if rule.get("active") and re.search(strict_regex, flow.request.pretty_url):
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
                        pattern = rule.get("pattern", "")
                        # Escape, convert * to .*, and anchor
                        strict_regex = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
                        
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
                        pattern = rule.get("pattern", "")
                        # Escape, convert * to .*, and anchor
                        strict_regex = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
                        
                        if re.search(strict_regex, flow.request.pretty_url):
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
            # --- DYNAMICALLY RESOLVE PATHS ---
            adb_cmd = get_executable_path("adb")
            openssl_cmd = get_executable_path("openssl")

            await update("check_adb", "start")
            subprocess.run([adb_cmd, "version"], check=True, capture_output=True, text=True)
            await asyncio.sleep(0.5)
            await update("check_adb", "success")

            await update("cert_prepare", "start")
            cert_path = os.path.expanduser("~/.mitmproxy/mitmproxy-ca-cert.pem")
            if not os.path.exists(cert_path):
                await update("cert_prepare", "error", "Certificate not found. Start proxy first!")
                return

            # 1. Get the hash
            hash_proc = subprocess.run([openssl_cmd, "x509", "-inform", "PEM", "-subject_hash_old", "-in", cert_path], capture_output=True, text=True, check=True)
            cert_hash = hash_proc.stdout.splitlines()[0].strip()
            hashed_cert_name = f"{cert_hash}.0"

            # 2. THE FIX: Safely copy the PEM file to the OS Temp directory instead of using OpenSSL to convert/save to the current directory
            import tempfile
            import shutil
            safe_hashed_cert_path = os.path.join(tempfile.gettempdir(), hashed_cert_name)
            shutil.copy(cert_path, safe_hashed_cert_path)
            
            await update("cert_prepare", "success")

            await update("root_emu", "start")
            root_proc = subprocess.run([adb_cmd, "root"], capture_output=True, text=True)
            if root_proc.returncode != 0:
                error_msg = root_proc.stderr.strip() or root_proc.stdout.strip()
                raise Exception(f"adb root failed: {error_msg}")
                
            await asyncio.sleep(1.5)
            await update("root_emu", "success")

            await update("push_cert", "start")
            # 3. Push from the safe temp path
            subprocess.run([adb_cmd, "push", safe_hashed_cert_path, f"/data/misc/user/0/cacerts-added/{hashed_cert_name}"], check=True, capture_output=True, text=True)
            subprocess.run([adb_cmd, "shell", "su", "0", "chmod", "644", f"/data/misc/user/0/cacerts-added/{hashed_cert_name}"], check=True, capture_output=True, text=True)
            
            # 4. Cleanup the temp file safely
            if os.path.exists(safe_hashed_cert_path):
                os.remove(safe_hashed_cert_path)
                
            await update("push_cert", "success")

            await update("set_proxy", "start")
            subprocess.run([adb_cmd, "shell", "settings", "put", "global", "http_proxy", f"10.0.2.2:{self.proxy_port}"], check=True, capture_output=True, text=True)
            await asyncio.sleep(0.5)
            await update("set_proxy", "success")

            await update("done", "success")

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            await update("current_active_step", "error", f"Command failed: {error_msg}")
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
                    
                    def _save_dialog():
                        try:
                            window = webview.windows[0]
                            
                            # 1. Silence the deprecation warning using the new FileDialog Enum
                            # (with a fallback just in case you ever run this on an older pywebview version)
                            dialog_type = webview.FileDialog.SAVE if hasattr(webview, 'FileDialog') else webview.SAVE_DIALOG
                            
                            # 2. Fix the macOS "/" crash by explicitly setting a starting directory
                            safe_dir = os.path.expanduser('~/Desktop')
                            
                            result = window.create_file_dialog(
                                dialog_type, 
                                directory=safe_dir,        # <-- This saves macOS from panicking
                                save_filename=filename
                            )
                            
                            if result and len(result) > 0:
                                save_path = result[0]
                                if isinstance(save_path, tuple): 
                                    save_path = save_path[0]
                                with open(save_path, 'w', encoding='utf-8') as f:
                                    f.write(file_data)
                                print(f"[INFO] Export saved to {save_path}")
                        except Exception as e:
                            print(f"[ERROR] Failed to open save dialog: {e}")

                    threading.Thread(target=_save_dialog, daemon=True).start()

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
# ============================================================================
# 3. ASYNC RUNNERS (Background Threads)
# ============================================================================
async def run_proxy_forever(bridge, proxy_port):
    """Keeps Mitmproxy alive. If it crashes due to a network drop, it re-initializes."""
    while True:
        try:
            print(f"[INFO] Starting Mitmproxy on port {proxy_port}...")
            opts = options.Options(listen_host='0.0.0.0', listen_port=proxy_port)
            master = DumpMaster(opts, with_termlog=False, with_dumper=False)
            master.addons.add(bridge)
            await master.run()
        except asyncio.CancelledError:
            break  # Allow graceful shutdown if the app closes
        except Exception as e:
            print(f"[ERROR] Mitmproxy crashed: {e}. Restarting in 3 seconds...")
            await asyncio.sleep(3)
        finally:
            if 'master' in locals():
                try:
                    master.shutdown()
                except Exception:
                    pass

async def run_ws_forever(bridge):
    """Keeps the WebSocket server alive with Ping/Pong to detect dead sockets."""
    while True:
        try:
            print("[INFO] Starting WebSocket server on port 8765...")
            # ping_interval and ping_timeout are crucial here!
            # They detect if the Mac went to sleep and dropped the connection.
            async with websockets.serve(
                bridge.websocket_handler, 
                "127.0.0.1", 
                8765, 
                ping_interval=20,   # Ping the client every 20s
                ping_timeout=20     # Drop connection if no pong in 20s
            ):
                # Run forever until an exception breaks it
                await asyncio.Future()
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[ERROR] WebSocket server crashed: {e}. Restarting in 3 seconds...")
            await asyncio.sleep(3)

def run_async_loop(bridge, proxy_port):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def supervisor():
        # Run both tasks concurrently. If one fails, the while-loops inside them will restart them.
        await asyncio.gather(
            run_proxy_forever(bridge, proxy_port),
            run_ws_forever(bridge)
        )

    try:
        loop.run_until_complete(supervisor())
    except Exception as e:
        print(f"[FATAL] Supervisor died: {e}")


def on_closed():
    """Triggered when the user closes the UI window."""
    print("[INFO] UI window closed. Terminating OpenProxy...")
    os._exit(0)  # Hard kill to destroy all background threads and release ports instantly

if __name__ == "__main__":
    ACTIVE_PROXY_PORT = get_free_port(9090)
    print(f"Starting OpenProxy on port {ACTIVE_PROXY_PORT}")

    bridge = ProxyUIBridge(proxy_port=ACTIVE_PROXY_PORT)
    
    t = threading.Thread(target=run_async_loop, args=(bridge, ACTIVE_PROXY_PORT), daemon=True)
    t.start()

    html_path = get_resource_path('ui/dist/index.html')
    icon_path = get_resource_path('icon.png')
    
    # --- 1. INSTANTIATE THE API ---
    webview_api = PyWebViewAPI()
    
    window = webview.create_window(
        title='OpenProxy', 
        url=html_path, 
        width=1024, 
        height=720,
        min_size=(1024, 720),
        background_color='#1a1a1b',
        js_api=webview_api  # --- 2. BIND THE API TO THE FRONTEND ---
    )
    
    # --- 3. GIVE THE API ACCESS TO THE WINDOW ---
    webview_api.window = window
    
    def on_closed():
        print("[INFO] UI window closed. Terminating OpenProxy...")
        os._exit(0)
        
    window.events.closed += on_closed
    
    webview.start(private_mode=False, debug=True, icon=icon_path)