import os
import shutil
import subprocess

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


def _linux_desktop_environment() -> str:
    """Best-effort GNOME/KDE detection via the standard XDG env vars."""
    de = (os.environ.get('XDG_CURRENT_DESKTOP') or os.environ.get('DESKTOP_SESSION') or '').lower()
    if 'kde' in de or 'plasma' in de:
        return 'kde'
    if 'gnome' in de or 'unity' in de or 'cinnamon' in de or 'budgie' in de:
        return 'gnome'
    return 'unknown'


def _kwriteconfig_cmd():
    """kwriteconfig6 (Plasma 6) or kwriteconfig5 (Plasma 5) — whichever is on PATH."""
    return shutil.which('kwriteconfig6') or shutil.which('kwriteconfig5')


def set_linux_proxy(port: int) -> dict:
    """
    Sets HTTP+HTTPS proxy to 127.0.0.1:<port> for the current desktop session.
    GNOME: gsettings (applies live to GNOME/GTK apps and Chrome immediately).
    KDE: writes kioslaverc via kwriteconfig — best-effort, some apps may need
    a restart to pick it up. No admin privileges needed for either.
    """
    de = _linux_desktop_environment()
    try:
        if de == 'gnome':
            bypass = "['localhost', '127.0.0.0/8', '::1']"
            for cmd in [
                ['gsettings', 'set', 'org.gnome.system.proxy', 'mode', 'manual'],
                ['gsettings', 'set', 'org.gnome.system.proxy.http', 'host', '127.0.0.1'],
                ['gsettings', 'set', 'org.gnome.system.proxy.http', 'port', str(port)],
                ['gsettings', 'set', 'org.gnome.system.proxy.https', 'host', '127.0.0.1'],
                ['gsettings', 'set', 'org.gnome.system.proxy.https', 'port', str(port)],
                ['gsettings', 'set', 'org.gnome.system.proxy', 'ignore-hosts', bypass],
            ]:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if r.returncode != 0:
                    return {'ok': False, 'error': r.stderr.strip() or f"'{cmd[0]}' failed"}
            return {'ok': True, 'error': None}

        if de == 'kde':
            kwriteconfig = _kwriteconfig_cmd()
            if not kwriteconfig:
                return {'ok': False, 'error': "kwriteconfig5/6 not found — can't configure KDE's proxy settings."}
            proxy_val = f"http://127.0.0.1 {port}"
            for args in [
                ['--file', 'kioslaverc', '--group', 'Proxy Settings', '--key', 'ProxyType', '1'],
                ['--file', 'kioslaverc', '--group', 'Proxy Settings', '--key', 'httpProxy', proxy_val],
                ['--file', 'kioslaverc', '--group', 'Proxy Settings', '--key', 'httpsProxy', proxy_val],
                ['--file', 'kioslaverc', '--group', 'Proxy Settings', '--key', 'NoProxyFor', 'localhost,127.0.0.1,::1'],
            ]:
                r = subprocess.run([kwriteconfig] + args, capture_output=True, text=True, timeout=5)
                if r.returncode != 0:
                    return {'ok': False, 'error': r.stderr.strip() or 'kwriteconfig failed'}
            return {'ok': True, 'error': None}

        return {'ok': False, 'error': (
            f"Unsupported desktop environment ({de or 'unknown'}). "
            "GNOME and KDE are supported automatically — set the proxy manually "
            "via your DE's network settings otherwise."
        )}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def unset_linux_proxy() -> dict:
    """Disables the proxy set by set_linux_proxy()."""
    de = _linux_desktop_environment()
    try:
        if de == 'gnome':
            r = subprocess.run(['gsettings', 'set', 'org.gnome.system.proxy', 'mode', 'none'],
                                capture_output=True, text=True, timeout=5)
            if r.returncode != 0:
                return {'ok': False, 'error': r.stderr.strip() or "'gsettings' failed"}
            return {'ok': True, 'error': None}

        if de == 'kde':
            kwriteconfig = _kwriteconfig_cmd()
            if not kwriteconfig:
                return {'ok': False, 'error': "kwriteconfig5/6 not found — can't configure KDE's proxy settings."}
            r = subprocess.run(
                [kwriteconfig, '--file', 'kioslaverc', '--group', 'Proxy Settings', '--key', 'ProxyType', '0'],
                capture_output=True, text=True, timeout=5
            )
            if r.returncode != 0:
                return {'ok': False, 'error': r.stderr.strip() or 'kwriteconfig failed'}
            return {'ok': True, 'error': None}

        return {'ok': False, 'error': f"Unsupported desktop environment ({de or 'unknown'})."}
    except Exception as e:
        return {'ok': False, 'error': str(e)}
