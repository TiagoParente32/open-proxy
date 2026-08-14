import os
import sys
import json
import stat
import ssl
import subprocess
import urllib.request

from server.constants import APP_VERSION, APP_PRODUCT_NAME, APP_LINUX_EXE_NAME, GITHUB_REPO

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
    # Dev mode (unfrozen): updater.py lives in server/, so go up one more
    # level than __file__'s own directory to land on the project root
    # (matches the pre-refactor behavior where this lived directly in main.py).
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
