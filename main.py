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
import sqlite3
import hashlib
import urllib.request
import websockets
import psutil
import mitmproxy_rs
from PIL import Image
from mitmproxy import http, options
from mitmproxy.tools.dump import DumpMaster
from mitmproxy.proxy.mode_servers import WireGuardServerInstance

APP_VERSION = "1.0.2"
GITHUB_REPO = "TiagoParente32/open-proxy"

# Global refs so background threads can reach the bridge and its event loop
_global_bridge = None
_global_loop   = None

# ============================================================================
# 1. NETWORK & SYSTEM HELPERS
# ============================================================================
def get_executable_path(base_name):
    """Finds the absolute path for an executable across Windows, macOS, and Linux."""
    import shutil
    import os
    import sys

    exe_name = f"{base_name}.exe" if os.name == "nt" else base_name

    path = shutil.which(exe_name) or shutil.which(base_name)
    if path:
        return path

    if base_name == "adb":
        android_home = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
        if android_home:
            fallback = os.path.join(android_home, "platform-tools", exe_name)
            if os.path.exists(fallback): return fallback

        if os.name == "nt":
            fallback = os.path.expandvars(rf"%LOCALAPPDATA%\Android\Sdk\platform-tools\{exe_name}")
            if os.path.exists(fallback): return fallback

        elif sys.platform == "darwin":
            for f in [
                os.path.expanduser("~/Library/Android/sdk/platform-tools/adb"),
                "/opt/homebrew/bin/adb",
                "/usr/local/bin/adb"
            ]:
                if os.path.exists(f): return f

        else:
            for f in [
                os.path.expanduser("~/Android/Sdk/platform-tools/adb"),
                "/usr/bin/adb",
                "/usr/local/bin/adb"
            ]:
                if os.path.exists(f): return f

    if base_name == "openssl" and os.name == "nt":
        fallbacks = [
            r"C:\Program Files\Git\usr\bin\openssl.exe",
            r"C:\Program Files\OpenSSL-Win64\bin\openssl.exe",
            r"C:\Program Files (x86)\GnuWin32\bin\openssl.exe"
        ]
        for f in fallbacks:
            if os.path.exists(f): return f
        raise FileNotFoundError("OpenSSL not found. On Windows, please install 'Git for Windows' (which includes OpenSSL) or install OpenSSL directly.")

    raise FileNotFoundError(f"Could not find '{base_name}'. Please ensure it is installed and in your PATH.")


def get_local_ip():
    """Return the best LAN IP for the host, ignoring VPN and virtual interfaces."""
    # Virtual/tunnel interface name fragments to skip
    SKIP_IFACE = [
        'vbox', 'virtual', 'vmnet', 'host-only', 'virtualbox', 'hyper-v',
        'vpn', 'docker', 'veth', 'tailscale', 'zerotier', 'wsl',
        'tun', 'tap', 'ppp', 'utun', 'wg',
    ]

    try:
        interfaces = psutil.net_if_addrs()

        # Pass 1: prefer private LAN addresses (192.168.x / 10.x) on physical interfaces
        for interface_name, interface_addresses in interfaces.items():
            lname = interface_name.lower()
            if any(v in lname for v in SKIP_IFACE):
                continue
            for address in interface_addresses:
                if address.family == socket.AF_INET:
                    ip = address.address
                    if ip.startswith("192.168.") or ip.startswith("10."):
                        return ip

        # Pass 2: accept any non-loopback/non-APIPA address on non-virtual interfaces
        for interface_name, interface_addresses in interfaces.items():
            lname = interface_name.lower()
            if any(v in lname for v in SKIP_IFACE):
                continue
            for address in interface_addresses:
                if address.family == socket.AF_INET:
                    ip = address.address
                    if not ip.startswith("127.") and not ip.startswith("169.254."):
                        return ip

    except Exception as e:
        print(f"[WARNING] psutil failed: {e}")

    # Last resort: UDP connect trick (may return VPN IP if active, but better than nothing)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        if ip and not ip.startswith('127.'):
            return ip
    except Exception:
        pass
    finally:
        try:
            s.close()
        except Exception:
            pass

    return '127.0.0.1'

def get_free_port(preferred_port=9090):
    """
    Tries the preferred port first. Only scans upward if it's taken.
    This keeps the port stable across restarts as long as nothing else claims it.
    """
    port = preferred_port
    while port <= 65535:
        print(f"Checking port {port}")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('0.0.0.0', port))
                return port
            except OSError:
                port += 1

def get_resource_path(relative_path):
    """ Get the absolute path to a resource. Works for dev and for PyInstaller. """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

LOCAL_IP = get_local_ip()


# ============================================================================
# AUTO-UPDATE HELPERS
# ============================================================================
def _get_app_install_path():
    """Return the Electron app root (the .app bundle on macOS, exe folder on Windows/Linux)."""
    exe = os.path.abspath(sys.executable)
    if sys.platform == 'darwin' and '.app/Contents/' in exe:
        return exe.split('/Contents/')[0]   # /path/to/OpenProxy.app
    if getattr(sys, 'frozen', False):
        # PyInstaller onedir: exe at <electron_root>/resources/backend/OpenProxy-server/
        # Navigate up 3 levels to reach the Electron app root
        return os.path.normpath(os.path.join(os.path.dirname(exe), '..', '..', '..'))
    return os.path.dirname(os.path.abspath(__file__))


def _parse_version(tag):
    """Parse a semver tag like 'v1.2.3' into a comparable tuple."""
    try:
        return tuple(int(x) for x in tag.lstrip('v').split('.'))
    except Exception:
        return (0,)


def check_for_updates():
    """
    Query GitHub Releases API. Returns a dict if a newer version is available, else None.
    { version, current, download_url, release_url }
    """
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        req = urllib.request.Request(url, headers={'User-Agent': f'OpenProxy/{APP_VERSION}'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        latest = data.get('tag_name', '').strip()
        if not latest or _parse_version(latest) <= _parse_version(APP_VERSION):
            return None

        platform_keywords = {
            'darwin': ['macos', 'mac', 'osx', 'darwin'],
            'win32':  ['windows', 'win'],
        }.get(sys.platform, ['linux'])

        download_url = None
        for asset in data.get('assets', []):
            name = asset.get('name', '').lower()
            if name.endswith('.zip') and any(kw in name for kw in platform_keywords):
                download_url = asset['browser_download_url']
                break

        return {
            'version': latest,
            'current': APP_VERSION,
            'download_url': download_url,
            'release_url': f"https://github.com/{GITHUB_REPO}/releases/tag/{latest}",
        }
    except Exception as e:
        print(f"[Update] Check failed: {e}")
        return None


def apply_update(download_url, progress_cb=None):
    """
    Download the release zip, extract it, then launch a helper script that
    swaps the new app over the old one and relaunches.
    progress_cb(pct) is called with 0-100 during download.
    Raises on any error so the caller can surface it to the UI.
    """
    import tempfile, zipfile, shutil, stat

    install_path = _get_app_install_path()
    tmp_dir = tempfile.mkdtemp(prefix='openproxy_update_')

    zip_path = os.path.join(tmp_dir, 'update.zip')
    extract_dir = os.path.join(tmp_dir, 'extracted')
    os.makedirs(extract_dir, exist_ok=True)

    def reporthook(block_num, block_size, total_size):
        if progress_cb and total_size > 0:
            pct = min(100, int(block_num * block_size * 100 / total_size))
            progress_cb(pct)

    urllib.request.urlretrieve(download_url, zip_path, reporthook)
    if progress_cb:
        progress_cb(100)

    if sys.platform == 'darwin':
        subprocess.run(['ditto', '-x', '-k', zip_path, extract_dir], check=True)
    elif sys.platform != 'win32':
        result = subprocess.run(['unzip', '-q', zip_path, '-d', extract_dir])
        if result.returncode != 0:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(extract_dir)
    else:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(extract_dir)

    if sys.platform == 'darwin':
        new_app = next(
            (os.path.join(extract_dir, f) for f in os.listdir(extract_dir) if f.endswith('.app')),
            None
        )
        if not new_app:
            raise FileNotFoundError("No .app bundle found in the downloaded zip")

        app_name = os.path.splitext(os.path.basename(new_app))[0]
        new_support_dir = os.path.join(extract_dir, app_name)

        install_dir = os.path.dirname(install_path)
        old_support_dir = os.path.join(install_dir, app_name)

        log = os.path.join(tmp_dir, 'update.log')
        script = os.path.join(tmp_dir, 'do_update.sh')
        with open(script, 'w') as f:
            support_lines = ""
            if os.path.isdir(new_support_dir):
                support_lines = f"""
rm -rf "{old_support_dir}"
mv -f "{new_support_dir}" "{old_support_dir}"
xattr -r -d com.apple.quarantine "{old_support_dir}" 2>/dev/null || true"""

            f.write(f"""#!/bin/bash
exec >"{log}" 2>&1
set -x
sleep 2
rm -rf "{install_path}"
mv -f "{new_app}" "{install_path}"
xattr -r -d com.apple.quarantine "{install_path}" 2>/dev/null || true{support_lines}
bin=$(defaults read "{install_path}/Contents/Info" CFBundleExecutable 2>/dev/null)
if [ -z "$bin" ]; then bin=$(ls "{install_path}/Contents/MacOS/" | head -1); fi
chmod +x "{install_path}/Contents/MacOS/$bin"
nohup "{install_path}/Contents/MacOS/$bin" &
""")
        os.chmod(script, os.stat(script).st_mode | stat.S_IEXEC)
        subprocess.Popen(['bash', script], close_fds=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    elif sys.platform == 'win32':
        new_dir = next(
            (os.path.join(extract_dir, f) for f in os.listdir(extract_dir)
             if os.path.isdir(os.path.join(extract_dir, f))),
            extract_dir
        )
        exe_name = os.path.basename(sys.executable)
        log = os.path.join(tmp_dir, 'update.log')
        script = os.path.join(tmp_dir, 'do_update.bat')
        with open(script, 'w') as f:
            f.write(f"""@echo off
timeout /t 2 /nobreak >nul
robocopy "{new_dir}" "{install_path}" /E /IS /IT /IM >"{log}" 2>&1
start "" "{os.path.join(install_path, exe_name)}"
""")
        subprocess.Popen(['cmd', '/c', script], close_fds=True,
                         creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS)

    else:
        new_dir = next(
            (os.path.join(extract_dir, f) for f in os.listdir(extract_dir)
             if os.path.isdir(os.path.join(extract_dir, f))),
            extract_dir
        )
        exe_name = os.path.basename(sys.executable)
        log = os.path.join(tmp_dir, 'update.log')
        script = os.path.join(tmp_dir, 'do_update.sh')
        with open(script, 'w') as f:
            f.write(f"""#!/bin/bash
exec >"{log}" 2>&1
set -x
sleep 2
cp -rf "{new_dir}/." "{install_path}/"
chmod +x "{os.path.join(install_path, exe_name)}"
nohup "{os.path.join(install_path, exe_name)}" &
""")
        os.chmod(script, os.stat(script).st_mode | stat.S_IEXEC)
        subprocess.Popen(['bash', script], close_fds=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ============================================================================
# ADB DEVICE HELPERS
# ============================================================================
def list_adb_devices(adb_cmd):
    result = subprocess.run(
        [adb_cmd, "devices", "-l"],
        capture_output=True, text=True
    )
    
    # Debug: print raw output so you can see exactly what adb returns
    print(f"[DEBUG] adb devices output:\n{result.stdout}")
    
    devices = []
    for line in result.stdout.splitlines()[1:]:  # skip header
        line = line.strip()
        if not line:
            continue

        # adb devices -l format:
        # "emulator-5554          device product:sdk_gphone... model:Pixel_6 device:..."
        # serial and state are whitespace-separated, rest is key:value tokens
        parts = line.split()
        if len(parts) < 2:
            continue

        serial = parts[0]
        state = parts[1]

        if state != "device":
            continue

        # Parse key:value tokens from the rest of the line
        info = {}
        for token in parts[2:]:
            if ":" in token:
                k, _, v = token.partition(":")
                info[k] = v

        model = info.get("model", info.get("device", serial))
        device_type = "emulator" if serial.startswith("emulator-") else "device"

        devices.append({
            "serial": serial,
            "model": model.replace("_", " "),
            "type": device_type,
            "state": state
        })

    return devices


# ============================================================================
# IOS SIMULATOR HELPERS  (macOS only)
# ============================================================================
def list_ios_simulators():
    """Returns available iOS simulators via xcrun simctl."""
    result = subprocess.run(
        ["xcrun", "simctl", "list", "devices", "--json"],
        capture_output=True, text=True, timeout=10
    )
    data = json.loads(result.stdout)
    simulators = []
    for runtime, devices in data.get("devices", {}).items():
        if "iOS" not in runtime:
            continue
        runtime_label = (runtime
            .replace("com.apple.CoreSimulator.SimRuntime.", "")
            .replace("-", " "))
        for device in devices:
            if not device.get("isAvailable", True):
                continue
            simulators.append({
                "udid":    device["udid"],
                "name":    device["name"],
                "state":   device.get("state", "Shutdown"),
                "runtime": runtime_label,
            })
    # Sort: booted simulators first
    simulators.sort(key=lambda d: 0 if d["state"] == "Booted" else 1)
    return simulators


# ============================================================================
# MACOS SYSTEM PROXY HELPERS  (macOS only)
# ============================================================================
def get_active_network_services():
    """Returns list of network service names that are currently active (have an IP)."""
    if sys.platform != "darwin":
        return []
    try:
        result = subprocess.run(
            ["networksetup", "-listallnetworkservices"],
            capture_output=True, text=True, timeout=5
        )
        services = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("An asterisk") or line.startswith("*"):
                continue
            # Check if the service has an active IP
            info = subprocess.run(
                ["networksetup", "-getinfo", line],
                capture_output=True, text=True, timeout=5
            )
            for info_line in info.stdout.splitlines():
                if info_line.startswith("IP address:"):
                    ip = info_line.split(":", 1)[1].strip()
                    if ip and ip.lower() != "none":
                        services.append(line)
                    break
        return services
    except Exception:
        return []


def set_macos_proxy(port: int) -> dict:
    """
    Sets HTTP+HTTPS proxy to 127.0.0.1:<port> on all active network services.
    Uses osascript so macOS shows the native admin password dialog.
    Returns {'ok': bool, 'services': [...], 'error': str|None}.
    """
    services = get_active_network_services()
    if not services:
        return {'ok': False, 'services': [], 'error': 'No active network services found.'}

    bypass = "127.0.0.1 localhost ::1 *.local 192.168.0.0/16 10.0.0.0/8 172.16.0.0/12"
    cmds = []
    for svc in services:
        s = svc.replace('"', '\\"')
        cmds.append(f'networksetup -setwebproxy "{s}" 127.0.0.1 {port}')
        cmds.append(f'networksetup -setsecurewebproxy "{s}" 127.0.0.1 {port}')
        cmds.append(f'networksetup -setproxybypassdomains "{s}" {bypass}')

    shell_cmd = " && ".join(cmds)
    script = f'do shell script "{shell_cmd}" with administrator privileges'
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            return {'ok': True, 'services': services, 'error': None}
        err = result.stderr.strip() or result.stdout.strip()
        # User cancelled the password dialog
        if "User cancelled" in err or "-128" in err:
            return {'ok': False, 'services': services, 'error': 'cancelled'}
        return {'ok': False, 'services': services, 'error': err or 'Unknown error'}
    except subprocess.TimeoutExpired:
        return {'ok': False, 'services': services, 'error': 'Operation timed out.'}
    except Exception as e:
        return {'ok': False, 'services': services, 'error': str(e)}


def unset_macos_proxy() -> dict:
    """
    Disables HTTP+HTTPS proxy on all active network services.
    Returns {'ok': bool, 'services': [...], 'error': str|None}.
    """
    services = get_active_network_services()
    if not services:
        return {'ok': True, 'services': [], 'error': None}  # Already off

    cmds = []
    for svc in services:
        s = svc.replace('"', '\\"')
        cmds.append(f'networksetup -setwebproxystate "{s}" off')
        cmds.append(f'networksetup -setsecurewebproxystate "{s}" off')

    shell_cmd = " && ".join(cmds)
    script = f'do shell script "{shell_cmd}" with administrator privileges'
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            return {'ok': True, 'services': services, 'error': None}
        err = result.stderr.strip() or result.stdout.strip()
        if "User cancelled" in err or "-128" in err:
            return {'ok': False, 'services': services, 'error': 'cancelled'}
        return {'ok': False, 'services': services, 'error': err or 'Unknown error'}
    except subprocess.TimeoutExpired:
        return {'ok': False, 'services': services, 'error': 'Operation timed out.'}
    except Exception as e:
        return {'ok': False, 'services': services, 'error': str(e)}




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

        # WireGuard mode
        self.wg_enabled = False
        self.wg_port = 51820
        self._master = None     # set by run_proxy_forever; used for WG restart + inject
        self._last_startup_error = ""   # captured from mitmproxy's log on startup failure
        self.pending_update_info = None  # cached until a client connects

    def add_log(self, entry) -> None:
        """Capture mitmproxy ERROR log entries so we can surface them in the UI."""
        if getattr(entry, 'level', None) == "error":
            self._last_startup_error = getattr(entry, 'msg', str(entry))

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

        request_data = {
            "id": flow.id,
            "client_ip": flow.client_conn.peername[0] if flow.client_conn.peername else "Unknown",
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

        if self.breakpoints_enabled:
            for rule in self.breakpoint_rules:
                if rule.get("active") and rule.get("is_request"):
                    try:
                        pattern = rule.get("pattern", "")
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

        if self.disable_cache:
            flow.response.headers.pop("ETag", None)
            flow.response.headers.pop("Last-Modified", None)
            flow.response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            flow.response.headers["Expires"] = "0"

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

        if self.breakpoints_enabled:
            for rule in self.breakpoint_rules:
                if rule.get("active") and rule.get("is_response"):
                    try:
                        pattern = rule.get("pattern", "")
                        strict_regex = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"

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

        if not hasattr(flow, 'websocket') or not flow.websocket or not flow.websocket.messages:
            return

        latest_msg = flow.websocket.messages[-1]

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

    # -------------------------------------------------------------------------
    # ANDROID SETUP HELPERS
    # -------------------------------------------------------------------------

    async def handle_list_adb_devices(self, ws):
        try:
            adb_cmd = get_executable_path("adb")
            # Run in executor so it doesn't block the event loop
            loop = asyncio.get_running_loop()
            devices = await asyncio.wait_for(
                loop.run_in_executor(None, list_adb_devices, adb_cmd),
                timeout=10.0
            )
            await ws.send(json.dumps({"type": "ADB_DEVICES", "devices": devices}))
        except asyncio.TimeoutError:
            await ws.send(json.dumps({
                "type": "ADB_DEVICES", "devices": [],
                "error": "adb timed out after 10 seconds. Is adb server running?"
            }))
        except FileNotFoundError as e:
            await ws.send(json.dumps({"type": "ADB_DEVICES", "devices": [], "error": str(e)}))
        except Exception as e:
            await ws.send(json.dumps({"type": "ADB_DEVICES", "devices": [], "error": f"Unexpected error: {e}"}))
            
    async def setup_android_device(self, ws, serial: str, device_type: str):
        """
        Installs the mitmproxy cert and sets the proxy on a specific ADB device.
        Uses 10.0.2.2 as the proxy host for emulators, LOCAL_IP for physical devices.
        """
        # Serial flag for all adb commands targeting this specific device
        serial_flag = ["-s", serial]

        # Emulators reach the host machine via the special alias 10.0.2.2.
        # Physical devices need the real LAN IP since they're on the actual network.
        proxy_host = "10.0.2.2" if device_type == "emulator" else LOCAL_IP

        async def update(step_id, status, msg=""):
            await ws.send(json.dumps({
                "type": "SETUP_PROGRESS",
                "step": step_id,
                "status": status,
                "message": msg,
                "serial": serial
            }))

        try:
            adb_cmd = get_executable_path("adb")
            openssl_cmd = get_executable_path("openssl")

            await update("check_adb", "start")
            subprocess.run([adb_cmd, "version"], check=True, capture_output=True, text=True)
            await asyncio.sleep(0.3)
            await update("check_adb", "success")

            await update("cert_prepare", "start")
            cert_path = os.path.expanduser("~/.mitmproxy/mitmproxy-ca-cert.pem")
            if not os.path.exists(cert_path):
                await update("cert_prepare", "error", "Certificate not found. Start proxy first!")
                return

            hash_proc = subprocess.run(
                [openssl_cmd, "x509", "-inform", "PEM", "-subject_hash_old", "-in", cert_path],
                capture_output=True, text=True, check=True
            )
            cert_hash = hash_proc.stdout.splitlines()[0].strip()
            hashed_cert_name = f"{cert_hash}.0"

            import tempfile, shutil
            safe_hashed_cert_path = os.path.join(tempfile.gettempdir(), hashed_cert_name)
            shutil.copy(cert_path, safe_hashed_cert_path)
            await update("cert_prepare", "success")

            # Only emulators support `adb root` (Google Play builds do not).
            if device_type == "emulator":
                await update("root_emu", "start")
                root_proc = subprocess.run(
                    [adb_cmd] + serial_flag + ["root"],
                    capture_output=True, text=True
                )
                if root_proc.returncode != 0:
                    error_msg = root_proc.stderr.strip() or root_proc.stdout.strip()
                    raise Exception(f"adb root failed: {error_msg}")
                await asyncio.sleep(1.5)
                await update("root_emu", "success")
            else:
                # Skip root step for physical devices — signal it as not applicable
                await update("root_emu", "skip")

            await update("push_cert", "start")
            subprocess.run(
                [adb_cmd] + serial_flag + [
                    "push", safe_hashed_cert_path,
                    f"/data/misc/user/0/cacerts-added/{hashed_cert_name}"
                ],
                check=True, capture_output=True, text=True
            )
            subprocess.run(
                [adb_cmd] + serial_flag + [
                    "shell", "su", "0", "chmod", "644",
                    f"/data/misc/user/0/cacerts-added/{hashed_cert_name}"
                ],
                check=True, capture_output=True, text=True
            )

            if os.path.exists(safe_hashed_cert_path):
                os.remove(safe_hashed_cert_path)
            await update("push_cert", "success")

            await update("set_proxy", "start")
            subprocess.run(
                [adb_cmd] + serial_flag + [
                    "shell", "settings", "put", "global",
                    "http_proxy", f"{proxy_host}:{self.proxy_port}"
                ],
                check=True, capture_output=True, text=True
            )
            await asyncio.sleep(0.5)
            await update("set_proxy", "success")

            await update("done", "success")

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            await update("current_active_step", "error", f"Command failed: {error_msg}")
        except Exception as e:
            await update("current_active_step", "error", str(e))

    async def revert_android_device(self, ws, serial: str):
        """Clears the proxy setting and removes the mitmproxy cert from a device."""
        serial_flag = ["-s", serial]

        async def update(step_id, status, msg=""):
            await ws.send(json.dumps({
                "type": "REVERT_PROGRESS",
                "step": step_id,
                "status": status,
                "message": msg,
                "serial": serial
            }))

        try:
            adb_cmd = get_executable_path("adb")
            openssl_cmd = get_executable_path("openssl")

            await update("clear_proxy", "start")
            subprocess.run(
                [adb_cmd] + serial_flag + [
                    "shell", "settings", "delete", "global", "http_proxy"
                ],
                check=True, capture_output=True, text=True
            )
            # Some Android versions also need the explicit reset command
            subprocess.run(
                [adb_cmd] + serial_flag + [
                    "shell", "settings", "put", "global", "http_proxy", ":0"
                ],
                capture_output=True, text=True  # not check=True — fine if this fails
            )
            await asyncio.sleep(0.5)
            await update("clear_proxy", "success")

            await update("remove_cert", "start")
            cert_path = os.path.expanduser("~/.mitmproxy/mitmproxy-ca-cert.pem")
            if os.path.exists(cert_path):
                try:
                    hash_proc = subprocess.run(
                        [openssl_cmd, "x509", "-inform", "PEM", "-subject_hash_old", "-in", cert_path],
                        capture_output=True, text=True, check=True
                    )
                    cert_hash = hash_proc.stdout.splitlines()[0].strip()
                    hashed_cert_name = f"{cert_hash}.0"

                    subprocess.run(
                        [adb_cmd] + serial_flag + [
                            "shell", "su", "0", "rm", "-f",
                            f"/data/misc/user/0/cacerts-added/{hashed_cert_name}"
                        ],
                        capture_output=True, text=True  # not check — device may not have it
                    )
                except Exception as cert_err:
                    print(f"[WARNING] Could not remove cert (may not exist on device): {cert_err}")

            await update("remove_cert", "success")
            await update("done", "success")

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            await update("current_active_step", "error", f"Command failed: {error_msg}")
        except Exception as e:
            await update("current_active_step", "error", str(e))

    # -------------------------------------------------------------------------
    # iOS SIMULATOR SETUP HELPERS  (macOS only)
    # -------------------------------------------------------------------------

    async def handle_list_ios_simulators(self, ws):
        if sys.platform != "darwin":
            await ws.send(json.dumps({
                "type": "IOS_SIMULATORS", "simulators": [],
                "error": "iOS Simulator setup is only available on macOS."
            }))
            return
        try:
            loop = asyncio.get_running_loop()
            simulators = await asyncio.wait_for(
                loop.run_in_executor(None, list_ios_simulators),
                timeout=10.0
            )
            await ws.send(json.dumps({"type": "IOS_SIMULATORS", "simulators": simulators}))
        except asyncio.TimeoutError:
            await ws.send(json.dumps({
                "type": "IOS_SIMULATORS", "simulators": [],
                "error": "xcrun timed out. Is Xcode installed?"
            }))
        except FileNotFoundError:
            await ws.send(json.dumps({
                "type": "IOS_SIMULATORS", "simulators": [],
                "error": "xcrun not found. Please install Xcode."
            }))
        except Exception as e:
            await ws.send(json.dumps({
                "type": "IOS_SIMULATORS", "simulators": [],
                "error": f"Unexpected error: {e}"
            }))

    async def setup_ios_simulator(self, ws, udid: str):
        """Installs the mitmproxy CA cert into a booted iOS Simulator."""
        async def update(step_id, status, msg=""):
            await ws.send(json.dumps({
                "type": "IOS_SETUP_PROGRESS",
                "step": step_id, "status": status,
                "message": msg, "udid": udid
            }))

        try:
            await update("check_xcrun", "start")
            subprocess.run(["xcrun", "--version"], check=True, capture_output=True, text=True)
            await asyncio.sleep(0.3)
            await update("check_xcrun", "success")

            await update("find_cert", "start")
            cert_path = os.path.expanduser("~/.mitmproxy/mitmproxy-ca-cert.pem")
            if not os.path.exists(cert_path):
                await update("find_cert", "error", "Certificate not found. Start the proxy first to generate it.")
                return
            await asyncio.sleep(0.2)
            await update("find_cert", "success")

            await update("install_cert", "start")
            result = subprocess.run(
                ["xcrun", "simctl", "keychain", udid, "add-root-cert", cert_path],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip()
                await update("install_cert", "error", f"simctl failed: {error_msg}")
                return
            await asyncio.sleep(0.5)
            await update("install_cert", "success")

            await update("done", "success")

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            await update("current_active_step", "error", f"Command failed: {error_msg}")
        except Exception as e:
            await update("current_active_step", "error", str(e))

    async def revert_ios_simulator(self, ws, udid: str):
        """Removes the mitmproxy CA cert from an iOS Simulator's TrustStore."""
        async def update(step_id, status, msg=""):
            await ws.send(json.dumps({
                "type": "IOS_REVERT_PROGRESS",
                "step": step_id, "status": status,
                "message": msg, "udid": udid
            }))

        try:
            await update("find_store", "start")
            sim_base = os.path.expanduser(
                f"~/Library/Developer/CoreSimulator/Devices/{udid}"
            )
            candidates = [
                os.path.join(sim_base, "data/private/var/protected/trustd/private/TrustStore.sqlite3"),
                os.path.join(sim_base, "data/Library/Keychains/TrustStore.sqlite3"),
            ]
            trust_store_path = next((p for p in candidates if os.path.isfile(p)), None)
            if not trust_store_path:
                await update("find_store", "error",
                    "TrustStore not found. Boot the simulator at least once first.")
                return
            await asyncio.sleep(0.2)
            await update("find_store", "success")

            await update("remove_cert", "start")
            cert_path = os.path.expanduser("~/.mitmproxy/mitmproxy-ca-cert.pem")
            if not os.path.exists(cert_path):
                await update("remove_cert", "error", "Proxy certificate not found.")
                return

            with open(cert_path, "r") as f:
                pem_data = f.read()
            der_data = ssl.PEM_cert_to_DER_cert(pem_data)

            # Determine hash column (sha1 or sha256) from schema
            conn = sqlite3.connect(trust_store_path)
            try:
                c = conn.cursor()
                row = c.execute(
                    "SELECT sql FROM sqlite_master WHERE name='tsettings'"
                ).fetchone()
                hash_col = "sha256" if row and "sha256" in row[0] else "sha1"

                sha_digest = (hashlib.sha256(der_data).digest()
                              if hash_col == "sha256"
                              else hashlib.sha1(der_data).digest())

                c.execute(
                    f"DELETE FROM tsettings WHERE {hash_col}=?",
                    [sqlite3.Binary(sha_digest)]
                )
                removed = c.rowcount
                conn.commit()
            finally:
                conn.close()

            if removed == 0:
                await update("remove_cert", "error",
                    "Certificate was not found in the trust store (may already be removed).")
                return

            await asyncio.sleep(0.3)
            await update("remove_cert", "success")
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
            await websocket.send(json.dumps({
                "type": "SYSTEM_INFO",
                "data": {"ip": LOCAL_IP, "port": self.proxy_port, "platform": sys.platform}
            }))

            if self.pending_update_info:
                await websocket.send(json.dumps({"type": "UPDATE_AVAILABLE", "data": self.pending_update_info}))
                self.pending_update_info = None

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

                # ---- NEW: List ADB devices ----
                elif payload.get("type") == "LIST_ADB_DEVICES":
                    asyncio.create_task(self.handle_list_adb_devices(websocket))

                # ---- NEW: Setup a specific device (replaces generic SETUP_ANDROID) ----
                elif payload.get("type") == "SETUP_ANDROID_DEVICE":
                    serial = payload.get("serial")
                    device_type = payload.get("device_type", "emulator")
                    if serial:
                        asyncio.create_task(self.setup_android_device(websocket, serial, device_type))

                # ---- LEGACY: kept for backward compatibility ----
                elif payload.get("type") == "SETUP_ANDROID":
                    asyncio.create_task(self.setup_android_device(websocket, "emulator-5554", "emulator"))

                # ---- NEW: Revert a specific device ----
                elif payload.get("type") == "REVERT_ANDROID_DEVICE":
                    serial = payload.get("serial")
                    if serial:
                        asyncio.create_task(self.revert_android_device(websocket, serial))

                # ---- iOS Simulator setup ----
                elif payload.get("type") == "LIST_IOS_SIMULATORS":
                    asyncio.create_task(self.handle_list_ios_simulators(websocket))

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

                elif payload.get("type") == "CHECK_FOR_UPDATES":
                    async def _check():
                        info = await asyncio.get_event_loop().run_in_executor(None, check_for_updates)
                        if info:
                            await websocket.send(json.dumps({"type": "UPDATE_AVAILABLE", "data": info}))
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
# ============================================================================
# 3. ios setup
# ============================================================================
import os, sqlite3, ssl, hashlib, struct, glob, plistlib

SIMULATOR_DIR = os.path.expanduser("~/Library/Developer/CoreSimulator/Devices/")
TRUSTSTORE_PATHS = [
    "/data/private/var/protected/trustd/private/TrustStore.sqlite3",
    "/data/Library/Keychains/TrustStore.sqlite3",
]

def get_cert_der(pem_path):
    with open(pem_path) as f:
        return ssl.PEM_cert_to_DER_cert(f.read())

def get_cert_sha256(der: bytes) -> bytes:
    return hashlib.sha256(der).digest()

def get_cert_subject_asn1(der: bytes) -> bytes:
    """
    Walks the DER-encoded cert to extract the raw Subject field bytes.
    Structure: SEQUENCE { SEQUENCE { [0] version, serial, algo, issuer, validity, SUBJECT, ... } }
    """
    def read_tlv(data, pos):
        tag = data[pos]; pos += 1
        b = data[pos]; pos += 1
        if b & 0x80:
            n = b & 0x7f
            length = int.from_bytes(data[pos:pos+n], 'big'); pos += n
        else:
            length = b
        return tag, data[pos:pos+length], pos+length

    # Unwrap outer SEQUENCE
    _, cert_seq, _ = read_tlv(der, 0)
    # Unwrap tbsCertificate SEQUENCE
    _, tbs, _ = read_tlv(cert_seq, 0)

    pos = 0
    # Skip: [0] version (optional context tag 0xa0), serialNumber, signature, issuer, validity
    for _ in range(5):
        tag, val, pos = read_tlv(tbs, pos)
        if tag == 0xa0:  # version is optional explicit context [0]
            tag, val, pos = read_tlv(tbs, pos)  # serialNumber
            tag, val, pos = read_tlv(tbs, pos)  # signature
            tag, val, pos = read_tlv(tbs, pos)  # issuer
            tag, val, pos = read_tlv(tbs, pos)  # validity
            break

    # Next TLV is subject — we want the raw bytes INCLUDING the tag+length
    subj_start = pos
    tag, val, pos = read_tlv(tbs, pos)
    return tbs[subj_start:pos]

TSET_PLIST = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
    b'"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
    b'<plist version="1.0">\n<array/>\n</plist>\n'
)

def inject_cert_into_truststore(db_path: str, der: bytes):
    sha   = get_cert_sha256(der)
    subj  = get_cert_subject_asn1(der)

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Detect whether this TrustStore uses sha1 or sha256 column
    row = c.execute("SELECT sql FROM sqlite_master WHERE name='tsettings'").fetchone()
    if not row:
        conn.close()
        raise RuntimeError(f"No tsettings table in {db_path}")
    hash_col = "sha256" if "sha256" in row[0] else "sha1"

    existing = c.execute("SELECT COUNT(*) FROM tsettings WHERE subj=?",
                         [sqlite3.Binary(subj)]).fetchone()[0]
    if existing:
        c.execute(f"UPDATE tsettings SET {hash_col}=?, tset=?, data=? WHERE subj=?",
                  [sqlite3.Binary(sha), sqlite3.Binary(TSET_PLIST),
                   sqlite3.Binary(der), sqlite3.Binary(subj)])
    else:
        c.execute(f"INSERT INTO tsettings ({hash_col}, subj, tset, data) VALUES (?,?,?,?)",
                  [sqlite3.Binary(sha), sqlite3.Binary(subj),
                   sqlite3.Binary(TSET_PLIST), sqlite3.Binary(der)])
    conn.commit()
    conn.close()

def _find_truststore_path(udid: str):
    """Returns the TrustStore.sqlite3 path for the given simulator UDID, or None if not found."""
    device_dir = os.path.join(SIMULATOR_DIR, udid)
    for rel_path in TRUSTSTORE_PATHS:
        ts = os.path.join(device_dir, rel_path.lstrip("/"))
        if os.path.isfile(ts):
            return ts
    return None

async def handle_list_ios_simulators(self, ws):
    try:
        sims = list_ios_simulators()
        await ws.send(json.dumps({"type": "IOS_SIMULATORS", "simulators": sims}))
    except Exception as e:
        await ws.send(json.dumps({"type": "IOS_SIMULATORS", "simulators": [], "error": str(e)}))

async def setup_ios_simulator(self, ws, udid: str):
    async def update(step_id, status, msg=""):
        await ws.send(json.dumps({
            "type": "IOS_SIM_PROGRESS", "step": step_id,
            "status": status, "message": msg, "udid": udid
        }))

    try:
        await update("find_cert", "start")
        cert_path = os.path.expanduser("~/.mitmproxy/mitmproxy-ca-cert.pem")
        if not os.path.exists(cert_path):
            await update("find_cert", "error", "Certificate not found. Start proxy first.")
            return
        der = get_cert_der(cert_path)
        await update("find_cert", "success")

        await update("inject_cert", "start")
        truststore_path = _find_truststore_path(udid)
        if not truststore_path:
            await update("inject_cert", "error",
                "TrustStore not found. Ensure the simulator is booted and has been used at least once.")
            return
        await asyncio.get_running_loop().run_in_executor(
            None, inject_cert_into_truststore, truststore_path, der
        )
        await update("inject_cert", "success")
        await update("done", "success")

    except Exception as e:
        await update("inject_cert", "error", str(e))
        
# ============================================================================
# 3. ASYNC RUNNERS (Background Threads)
# ============================================================================
async def run_proxy_forever(bridge, proxy_port):
    """Keeps Mitmproxy alive. If it crashes due to a network drop, it re-initializes."""
    while True:
        bridge._last_startup_error = ""
        try:
            modes = ["regular"]
            if bridge.wg_enabled:
                modes.append(f"wireguard@{bridge.wg_port}")
            print(f"[INFO] Starting Mitmproxy on port {proxy_port}, modes={modes}...")
            opts = options.Options(listen_host='', listen_port=proxy_port)
            opts.update(mode=modes)
            master = DumpMaster(opts, with_termlog=False, with_dumper=False)
            master.addons.add(bridge)
            bridge._master = master
            await master.run()
        except asyncio.CancelledError:
            break
        except SystemExit:
            # mitmproxy's errorcheck addon calls sys.exit(1) when a startup error is logged.
            # Catch it so the while loop can restart the proxy cleanly.
            detail = bridge._last_startup_error or "Unknown startup error."
            print(f"[ERROR] Mitmproxy startup failed: {detail}")
            if bridge.wg_enabled:
                bridge.wg_enabled = False
                try:
                    await bridge.broadcast_to_ui("WG_STATUS", {
                        "status": "error", "enabled": False,
                        "error": f"WireGuard failed to start: {detail}",
                    })
                except Exception:
                    pass
            await asyncio.sleep(3)
        except Exception as e:
            err = str(e)
            print(f"[ERROR] Mitmproxy crashed: {err}. Restarting in 3 seconds...")
            if bridge.wg_enabled:
                bridge.wg_enabled = False
                await bridge.broadcast_to_ui("WG_STATUS", {
                    "status": "error", "enabled": False,
                    "error": f"WireGuard crashed: {err}",
                })
            await asyncio.sleep(3)
        finally:
            bridge._master = None
            if 'master' in locals():
                try:
                    master.shutdown()
                except Exception:
                    pass
            await asyncio.sleep(1.5)

async def run_ws_forever(bridge):
    """Keeps the WebSocket server alive with Ping/Pong to detect dead sockets."""
    while True:
        try:
            print("[INFO] Starting WebSocket server on port 8765...")
            async with websockets.serve(
                bridge.websocket_handler,
                "127.0.0.1",
                8765,
                ping_interval=20,
                ping_timeout=20
            ):
                await asyncio.Future()
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[ERROR] WebSocket server crashed: {e}. Restarting in 3 seconds...")
            await asyncio.sleep(3)

async def _auto_check_update(bridge):
    """Wait for the UI to connect, then check for updates in the background."""
    await asyncio.sleep(8)
    try:
        info = await asyncio.get_event_loop().run_in_executor(None, check_for_updates)
        if info:
            bridge.pending_update_info = info
            await bridge.broadcast_to_ui("UPDATE_AVAILABLE", info)
    except Exception as e:
        print(f"[Update] Auto-check error: {e}")


def run_async_loop(bridge, proxy_port):
    global _global_bridge, _global_loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _global_bridge = bridge
    _global_loop   = loop

    async def supervisor():
        await asyncio.gather(
            run_proxy_forever(bridge, proxy_port),
            run_ws_forever(bridge),
            _auto_check_update(bridge),
        )

    try:
        loop.run_until_complete(supervisor())
    except Exception as e:
        print(f"[FATAL] Supervisor died: {e}")


if __name__ == "__main__":
    ACTIVE_PROXY_PORT = get_free_port(9090)
    print(f"Starting OpenProxy on port {ACTIVE_PROXY_PORT}", flush=True)

    bridge = ProxyUIBridge(proxy_port=ACTIVE_PROXY_PORT)

    t = threading.Thread(target=run_async_loop, args=(bridge, ACTIVE_PROXY_PORT), daemon=True)
    t.start()

    try:
        t.join()
    except KeyboardInterrupt:
        pass