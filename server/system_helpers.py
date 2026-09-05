import os
import sys
import socket
import asyncio

import psutil

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

    if base_name == "emulator":
        android_home = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
        if android_home:
            fallback = os.path.join(android_home, "emulator", exe_name)
            if os.path.exists(fallback): return fallback

        if os.name == "nt":
            fallback = os.path.expandvars(rf"%LOCALAPPDATA%\Android\Sdk\emulator\{exe_name}")
            if os.path.exists(fallback): return fallback

        elif sys.platform == "darwin":
            fallback = os.path.expanduser("~/Library/Android/sdk/emulator/emulator")
            if os.path.exists(fallback): return fallback

        else:
            fallback = os.path.expanduser("~/Android/Sdk/emulator/emulator")
            if os.path.exists(fallback): return fallback

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

async def _watch_local_ip(bridge):
    """Poll the local IP every 5 seconds and notify the UI when it changes."""
    global LOCAL_IP
    while True:
        await asyncio.sleep(5)
        try:
            new_ip = get_local_ip()
            if new_ip != LOCAL_IP:
                LOCAL_IP = new_ip
                print(f"[INFO] Network change detected — new local IP: {LOCAL_IP}")
                ip_onboarding = getattr(bridge, "_ip_onboarding_addon", None)
                if ip_onboarding:
                    ip_onboarding.host = LOCAL_IP
                await bridge.broadcast_to_ui("SYSTEM_INFO", {
                    "ip": LOCAL_IP,
                    "port": bridge.proxy_port,
                    "platform": sys.platform,
                    "mac_proxy_active": bridge.is_mac_proxy_set,
                })
        except Exception as e:
            print(f"[WARN] IP watch error: {e}")

# Cache: ip -> resolved hostname (or None if failed)
_hostname_cache: dict = {}

async def _resolve_hostname_bg(ip: str, proxy_addon):
    """Resolve a hostname for an IP in the background and notify the UI."""
    try:
        loop = asyncio.get_running_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, socket.gethostbyaddr, ip),
            timeout=2.0
        )
        hostname = result[0]
        _hostname_cache[ip] = hostname
    except Exception:
        _hostname_cache[ip] = None
        return
    # Notify frontend so sidebar can update without waiting for next request
    try:
        await proxy_addon.broadcast_to_ui("CLIENT_HOSTNAME_RESOLVED", {"ip": ip, "hostname": hostname})
    except Exception:
        pass
