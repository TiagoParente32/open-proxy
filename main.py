import os
import sys
import json
import time
import types
import socket
import asyncio
import re
import base64
import stat
import subprocess
import threading
import signal
import ssl
import sqlite3
import hashlib
import traceback
import uuid
import urllib.request
import websockets
import psutil
import mitmproxy_rs
from PIL import Image
from mitmproxy import http, options
from mitmproxy.tools.dump import DumpMaster
from mitmproxy.proxy.mode_servers import WireGuardServerInstance
from mitmproxy.addons import asgiapp
from mitmproxy.addons.onboardingapp import app as _onboarding_wsgi_app


# this comment is to test if the update is working
def _read_app_version():
    """Read version from package.json so there's a single source of truth."""
    try:
        if getattr(sys, 'frozen', False):
            # PyInstaller: exe is inside <resources>/backend/OpenProxy-server/
            # Two levels up from the exe's dir lands on <resources> itself
            # (same place electron/main.js copies icon.png etc. via extraResources).
            root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(sys.executable)), '..', '..'))
        else:
            root = os.path.dirname(os.path.abspath(__file__))
        version_file = 'version.json' if getattr(sys, 'frozen', False) else 'package.json'
        with open(os.path.join(root, version_file)) as _f:
            return json.load(_f)['version']
    except Exception:
        return "1.0.16"   # fallback — keep in sync if auto-read ever fails

APP_VERSION      = _read_app_version()
APP_PRODUCT_NAME   = "OpenProxy"   # must match build.productName in package.json
APP_LINUX_EXE_NAME = "open-proxy"  # must match package.json "name" (electron-builder uses this for the Linux binary)
GITHUB_REPO      = "TiagoParente32/open-proxy"

OPENPROXY_DATA_DIR = os.path.join(os.path.expanduser("~"), ".openproxy")
SCRIPTS_DIR        = os.path.join(OPENPROXY_DATA_DIR, "scripts")
SCRIPTS_META_FILE  = os.path.join(OPENPROXY_DATA_DIR, "scripts_meta.json")

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
        # Strip trailing .local FQDN noise from mDNS (keep it readable)
        _hostname_cache[ip] = hostname
    except Exception:
        _hostname_cache[ip] = None
        return
    # Notify frontend so sidebar can update without waiting for next request
    try:
        await proxy_addon.broadcast_to_ui("CLIENT_HOSTNAME_RESOLVED", {"ip": ip, "hostname": hostname})
    except Exception:
        pass


# ============================================================================
# AUTO-UPDATE HELPERS
# ============================================================================
def _get_app_install_path():
    """Return the Electron app root (the .app bundle on macOS, AppImage on Linux, exe folder on Windows/Linux tar)."""
    # Linux AppImage: $APPIMAGE is set by the AppImage runtime and points to the
    # actual .AppImage file on disk (not the read-only squashfs mount point).
    if sys.platform not in ('darwin', 'win32') and os.environ.get('APPIMAGE'):
        return os.environ['APPIMAGE']
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


def _get_ssl_context():
    """
    Build an SSL context with a reliable CA bundle for outbound HTTPS requests
    (e.g. the GitHub update check). Some Python installs (Homebrew, python.org
    on macOS, PyInstaller-frozen builds) don't have access to the system CA
    store, which causes:
        [SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate
    Using certifi's bundled CA file avoids that, falling back to the default
    system context if certifi isn't available.
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _friendly_update_error(e):
    """Translate low-level exceptions from check_for_updates() into a message
    that gives the user something actionable, instead of a raw traceback."""
    msg = str(e)
    if 'CERTIFICATE_VERIFY_FAILED' in msg or isinstance(e, ssl.SSLCertVerificationError):
        return (
            "Could not verify GitHub's SSL certificate (missing local root "
            "certificates). Please download the latest version manually from "
            "the Releases page below."
        )
    return msg


def check_for_updates():
    """
    Query GitHub Releases API. Returns a dict if a newer version is available, else None.
    { version, current, download_url, release_url }

    For local testing, set OPENPROXY_UPDATE_TEST_URL to a zip URL and the check
    will immediately return a fake update pointing to that URL, e.g.:
        OPENPROXY_UPDATE_TEST_URL=http://127.0.0.1:9999/update.zip ./OpenProxy.app/...
    """
    test_url = os.environ.get('OPENPROXY_UPDATE_TEST_URL')
    if test_url:
        print(f"[Update] TEST MODE — using override URL: {test_url}")
        return {
            'version': 'v99.9.9',
            'current': APP_VERSION,
            'download_url': test_url,
            'release_url': 'http://127.0.0.1:9999',
        }

    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        req = urllib.request.Request(url, headers={'User-Agent': f'OpenProxy/{APP_VERSION}'})
        with urllib.request.urlopen(req, timeout=10, context=_get_ssl_context()) as resp:
            data = json.loads(resp.read())

        latest = data.get('tag_name', '').strip()
        if not latest or _parse_version(latest) <= _parse_version(APP_VERSION):
            return None

        import platform as _platform
        machine = _platform.machine().lower()
        is_arm  = machine in ('arm64', 'aarch64')

        assets = data.get('assets', [])
        download_url = None

        if sys.platform == 'darwin':
            # electron-builder names: OpenProxy-1.0.0-arm64-mac.zip  /  OpenProxy-1.0.0-mac.zip
            mac_zips = [
                a for a in assets
                if a.get('name', '').lower().endswith('.zip')
                and any(kw in a.get('name', '').lower() for kw in ['mac', 'macos', 'osx', 'darwin'])
            ]
            if is_arm:
                arm_zips = [a for a in mac_zips if 'arm64' in a.get('name', '').lower()]
                chosen = arm_zips or mac_zips   # fall back to universal/x64 if no arm64 asset
            else:
                x64_zips = [a for a in mac_zips if 'arm64' not in a.get('name', '').lower()]
                chosen = x64_zips or mac_zips   # fall back if no explicit x64 asset
            if chosen:
                download_url = chosen[0]['browser_download_url']

        elif sys.platform == 'win32':
            machine_win = _platform.machine().upper()
            is_arm_win  = machine_win in ('ARM64',)
            for asset in assets:
                name = asset.get('name', '').lower()
                if not name.endswith('.zip'):
                    continue
                if not any(kw in name for kw in ['windows', 'win']):
                    continue
                if is_arm_win and 'arm64' not in name:
                    continue
                if not is_arm_win and 'arm64' in name:
                    continue
                download_url = asset['browser_download_url']
                break

        else:  # Linux — pick asset format that matches how the app was installed
            is_appimage_install = bool(os.environ.get('APPIMAGE'))
            _linux_path = _get_app_install_path()
            is_deb_install = (
                not is_appimage_install and
                (_linux_path.startswith('/opt/') or _linux_path.startswith('/usr/'))
            )
            if is_appimage_install:
                preferred = ['.appimage', '.tar.gz', '.zip']
            elif is_deb_install:
                preferred = ['.deb', '.tar.gz', '.zip']
            else:
                preferred = ['.tar.gz', '.zip', '.appimage']
            for ext in preferred:
                for asset in assets:
                    name = asset.get('name', '').lower()
                    if not name.endswith(ext):
                        continue
                    # For .zip, require 'linux' keyword to avoid picking up Windows/macOS zips.
                    # .tar.gz and .appimage are Linux-only formats so no keyword filter needed.
                    if ext == '.zip' and 'linux' not in name:
                        continue
                    # Architecture match
                    if is_arm and 'arm64' not in name and 'aarch64' not in name:
                        continue
                    if not is_arm and ('arm64' in name or 'aarch64' in name):
                        continue
                    download_url = asset['browser_download_url']
                    break
                if download_url:
                    break

        return {
            'version': latest,
            'current': APP_VERSION,
            'download_url': download_url,
            'release_url': f"https://github.com/{GITHUB_REPO}/releases/tag/{latest}",
        }
    except Exception as e:
        # Re-raise so callers can tell "check failed" apart from "no update
        # available" instead of both silently resolving to no-update.
        print(f"[Update] Check failed: {e}")
        raise


def _launch_linux_script(script, needs_elevation):
    """Launch a bash update script, escalating via pkexec if the install path needs root.

    For elevated installs we use a two-step approach:
      1. A tiny 'launcher' script that pkexec runs *synchronously* (subprocess.run blocks).
         The launcher immediately backgrounds the real update worker and exits.
      2. subprocess.run() returns only after the user authenticates — so UPDATE_READY
         (and the subsequent app quit) happens *after* the password dialog is dismissed,
         not before.  The real worker continues running as root in the background.
    """
    if needs_elevation:
        pkexec = subprocess.run(['which', 'pkexec'], capture_output=True, text=True).stdout.strip()
        if not pkexec:
            raise PermissionError(
                "The install location requires elevated privileges but pkexec was not found. "
                "Please download the new version manually from GitHub and reinstall."
            )

        # Tiny launcher: backgrounds the real script and exits immediately so
        # pkexec (and our blocking subprocess.run) can return as soon as
        # authentication succeeds — well before the app window closes.
        launcher = script + '.launcher.sh'
        with open(launcher, 'w') as f:
            f.write(f'#!/bin/bash\nnohup bash "{script}" >/dev/null 2>&1 &\n')
        os.chmod(launcher, os.stat(launcher).st_mode | stat.S_IEXEC)

        # Block until the user authenticates.  Raises if cancelled/failed.
        result = subprocess.run([pkexec, 'bash', launcher],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode != 0:
            raise PermissionError("Elevation was cancelled or authentication failed.")
    else:
        subprocess.Popen(['bash', script], close_fds=True,
                         start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def apply_update(download_url, progress_cb=None):
    """
    Download the release zip, extract it, then launch a helper script that
    swaps the new app over the old one and relaunches.
    progress_cb(pct) is called with 0-100 during download.
    Raises on any error so the caller can surface it to the UI.
    """
    import tempfile, zipfile, shutil, stat

    install_path = _get_app_install_path()

    # Check write access early; on Linux we can escalate via pkexec if needed.
    # macOS checks the parent dir (we need to replace the .app bundle itself).
    check_path = os.path.dirname(install_path) if sys.platform == 'darwin' else install_path
    needs_elevation = sys.platform not in ('darwin', 'win32') and not os.access(check_path, os.W_OK)

    tmp_dir = tempfile.mkdtemp(prefix='openproxy_update_')

    url_path = download_url.split('?')[0].lower()
    if url_path.endswith('.tar.gz'):
        ext = '.tar.gz'
    else:
        ext = os.path.splitext(url_path)[1]
    dl_path = os.path.join(tmp_dir, f'update{ext}')
    extract_dir = os.path.join(tmp_dir, 'extracted')
    os.makedirs(extract_dir, exist_ok=True)

    # Not urllib.request.urlretrieve(): it uses the default opener (no certifi
    # CA bundle — the same CERTIFICATE_VERIFY_FAILED risk check_for_updates()
    # was fixed for) and has no timeout, so a stalled connection would hang
    # the download forever with the UI stuck on "Downloading Update".
    req = urllib.request.Request(download_url, headers={'User-Agent': f'OpenProxy/{APP_VERSION}'})
    with urllib.request.urlopen(req, timeout=30, context=_get_ssl_context()) as resp:
        total_size = int(resp.headers.get('Content-Length', 0))
        downloaded = 0
        with open(dl_path, 'wb') as out:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                out.write(chunk)
                downloaded += len(chunk)
                if progress_cb and total_size > 0:
                    progress_cb(min(100, int(downloaded * 100 / total_size)))
    if progress_cb:
        progress_cb(100)

    # ── Linux AppImage: single executable, no extraction needed ─────────────
    if sys.platform not in ('darwin', 'win32'):
        log = os.path.join(tmp_dir, 'update.log')
        script = os.path.join(tmp_dir, 'do_update.sh')

        # ============================================================
        # APPIMAGE UPDATES
        # ============================================================

        if dl_path.lower().endswith('.appimage'):

            needs_elevation = not os.access(
                os.path.dirname(install_path),
                os.W_OK
            )

            with open(script, 'w') as f:
                f.write(f"""#!/bin/bash
    exec > "{log}" 2>&1

    set -e
    set -x

    # Wait for the running AppImage (and backend) to fully exit (up to 15s)
    # instead of a blind sleep, so we do not overwrite it out from under
    # itself. Match on the install path rather than a process name, since we
    # cannot know the AppImage's internal binary name ahead of time.
    for i in $(seq 1 15); do
      if ! pgrep -f "{install_path}" > /dev/null 2>&1 && ! pgrep -f "OpenProxy-server" > /dev/null 2>&1; then
        break
      fi
      echo "Waiting for app to exit... ($i/15)"
      sleep 1
    done
    sleep 1

    APP="{install_path}"
    NEW_APP="{dl_path}"

    echo "Replacing AppImage..."

    chmod +x "$NEW_APP"

    mv -f "$NEW_APP" "$APP"

    chmod +x "$APP"

    echo "AppImage updated successfully."

    exit 0
    """)

            os.chmod(script, os.stat(script).st_mode | stat.S_IEXEC)

            _launch_linux_script(script, needs_elevation)
            return

        # ============================================================
        # DEB PACKAGE UPDATES
        # ============================================================

        elif dl_path.lower().endswith('.deb'):

            # .deb ALWAYS requires elevation
            needs_elevation = True

            with open(script, 'w') as f:
                f.write(f"""#!/bin/bash
    exec > "{log}" 2>&1

    set -e
    set -x

    # Wait for the app to fully exit (up to 15s) instead of a blind sleep, so
    # dpkg does not hit "text file busy" trying to overwrite a running binary.
    for i in $(seq 1 15); do
      if ! pgrep -f "{APP_LINUX_EXE_NAME}" > /dev/null 2>&1 && ! pgrep -f "OpenProxy-server" > /dev/null 2>&1; then
        break
      fi
      echo "Waiting for app to exit... ($i/15)"
      sleep 1
    done
    sleep 1

    DEB="{dl_path}"

    echo "Installing DEB package..."

    dpkg -i "$DEB" || apt-get install -f -y

    echo "DEB installed successfully."

    exit 0
    """)

            os.chmod(script, os.stat(script).st_mode | stat.S_IEXEC)

            _launch_linux_script(script, needs_elevation)
            return

        # ============================================================
        # ARCHIVE UPDATES (.tar.gz / .zip)
        # ============================================================

        else:

            # --------------------------------------------------------
            # Extract archive
            # --------------------------------------------------------

            if dl_path.endswith('.tar.gz'):
                subprocess.run(
                    ['tar', '-xzf', dl_path, '-C', extract_dir],
                    check=True
                )

            elif dl_path.endswith('.zip'):
                result = subprocess.run(
                    ['unzip', '-q', dl_path, '-d', extract_dir]
                )

                if result.returncode != 0:
                    with zipfile.ZipFile(dl_path, 'r') as zf:
                        zf.extractall(extract_dir)

            else:
                raise RuntimeError(
                    f"Unsupported Linux update format: {dl_path}"
                )

            # --------------------------------------------------------
            # Find extracted app dir
            # --------------------------------------------------------

            extracted_items = [
                os.path.join(extract_dir, f)
                for f in os.listdir(extract_dir)
            ]

            new_dir = next(
                (p for p in extracted_items if os.path.isdir(p)),
                extract_dir
            )

            # Verify the extracted build has actual contents before we touch
            # the installed app — a truncated/corrupt download should fail
            # loudly here, not after the old install has already been moved aside.
            if not os.path.isfile(os.path.join(new_dir, APP_LINUX_EXE_NAME)):
                raise RuntimeError(
                    f"Downloaded update appears empty or corrupt (missing {APP_LINUX_EXE_NAME}): {new_dir}"
                )

            executable_path = os.path.join(
                install_path,
                APP_LINUX_EXE_NAME
            )
            backup_path = install_path + '.old'

            needs_elevation = not os.access(
                install_path,
                os.W_OK
            )

            with open(script, 'w') as f:
                f.write(f"""#!/bin/bash
    exec > "{log}" 2>&1

    set -e
    set -x

    # Restore the previous install if anything below fails after we have
    # moved it aside — this runs detached, after the app has already quit,
    # so a mid-swap failure would otherwise leave nothing to launch and no
    # way for the user to find out until they try to open the app.
    trap 'echo "Update failed - restoring previous version..."; if [ -e "{backup_path}" ] && [ ! -e "{install_path}" ]; then mv -f "{backup_path}" "{install_path}"; fi' ERR

    # Wait for the app to fully exit (up to 15s) instead of a blind sleep, so
    # we do not swap files out from under a still-running process. Use -f
    # (matches full cmdline) since Linux truncates /proc comm names at 15
    # chars and "OpenProxy-server" is 16.
    for i in $(seq 1 15); do
      if ! pgrep -f "{APP_LINUX_EXE_NAME}" > /dev/null 2>&1 && ! pgrep -f "OpenProxy-server" > /dev/null 2>&1; then
        break
      fi
      echo "Waiting for app to exit... ($i/15)"
      sleep 1
    done
    sleep 1

    SRC="{new_dir}"
    DEST="{install_path}"

    echo "Swapping in updated files..."

    # Rename (not merge-copy) so a partially-updated directory can never be
    # left in place: either DEST ends up fully new, or the trap above puts
    # the fully-old version back.
    rm -rf "{backup_path}"
    if [ -e "$DEST" ]; then
      mv -f "$DEST" "{backup_path}"
    fi
    mv -f "$SRC" "$DEST"

    echo "Fixing executable permissions..."

    chmod +x "{executable_path}"

    rm -rf "{backup_path}"

    echo "Files updated successfully."

    exit 0
    """)

            os.chmod(script, os.stat(script).st_mode | stat.S_IEXEC)

            _launch_linux_script(script, needs_elevation)
            return

    # ── All other formats: extract the archive first ─────────────────────────
    if sys.platform == 'darwin':
        subprocess.run(['ditto', '-x', '-k', dl_path, extract_dir], check=True)
    else:
        with zipfile.ZipFile(dl_path, 'r') as zf:
            zf.extractall(extract_dir)

    if sys.platform == 'darwin':
        new_app = next(
            (os.path.join(extract_dir, f) for f in os.listdir(extract_dir) if f.endswith('.app')),
            None
        )
        if not new_app:
            raise FileNotFoundError("No .app bundle found in the downloaded zip")

        # Verify the extracted bundle has actual contents before we touch the installed app.
        new_app_macos = os.path.join(new_app, 'Contents', 'MacOS')
        if not os.path.isdir(new_app_macos) or not os.listdir(new_app_macos):
            raise RuntimeError(
                f"Downloaded .app bundle appears empty or corrupt (missing Contents/MacOS): {new_app}"
            )

        app_name = os.path.splitext(os.path.basename(new_app))[0]
        new_support_dir = os.path.join(extract_dir, app_name)

        install_dir = os.path.dirname(install_path)
        old_support_dir = os.path.join(install_dir, app_name)
        backup_path = install_path + '.old'

        log = os.path.join(os.path.expanduser("~"), ".openproxy", "update.log")
        script = os.path.join(tmp_dir, 'do_update.sh')
        with open(script, 'w') as f:
            support_lines = ""
            if os.path.isdir(new_support_dir):
                support_lines = f"""
rm -rf "{old_support_dir}"
mv -f "{new_support_dir}" "{old_support_dir}"
xattr -cr "{old_support_dir}" 2>/dev/null || true"""

            f.write(f"""#!/bin/bash
exec >"{log}" 2>&1
set -e
set -x

# If anything below fails after the old app has been moved aside, put it back
# and relaunch it instead of silently leaving the user with no app at all —
# this script runs detached, after the app has already quit, so a mid-swap
# failure would otherwise be invisible until the user tries to open the app.
trap 'echo "Update failed - restoring previous version..."; if [ -e "{backup_path}" ] && [ ! -e "{install_path}" ]; then mv -f "{backup_path}" "{install_path}"; fi; if [ -e "{install_path}" ]; then open -n "{install_path}"; fi' ERR

# Wait for the app process to fully exit (up to 15 s) instead of a blind sleep.
# This covers cases where Spotlight/Finder holds the .app directory open —
# a plain rm -rf in that state removes the contents but leaves an empty dir,
# then mv puts the new bundle *inside* it instead of replacing it.
for i in $(seq 1 15); do
  if ! pgrep -x "OpenProxy" > /dev/null 2>&1; then
    break
  fi
  echo "Waiting for app to exit... ($i/15)"
  sleep 1
done
sleep 1

# Rename old app to a backup — avoids rm -rf leaving a locked empty dir behind.
# mv is an atomic rename so the destination is always fully absent before we place the new bundle.
if [ -e "{install_path}" ]; then
  rm -rf "{backup_path}"
  mv -f "{install_path}" "{backup_path}"
fi

# Move new app into place — destination no longer exists so mv does a rename, not a move-inside.
mv -f "{new_app}" "{install_path}"

# Clear ALL extended attributes (not just quarantine) — consistent with what
# Electron does at startup and required on macOS Sonoma/Sequoia where other
# xattrs (e.g. com.apple.macl) can silently block Gatekeeper from launching.
xattr -cr "{install_path}" 2>/dev/null || true{support_lines}
rm -rf "{backup_path}"

open -n "{install_path}"
""")
        os.chmod(script, os.stat(script).st_mode | stat.S_IEXEC)
        # start_new_session=True puts the script in its own process group so it
        # is fully independent of Python — survives Python being killed by Electron.
        subprocess.Popen(['bash', script], close_fds=True,
                         start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    elif sys.platform == 'win32':
        exe_name = APP_PRODUCT_NAME + '.exe'

        # electron-builder zips are usually flat
        if os.path.isfile(os.path.join(extract_dir, exe_name)):
            new_dir = extract_dir
        else:
            new_dir = next(
                (
                    os.path.join(extract_dir, f)
                    for f in os.listdir(extract_dir)
                    if os.path.isdir(os.path.join(extract_dir, f))
                ),
                extract_dir
            )

        # Verify the extracted build has actual contents before we touch the
        # installed app — a truncated/corrupt download should fail loudly
        # here, not after the old install has already been moved aside.
        if not os.path.isfile(os.path.join(new_dir, exe_name)):
            raise RuntimeError(
                f"Downloaded update appears empty or corrupt (missing {exe_name}): {new_dir}"
            )

        log = os.path.join(tmp_dir, 'update.log')
        script = os.path.join(tmp_dir, 'do_update.ps1')

        exe_path = os.path.join(install_path, exe_name)
        backup_path = install_path + '.old'

        with open(script, 'w', encoding='utf-8') as f:
            f.write(f'''
    $ErrorActionPreference = "Stop"

    Start-Transcript -Path "{log}" -Append

    # This script's own process inherits its working directory from the Python
    # backend that spawned it, which Electron launches with cwd = <install>\\resources
    # — i.e. *inside* the install folder we're about to rename. Windows refuses
    # to rename/move a directory while any process (including this one) has it
    # or a subfolder of it as its current directory, so Move-Item below would
    # fail with a sharing violation unless we step out of it first.
    Set-Location $env:SystemRoot

    # Wait for the app (and backend) to fully exit (up to 30s) instead of a
    # blind sleep. A locked OpenProxy-server.exe/DLL turns the swap below into
    # a partial update, since Move-Item aborts mid-copy with $ErrorActionPreference
    # set to Stop.
    Write-Host "Waiting for app to exit..."
    for ($i = 0; $i -lt 30; $i++) {{
        $proc = Get-Process -Name "OpenProxy-server","OpenProxy" -ErrorAction SilentlyContinue
        if (-not $proc) {{ break }}
        Write-Host "Waiting for app to exit... ($i/30)"
        Start-Sleep -Seconds 1
    }}
    Get-Process -Name "OpenProxy-server","OpenProxy" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1

    $source = "{new_dir}"
    $dest = "{install_path}"
    $backup = "{backup_path}"

    # Swap by renaming directories instead of copying files into a live tree.
    # A directory rename doesn't require every file inside it to be unlocked
    # (unlike overwriting each file in place), and if anything goes wrong we
    # still have the old install under $backup to restore instead of being
    # left with a half-old/half-new app.
    try {{
        if (Test-Path $backup) {{ Remove-Item $backup -Recurse -Force }}
        if (Test-Path $dest) {{ Move-Item $dest $backup -Force }}
        Move-Item $source $dest -Force
        Remove-Item $backup -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "Update applied successfully."
    }} catch {{
        Write-Host "Update failed: $_"
        if ((Test-Path $backup) -and (-not (Test-Path $dest))) {{
            Write-Host "Restoring previous version..."
            Move-Item $backup $dest -Force
        }}
        Start-Process "{exe_path}"
        Stop-Transcript
        exit 1
    }}

    Write-Host "Launching app..."

    Start-Process "{exe_path}"

    Stop-Transcript
    ''')

        subprocess.Popen(
            [
                'powershell',
                '-NoProfile',
                '-ExecutionPolicy', 'Bypass',
                '-File', script
            ],
            # Without an explicit cwd, Popen inherits ours (resourcesPath, inside
            # install_path) — see the Set-Location note in the script above.
            cwd=tmp_dir,
            # CREATE_BREAKAWAY_FROM_JOB is essential here: Electron/Chromium puts
            # every process it spawns (this Python backend) into a Windows Job
            # Object with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, and child processes
            # inherit that same job by default. When the UI tells Electron to
            # quit after APPLY_UPDATE, Electron kills the Python process — which
            # also force-kills this "detached" PowerShell script (and everything
            # else in the job tree) before it can swap files and relaunch the
            # app, since it's still part of that same job. Without breaking away,
            # the update silently disappears: app closes and never reopens.
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_BREAKAWAY_FROM_JOB,
            close_fds=True
        )


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


def list_avds(emulator_cmd):
    """Returns the names of all configured AVDs (running or not) via `emulator -list-avds`."""
    result = subprocess.run(
        [emulator_cmd, "-list-avds"],
        capture_output=True, text=True, timeout=10
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def get_avd_name_for_serial(adb_cmd, serial):
    """Returns the AVD name backing a running emulator serial, or None if it can't be determined."""
    try:
        result = subprocess.run(
            [adb_cmd, "-s", serial, "emu", "avd", "name"],
            capture_output=True, text=True, timeout=5
        )
        # Output is the AVD name on the first line, "OK" on the second.
        lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
        return lines[0] if lines else None
    except Exception:
        return None


# ============================================================================
# IOS SIMULATOR HELPERS  (macOS only)
# ============================================================================
def list_ios_simulators():
    """Returns available iOS simulators via xcrun simctl."""
    result = subprocess.run(
        ["xcrun", "simctl", "list", "devices", "--json"],
        capture_output=True, text=True, timeout=10
    )
    if not result.stdout.strip():
        # simctl prints nothing (instead of an empty devices list) when no iOS
        # runtime is installed — treat that as "no simulators", not a crash.
        return []
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
    """Returns all enabled (non-asterisk) network service names."""
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
            services.append(line)
        return services
    except Exception:
        return []


SUDOERS_PATH = '/etc/sudoers.d/openproxy'
NETWORKSETUP  = '/usr/sbin/networksetup'
SECURITY_BIN  = '/usr/bin/security'
MACOS_CERT_PATH = os.path.expanduser("~/.mitmproxy/mitmproxy-ca-cert.pem")
MACOS_TRUST_CMD = [
    SECURITY_BIN, 'add-trusted-cert', '-d', '-r', 'trustRoot',
    '-k', '/Library/Keychains/System.keychain', MACOS_CERT_PATH,
]

def _sudoers_entry_for_user(username: str) -> str:
    return (
        f'{username} ALL=(root) NOPASSWD: {NETWORKSETUP}\n'
        f'{username} ALL=(root) NOPASSWD: {" ".join(MACOS_TRUST_CMD)}\n'
    )

def _sudoers_ok() -> bool:
    """
    Return True if both networksetup and the cert-trust command are passwordless.
    Checks for SECURITY_BIN specifically (not just 'add-trusted-cert') so a stale
    sudoers file from before a SECURITY_BIN path fix is detected as stale and
    regenerated, rather than silently treated as already correct.
    """
    try:
        r = subprocess.run(['sudo', '-n', '-l'], capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            return False
        return NETWORKSETUP in r.stdout and SECURITY_BIN in r.stdout and 'add-trusted-cert' in r.stdout
    except Exception:
        return False

def ensure_networksetup_sudoers() -> dict:
    """
    Installs /etc/sudoers.d/openproxy so networksetup can be called via
    'sudo -n' without a password prompt.  Asks for the admin password exactly
    once via osascript; subsequent calls are silent.
    Returns {'ok': bool, 'already_installed': bool, 'error': str|None}.
    """
    if _sudoers_ok():
        return {'ok': True, 'already_installed': True, 'error': None}

    username = os.environ.get('USER') or os.environ.get('LOGNAME') or ''
    if not username:
        return {'ok': False, 'already_installed': False, 'error': 'Cannot determine current username.'}

    entry   = _sudoers_entry_for_user(username)
    tmp     = '/tmp/openproxy-sudoers-tmp'
    # Write to tmp, validate with visudo -c, then install with correct permissions.
    shell_cmd = (
        f"printf '%s' '{entry}' > {tmp} && "
        f"/usr/sbin/visudo -c -f {tmp} && "
        f"cp {tmp} {SUDOERS_PATH} && "
        f"chmod 0440 {SUDOERS_PATH} && "
        f"rm -f {tmp}"
    )
    as_string = shell_cmd.replace('\\', '\\\\').replace('"', '\\"')
    script = f'do shell script "{as_string}" with administrator privileges'
    try:
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0 and _sudoers_ok():
            print('[Proxy] Passwordless networksetup sudoers entry installed.')
            return {'ok': True, 'already_installed': False, 'error': None}
        err = result.stderr.strip() or result.stdout.strip()
        if 'User cancelled' in err or '-128' in err:
            return {'ok': False, 'already_installed': False, 'error': 'cancelled'}
        return {'ok': False, 'already_installed': False, 'error': err or 'Unknown error'}
    except subprocess.TimeoutExpired:
        return {'ok': False, 'already_installed': False, 'error': 'Operation timed out.'}
    except Exception as e:
        return {'ok': False, 'already_installed': False, 'error': str(e)}


def is_cert_trusted_macos() -> bool:
    """
    Checks whether the mitmproxy CA is actually trusted — not just present in the
    keychain. `find-certificate` only checks presence, so a cert explicitly set to
    "Never Trust" in Keychain Access would still show up as "found". `verify-cert`
    runs the real trust evaluation and correctly respects that override.
    """
    if not os.path.exists(MACOS_CERT_PATH):
        return False
    try:
        r = subprocess.run(
            ['security', 'verify-cert', '-c', MACOS_CERT_PATH],
            capture_output=True, timeout=5
        )
        return r.returncode == 0
    except Exception:
        return False


def trust_cert_macos() -> dict:
    """Adds the mitmproxy CA cert to the System keychain as a trusted root."""
    if not os.path.exists(MACOS_CERT_PATH):
        return {'ok': False, 'error': 'Certificate not found. Start the proxy first to generate it.'}
    if is_cert_trusted_macos():
        return {'ok': True, 'error': None}
    setup = ensure_networksetup_sudoers()
    if not setup['ok']:
        return {'ok': False, 'error': setup['error']}
    try:
        r = subprocess.run(['sudo', '-n'] + MACOS_TRUST_CMD, capture_output=True, text=True, timeout=15)
        if r.returncode == 0:
            return {'ok': True, 'error': None}
        return {'ok': False, 'error': r.stderr.strip() or r.stdout.strip() or 'security add-trusted-cert failed'}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


# ============================================================================
# WINDOWS CERT TRUST HELPERS
# ============================================================================
WINDOWS_CERT_PATH = os.path.expanduser("~/.mitmproxy/mitmproxy-ca-cert.cer")

def is_cert_trusted_windows() -> bool:
    """Checks whether the mitmproxy CA is already in the current user's Root store."""
    try:
        certutil = get_executable_path("certutil")
    except FileNotFoundError:
        return False
    try:
        r = subprocess.run([certutil, '-user', '-store', 'Root'], capture_output=True, text=True, timeout=10)
        return 'mitmproxy' in r.stdout
    except Exception:
        return False


def trust_cert_windows() -> dict:
    """
    Adds the mitmproxy CA cert to the current user's Trusted Root store via certutil.
    Uses '-user' so this writes to HKCU, not the machine store — no UAC/admin
    elevation needed, and Chrome/Edge (which read the Windows cert store) pick it up.
    """
    if not os.path.exists(WINDOWS_CERT_PATH):
        return {'ok': False, 'error': 'Certificate not found. Start the proxy first to generate it.'}
    if is_cert_trusted_windows():
        return {'ok': True, 'error': None}
    try:
        certutil = get_executable_path("certutil")
    except FileNotFoundError as e:
        return {'ok': False, 'error': str(e)}
    try:
        r = subprocess.run(
            [certutil, '-user', '-addstore', '-f', 'Root', WINDOWS_CERT_PATH],
            capture_output=True, text=True, timeout=15
        )
        if r.returncode == 0:
            return {'ok': True, 'error': None}
        return {'ok': False, 'error': r.stderr.strip() or r.stdout.strip() or 'certutil failed'}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


# ============================================================================
# LINUX CERT TRUST HELPERS
# ============================================================================
LINUX_CERT_PATH   = os.path.expanduser("~/.mitmproxy/mitmproxy-ca-cert.pem")
LINUX_DEBIAN_DEST = '/usr/local/share/ca-certificates/openproxy-mitmproxy.crt'
LINUX_RHEL_DEST   = '/etc/pki/ca-trust/source/anchors/openproxy-mitmproxy.pem'

def is_cert_trusted_linux() -> bool:
    """Best-effort check: does our marker file already exist in a known system trust dir?"""
    return os.path.exists(LINUX_DEBIAN_DEST) or os.path.exists(LINUX_RHEL_DEST)


def trust_cert_linux() -> dict:
    """
    Adds the mitmproxy CA cert to the Linux system trust store (covers curl/wget and
    most Chromium-based browsers, depending on distro). Firefox keeps its own
    separate per-profile NSS cert database and isn't covered by this.
    Requires a graphical polkit agent for the 'pkexec' admin prompt.
    """
    import shutil

    if not os.path.exists(LINUX_CERT_PATH):
        return {'ok': False, 'error': 'Certificate not found. Start the proxy first to generate it.'}
    if is_cert_trusted_linux():
        return {'ok': True, 'error': None}

    if shutil.which('update-ca-certificates'):
        dest = LINUX_DEBIAN_DEST
        cmd = f"mkdir -p '{os.path.dirname(dest)}' && cp '{LINUX_CERT_PATH}' '{dest}' && update-ca-certificates"
    elif shutil.which('update-ca-trust'):
        dest = LINUX_RHEL_DEST
        cmd = f"mkdir -p '{os.path.dirname(dest)}' && cp '{LINUX_CERT_PATH}' '{dest}' && update-ca-trust extract"
    else:
        return {'ok': False, 'error': "No supported system trust store tool found (expected 'update-ca-certificates' or 'update-ca-trust')."}

    pkexec = shutil.which('pkexec')
    if not pkexec:
        return {'ok': False, 'error': "'pkexec' not found — can't request admin privileges graphically. Trust the certificate manually instead."}

    try:
        r = subprocess.run([pkexec, 'bash', '-c', cmd], capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            return {'ok': True, 'error': None}
        err = r.stderr.strip() or r.stdout.strip()
        if r.returncode == 126 or 'dismissed' in err.lower() or 'not authorized' in err.lower():
            return {'ok': False, 'error': 'cancelled'}
        return {'ok': False, 'error': err or 'Failed to update the system trust store.'}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def set_macos_proxy(port: int) -> dict:
    """
    Sets HTTP+HTTPS proxy to 127.0.0.1:<port> on all active network services.
    Installs a sudoers entry on first use so subsequent calls need no password.
    Returns {'ok': bool, 'services': [...], 'error': str|None}.
    """
    services = get_active_network_services()
    if not services:
        return {'ok': False, 'services': [], 'error': 'No active network services found.'}

    # Ensure passwordless access is set up (one-time prompt on first run)
    setup = ensure_networksetup_sudoers()
    if not setup['ok']:
        return {'ok': False, 'services': services, 'error': setup['error']}

    bypass = (
        "127.0.0.1 localhost ::1 *.local "
        "192.168.0.0/16 10.0.0.0/8 172.16.0.0/12 "
        "*.google.com *.googleapis.com *.googlevideo.com *.gstatic.com"
    )
    for svc in services:
        try:
            for args in [
                [NETWORKSETUP, '-setwebproxy',          svc, '127.0.0.1', str(port)],
                [NETWORKSETUP, '-setsecurewebproxy',    svc, '127.0.0.1', str(port)],
                [NETWORKSETUP, '-setproxybypassdomains', svc] + bypass.split(),
            ]:
                r = subprocess.run(['sudo', '-n'] + args, capture_output=True, text=True, timeout=10)
                if r.returncode != 0:
                    return {'ok': False, 'services': services, 'error': r.stderr.strip() or 'networksetup failed'}
        except Exception as e:
            return {'ok': False, 'services': services, 'error': str(e)}
    return {'ok': True, 'services': services, 'error': None}


def unset_macos_proxy() -> dict:
    """
    Disables HTTP+HTTPS proxy on all active network services.
    Uses 'sudo -n' when the sudoers entry is present (no password prompt).
    Returns {'ok': bool, 'services': [...], 'error': str|None}.
    """
    services = get_active_network_services()
    if not services:
        return {'ok': True, 'services': [], 'error': None}  # Already off

    # Ensure passwordless access is set up (one-time prompt on first run)
    setup = ensure_networksetup_sudoers()
    if not setup['ok']:
        return {'ok': False, 'services': services, 'error': setup['error']}

    for svc in services:
        try:
            for args in [
                [NETWORKSETUP, '-setwebproxystate',       svc, 'off'],
                [NETWORKSETUP, '-setsecurewebproxystate', svc, 'off'],
            ]:
                r = subprocess.run(['sudo', '-n'] + args, capture_output=True, text=True, timeout=10)
                if r.returncode != 0:
                    return {'ok': False, 'services': services, 'error': r.stderr.strip() or 'networksetup failed'}
        except Exception as e:
            return {'ok': False, 'services': services, 'error': str(e)}
    return {'ok': True, 'services': services, 'error': None}




# ============================================================================
# USER SCRIPTING
# ============================================================================

DEFAULT_SCRIPT = """\
# OpenProxy User Script
# Available hooks: request(flow), response(flow), websocket_message(flow), error(flow)
# Hooks must be regular (non-async) functions.
# The script is auto-disabled on runtime error.
# Docs: https://docs.mitmproxy.org/stable/api/mitmproxy/http.html

def request(flow):
    \"\"\"Called for every intercepted request. Modify flow.request here.\"\"\"
    pass


def response(flow):
    \"\"\"Called for every intercepted response. Modify flow.response here.\"\"\"
    pass


def error(flow):
    \"\"\"Called when a connection or protocol error occurs.\"\"\"
    pass
"""


def _script_path(script_id: str) -> str:
    return os.path.join(SCRIPTS_DIR, f"{script_id}.py")


def _compile_script(script_id: str, name: str, source: str, enabled: bool) -> dict:
    entry = {
        'id':      script_id,
        'name':    name,
        'source':  source,
        'enabled': enabled,
        'module':  None,
        'error':   '',
    }
    try:
        code = compile(source, _script_path(script_id), 'exec')
        mod  = types.ModuleType(f'user_script_{script_id}')
        mod.__file__ = _script_path(script_id)
        exec(code, mod.__dict__)
        entry['module'] = mod
    except BaseException:
        entry['error']   = traceback.format_exc()
        entry['enabled'] = False
    return entry


class ScriptsManager:
    def __init__(self):
        self._scripts: list[dict] = []

    def load_all(self):
        os.makedirs(SCRIPTS_DIR, exist_ok=True)
        meta = []
        try:
            if os.path.exists(SCRIPTS_META_FILE):
                with open(SCRIPTS_META_FILE, 'r') as f:
                    meta = json.load(f)
        except Exception:
            pass

        self._scripts = []
        for entry in meta:
            sid     = entry.get('id', '')
            name    = entry.get('name', 'Script')
            enabled = bool(entry.get('enabled', False))
            source  = DEFAULT_SCRIPT
            try:
                p = _script_path(sid)
                if os.path.exists(p):
                    with open(p, 'r', encoding='utf-8') as f:
                        source = f.read()
            except Exception:
                pass
            self._scripts.append(_compile_script(sid, name, source, enabled))

    def _save_meta(self):
        os.makedirs(OPENPROXY_DATA_DIR, exist_ok=True)
        meta = [{'id': s['id'], 'name': s['name'], 'enabled': s['enabled']} for s in self._scripts]
        with open(SCRIPTS_META_FILE, 'w') as f:
            json.dump(meta, f)

    def _save_source(self, script_id: str, source: str):
        os.makedirs(SCRIPTS_DIR, exist_ok=True)
        with open(_script_path(script_id), 'w', encoding='utf-8') as f:
            f.write(source)

    def new_script(self, name: str = "New Script") -> dict:
        sid   = str(uuid.uuid4())[:8]
        entry = _compile_script(sid, name, DEFAULT_SCRIPT, False)
        self._scripts.append(entry)
        self._save_source(sid, DEFAULT_SCRIPT)
        self._save_meta()
        return entry

    def save_script(self, script_id: str, name: str, source: str, enabled: bool) -> dict | None:
        for i, s in enumerate(self._scripts):
            if s['id'] == script_id:
                new_entry = _compile_script(script_id, name, source, enabled)
                if new_entry['error']:
                    new_entry['enabled'] = False
                self._scripts[i] = new_entry
                self._save_source(script_id, source)
                self._save_meta()
                return new_entry
        return None

    def delete_script(self, script_id: str):
        self._scripts = [s for s in self._scripts if s['id'] != script_id]
        try:
            os.remove(_script_path(script_id))
        except Exception:
            pass
        self._save_meta()

    def import_all(self, script_list: list):
        """Replace all scripts with the provided list (used during settings import)."""
        # Remove existing script files
        for s in self._scripts:
            try:
                os.remove(_script_path(s['id']))
            except Exception:
                pass
        self._scripts = []
        for item in script_list:
            sid     = item.get('id') or str(uuid.uuid4())[:8]
            name    = item.get('name', 'Script')
            content = item.get('content', '')
            enabled = bool(item.get('enabled', False))
            entry   = _compile_script(sid, name, content, enabled)
            self._scripts.append(entry)
            self._save_source(sid, content)
        self._save_meta()

    def toggle_script(self, script_id: str, enabled: bool) -> dict | None:
        for s in self._scripts:
            if s['id'] == script_id:
                s['enabled'] = enabled
                self._save_meta()
                return s
        return None

    def call_hooks(self, hook: str, flow) -> list[str]:
        """Run hook on all enabled scripts. Returns list of script IDs that errored."""
        errored = []
        for s in self._scripts:
            if not s['enabled'] or not s['module']:
                continue
            fn = getattr(s['module'], hook, None)
            if fn is None:
                continue
            try:
                result = fn(flow)
                if asyncio.iscoroutine(result):
                    result.close()
                    s['error']   = f"Hook '{hook}' must be a regular (non-async) function."
                    s['enabled'] = False
                    errored.append(s['id'])
            except BaseException:
                s['error']   = traceback.format_exc()
                s['enabled'] = False
                errored.append(s['id'])
        return errored

    def state_list(self) -> list[dict]:
        return [
            {'id': s['id'], 'name': s['name'], 'content': s['source'],
             'enabled': s['enabled'], 'error': s['error']}
            for s in self._scripts
        ]


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
        self._ip_onboarding_addon = None  # set by run_proxy_forever; serves mitm cert page on LOCAL_IP
        self._last_startup_error = ""   # captured from mitmproxy's log on startup failure
        self.pending_update_info = None  # cached until a client connects

        # macOS system proxy state — tracked so the SIGTERM handler can auto-unset on quit
        self.is_mac_proxy_set = False
        self.mac_proxy_services = []

        # User scripting
        self.scripts_manager = ScriptsManager()
        self.scripts_manager.load_all()

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
        hostname = _hostname_cache.get(raw_ip)  # None if not yet resolved
        if raw_ip not in _hostname_cache and raw_ip != "Unknown":
            # Fire background resolution — result cached for future requests
            loop = asyncio.get_running_loop()
            task = loop.create_task(_resolve_hostname_bg(raw_ip, self))
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

                        # Apply request header overrides
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

        # User script hooks
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

        # User script hooks
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

    # -------------------------------------------------------------------------
    # USER SCRIPT HELPERS
    # -------------------------------------------------------------------------

    async def _broadcast_scripts_list(self):
        await self.broadcast_to_ui("SCRIPTS_LIST", {"scripts": self.scripts_manager.state_list()})

    async def error(self, flow: http.HTTPFlow):
        """mitmproxy lifecycle hook — connection/protocol errors."""
        if self.scripts_manager.call_hooks('error', flow):
            await self._broadcast_scripts_list()

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

    async def handle_list_avds(self, ws):
        """Lists all configured AVDs (like Android Studio's Device Manager), flagging
        which ones are already running so the UI can offer to boot the rest."""
        try:
            emulator_cmd = get_executable_path("emulator")
            loop = asyncio.get_running_loop()
            avd_names = await asyncio.wait_for(
                loop.run_in_executor(None, list_avds, emulator_cmd),
                timeout=10.0
            )

            running_by_avd = {}
            try:
                adb_cmd = get_executable_path("adb")
                devices = await loop.run_in_executor(None, list_adb_devices, adb_cmd)
                for d in devices:
                    if d["type"] != "emulator":
                        continue
                    avd_name = await loop.run_in_executor(None, get_avd_name_for_serial, adb_cmd, d["serial"])
                    if avd_name:
                        running_by_avd[avd_name] = d["serial"]
            except FileNotFoundError:
                pass  # adb missing — still report the AVD list, just without running-state info

            avds = [{"name": n, "running_serial": running_by_avd.get(n)} for n in avd_names]
            await ws.send(json.dumps({"type": "AVD_LIST", "avds": avds}))
        except asyncio.TimeoutError:
            await ws.send(json.dumps({
                "type": "AVD_LIST", "avds": [],
                "error": "`emulator -list-avds` timed out after 10 seconds."
            }))
        except FileNotFoundError as e:
            await ws.send(json.dumps({"type": "AVD_LIST", "avds": [], "error": str(e)}))
        except Exception as e:
            await ws.send(json.dumps({"type": "AVD_LIST", "avds": [], "error": f"Unexpected error: {e}"}))

    async def boot_avd(self, ws, name: str):
        """Launches an offline AVD (detached, like double-clicking it in Android Studio's
        Device Manager) and waits for it to appear in adb and finish booting."""
        async def send(status, **kw):
            payload = {"type": "AVD_BOOT_PROGRESS", "name": name, "status": status}
            payload.update(kw)
            await ws.send(json.dumps(payload))

        loop = asyncio.get_running_loop()

        try:
            emulator_cmd = get_executable_path("emulator")
        except FileNotFoundError as e:
            await send("error", error=str(e))
            return

        adb_cmd = None
        before_serials = set()
        try:
            adb_cmd = get_executable_path("adb")
            before = await loop.run_in_executor(None, list_adb_devices, adb_cmd)
            before_serials = {d["serial"] for d in before}
        except FileNotFoundError:
            pass

        def _launch():
            kwargs = {}
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                kwargs["start_new_session"] = True
            return subprocess.Popen(
                [emulator_cmd, "-avd", name],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                **kwargs
            )

        try:
            proc = await loop.run_in_executor(None, _launch)
        except Exception as e:
            await send("error", error=str(e))
            return

        await send("launching")
        await asyncio.sleep(2.0)
        if proc.poll() is not None:
            await send("error", error=(
                f"emulator process exited immediately (code {proc.returncode}). "
                "It may already be running, or the AVD config may be broken."
            ))
            return

        if not adb_cmd:
            # Launched successfully but we can't verify boot completion without adb.
            await send("success")
            return

        serial = None
        deadline = loop.time() + 150  # cold boots can take well over a minute
        while loop.time() < deadline:
            try:
                devices = await loop.run_in_executor(None, list_adb_devices, adb_cmd)
            except Exception:
                devices = []
            new_serials = [d["serial"] for d in devices if d["serial"] not in before_serials]
            if new_serials:
                serial = new_serials[0]
                break
            await asyncio.sleep(3)

        if not serial:
            await send("error", error="Timed out waiting for the emulator to appear in `adb devices`.")
            return

        await send("booting", serial=serial)

        deadline = loop.time() + 150
        while loop.time() < deadline:
            try:
                result = await loop.run_in_executor(
                    None,
                    lambda: subprocess.run(
                        [adb_cmd, "-s", serial, "shell", "getprop", "sys.boot_completed"],
                        capture_output=True, text=True, timeout=10
                    )
                )
                if result.stdout.strip() == "1":
                    await send("success", serial=serial)
                    return
            except Exception:
                pass
            await asyncio.sleep(3)

        await send("error", error="Emulator appeared but never finished booting (sys.boot_completed check timed out).")

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

    async def push_cert_to_downloads(self, ws, serial: str):
        """
        Pushes the mitmproxy CA cert (.cer, Android-friendly extension) straight into
        the device's Downloads folder via `adb push`, as an alternative to visiting
        http://mitm.it (useful when the browser force-upgrades to https and fails to load).
        The user still has to tap the file in Downloads/Files to install it as a CA.
        """
        serial_flag = ["-s", serial]
        logs = []

        async def log(msg):
            print(f"[PUSH_CERT] {msg}", flush=True)
            logs.append(msg)
            await ws.send(json.dumps({"type": "CERT_PUSH_LOG", "serial": serial, "message": msg}))

        await log(f"Starting push for serial={serial!r}")
        try:
            adb_cmd = get_executable_path("adb")
            await log(f"Using adb at: {adb_cmd!r}")

            cert_path = os.path.expanduser("~/.mitmproxy/mitmproxy-ca-cert.cer")
            await log(f"Cert path: {cert_path!r} exists={os.path.exists(cert_path)}")
            if not os.path.exists(cert_path):
                error = "Certificate not found. Start the proxy first!"
                await log(f"ERROR: {error}")
                await ws.send(json.dumps({
                    "type": "CERT_PUSHED", "serial": serial, "success": False,
                    "error": error, "logs": logs
                }))
                return

            dest_path = "/sdcard/Download/mitmproxy-ca-cert.cer"
            cmd = [adb_cmd] + serial_flag + ["push", cert_path, dest_path]
            await log(f"Running: {' '.join(cmd)}")

            # Run adb off the event loop with a timeout, so a stuck/unauthorized
            # device can't hang the whole websocket server.
            loop = asyncio.get_event_loop()
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: subprocess.run(cmd, capture_output=True, text=True)
                    ),
                    timeout=20
                )
            except asyncio.TimeoutError:
                error = "adb push timed out after 20s. Is the device authorized (check for an 'Allow USB debugging' prompt)?"
                await log(f"ERROR: {error}")
                await ws.send(json.dumps({
                    "type": "CERT_PUSHED", "serial": serial, "success": False,
                    "error": error, "logs": logs
                }))
                return

            await log(f"returncode={result.returncode}")
            if result.stdout.strip():
                await log(f"stdout: {result.stdout.strip()}")
            if result.stderr.strip():
                await log(f"stderr: {result.stderr.strip()}")
            result.check_returncode()

            await log(f"Success — pushed to {dest_path}")
            await ws.send(json.dumps({
                "type": "CERT_PUSHED", "serial": serial, "success": True,
                "path": dest_path, "logs": logs
            }))
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            await log(f"ERROR: Command failed: {error_msg}")
            await ws.send(json.dumps({
                "type": "CERT_PUSHED", "serial": serial, "success": False,
                "error": f"Command failed: {error_msg}", "logs": logs
            }))
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            await log(f"ERROR: Unexpected error: {e}\n{tb}")
            await ws.send(json.dumps({
                "type": "CERT_PUSHED", "serial": serial, "success": False,
                "error": str(e), "logs": logs
            }))

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

    async def boot_ios_simulator(self, ws, udid: str):
        """Boots a Shutdown iOS Simulator and brings Simulator.app to the foreground."""
        async def send(success, error=None):
            await ws.send(json.dumps({
                "type": "IOS_SIMULATOR_BOOTED", "udid": udid,
                "success": success, "error": error
            }))

        try:
            loop = asyncio.get_running_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: subprocess.run(["xcrun", "simctl", "boot", udid], capture_output=True, text=True)
                ),
                timeout=30
            )
            # simctl errors out if the device is already booted — that's not a real failure.
            if result.returncode != 0 and "current state: Booted" not in (result.stderr or ""):
                error_msg = result.stderr.strip() or result.stdout.strip() or "simctl boot failed"
                await send(False, error_msg)
                return

            await loop.run_in_executor(
                None,
                lambda: subprocess.run(["open", "-a", "Simulator"], capture_output=True, text=True)
            )
            await send(True)
        except asyncio.TimeoutError:
            await send(False, "xcrun simctl boot timed out after 30s.")
        except Exception as e:
            await send(False, str(e))

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

    async def _toggle_macos_proxy(self, websocket, enable: bool):
        if sys.platform != "darwin":
            await websocket.send(json.dumps({
                "type": "MACOS_PROXY_STATUS",
                "active": False,
                "services": [],
                "error": "System proxy toggle is macOS-only.",
            }))
            return

        # Notify the UI if this will require a one-time admin password prompt
        # to install the passwordless sudoers entry.
        if not _sudoers_ok():
            await self.broadcast_to_ui("MACOS_PROXY_FIRST_TIME_SETUP", {})

        # set/unset_macos_proxy() may block on the osascript admin dialog
        # (first run only), so run them off the asyncio loop.
        loop = asyncio.get_running_loop()
        if enable:
            result = await loop.run_in_executor(None, set_macos_proxy, self.proxy_port)
        else:
            result = await loop.run_in_executor(None, unset_macos_proxy)

        if result.get("ok"):
            self.is_mac_proxy_set = enable
            self.mac_proxy_services = result.get("services", []) if enable else []

        await self.broadcast_to_ui("MACOS_PROXY_STATUS", {
            "active": self.is_mac_proxy_set,
            "services": result.get("services", []),
            "error": result.get("error"),
        })

    async def handle_check_cert_trust(self, ws):
        """Reports whether the mitmproxy CA is already trusted on this machine."""
        loop = asyncio.get_running_loop()
        if sys.platform == "darwin":
            trusted = await loop.run_in_executor(None, is_cert_trusted_macos)
        elif sys.platform == "win32":
            trusted = await loop.run_in_executor(None, is_cert_trusted_windows)
        elif sys.platform.startswith("linux"):
            trusted = await loop.run_in_executor(None, is_cert_trusted_linux)
        else:
            trusted = False
        await ws.send(json.dumps({"type": "CERT_TRUST_STATUS", "trusted": trusted}))

    async def handle_trust_cert(self, ws):
        """Trusts the mitmproxy CA in this machine's OS cert store (Chrome/Edge/curl on
        all platforms, plus Safari on macOS). Firefox keeps its own separate store."""
        loop = asyncio.get_running_loop()
        if sys.platform == "darwin":
            result = await loop.run_in_executor(None, trust_cert_macos)
        elif sys.platform == "win32":
            result = await loop.run_in_executor(None, trust_cert_windows)
        elif sys.platform.startswith("linux"):
            result = await loop.run_in_executor(None, trust_cert_linux)
        else:
            result = {"ok": False, "error": f"Unsupported platform: {sys.platform}"}
        await ws.send(json.dumps({"type": "CERT_TRUST_RESULT", "ok": result["ok"], "error": result["error"]}))

    async def websocket_handler(self, websocket):
        self.connected_clients.add(websocket)
        try:
            await websocket.send(json.dumps({
                "type": "SYSTEM_INFO",
                "data": {
                    "ip": LOCAL_IP,
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

                # ---- NEW: List ADB devices ----
                elif payload.get("type") == "LIST_ADB_DEVICES":
                    asyncio.create_task(self.handle_list_adb_devices(websocket))

                # ---- NEW: List AVDs (including offline ones) and boot them on demand ----
                elif payload.get("type") == "LIST_AVDS":
                    asyncio.create_task(self.handle_list_avds(websocket))

                elif payload.get("type") == "BOOT_AVD":
                    avd_name = payload.get("name")
                    if avd_name:
                        asyncio.create_task(self.boot_avd(websocket, avd_name))

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

                # ---- NEW: Push the CA cert straight into the device's Downloads folder ----
                elif payload.get("type") == "PUSH_CERT_TO_DOWNLOADS":
                    serial = payload.get("serial")
                    print(f"[WS] Received PUSH_CERT_TO_DOWNLOADS serial={serial!r}", flush=True)
                    if serial:
                        asyncio.create_task(self.push_cert_to_downloads(websocket, serial))
                    else:
                        print("[WS] PUSH_CERT_TO_DOWNLOADS ignored: no serial provided", flush=True)

                # ---- iOS Simulator setup ----
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
            print(f"[INFO] OpenProxy version: {APP_VERSION}")
            opts = options.Options(listen_host='', listen_port=proxy_port)
            opts.update(mode=modes)
            master = DumpMaster(opts, with_termlog=False, with_dumper=False)
            master.addons.add(bridge)
            # Chrome/Safari's "HTTPS-First" mode auto-upgrades http://mitm.it to https://
            # (it's a public-looking hostname), which shows a cert warning instead of the
            # cert download page. Private-network IPs are exempt from that upgrade, so we
            # also serve the same onboarding app on the device's own LAN IP — used by the
            # physical-device setup instructions/QR code. Kept in sync by _watch_local_ip().
            ip_onboarding = asgiapp.WSGIApp(_onboarding_wsgi_app, LOCAL_IP, None)
            master.addons.add(ip_onboarding)
            bridge._ip_onboarding_addon = ip_onboarding
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

UPDATE_CHECK_INTERVAL_SECS = 6 * 60 * 60  # re-check every 6 hours for long-running sessions

async def _auto_check_update(bridge):
    """Periodically check for updates in the background, starting almost immediately.

    No need to wait for the UI to connect first: check_for_updates() runs on a
    worker thread via run_in_executor and never touches the websocket, and if
    it finishes before any client has connected, bridge.pending_update_info
    caches the result for the on-connect handler to flush (see the
    CONNECTED_CLIENTS handler's `if self.pending_update_info` check).
    """
    await asyncio.sleep(0.5)
    while True:
        try:
            info = await asyncio.get_event_loop().run_in_executor(None, check_for_updates)
            if info:
                bridge.pending_update_info = info
                await bridge.broadcast_to_ui("UPDATE_AVAILABLE", info)
        except Exception as e:
            print(f"[Update] Auto-check error: {e}")
        await asyncio.sleep(UPDATE_CHECK_INTERVAL_SECS)


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
            _watch_local_ip(bridge),
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

    def _shutdown(*_args):
        # If the user set the macOS system proxy this session, unset it on quit
        # — otherwise their entire Mac keeps routing through OpenProxy after we
        # exit. This will pop the admin password dialog one more time.
        if sys.platform == "darwin" and bridge.is_mac_proxy_set:
            try:
                unset_macos_proxy()
            except Exception as e:
                print(f"[QUIT] Failed to unset macOS proxy: {e}", flush=True)
        os._exit(0)

    # Electron sends SIGTERM via pythonProcess.kill() on before-quit; SIGINT
    # covers Ctrl-C in dev. Both must run cleanup before we exit.
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT,  _shutdown)

    try:
        t.join()
    except KeyboardInterrupt:
        _shutdown()