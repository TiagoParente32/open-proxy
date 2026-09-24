import os
import subprocess

from server.system_helpers import get_executable_path

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


def _refresh_windows_proxy_settings():
    """Tells WinINet (and therefore Chrome/Edge) to re-read the registry proxy
    settings immediately, instead of waiting for the next app restart."""
    import ctypes
    INTERNET_OPTION_SETTINGS_CHANGED = 39
    INTERNET_OPTION_REFRESH = 37
    ctypes.windll.wininet.InternetSetOptionW(0, INTERNET_OPTION_SETTINGS_CHANGED, 0, 0)
    ctypes.windll.wininet.InternetSetOptionW(0, INTERNET_OPTION_REFRESH, 0, 0)


def set_windows_proxy(port: int) -> dict:
    """
    Sets HTTP+HTTPS proxy to 127.0.0.1:<port> via the per-user registry key —
    HKCU, not HKLM, so no admin/UAC elevation is needed.
    """
    import winreg
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, f"127.0.0.1:{port}")
        winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ,
            "localhost;127.*;10.*;172.16.*;172.17.*;172.18.*;172.19.*;172.2*.*;172.30.*;172.31.*;192.168.*;<local>")
        winreg.CloseKey(key)
        _refresh_windows_proxy_settings()
        return {'ok': True, 'error': None}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def unset_windows_proxy() -> dict:
    """Disables the per-user HTTP+HTTPS proxy set by set_windows_proxy()."""
    import winreg
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
        winreg.CloseKey(key)
        _refresh_windows_proxy_settings()
        return {'ok': True, 'error': None}
    except Exception as e:
        return {'ok': False, 'error': str(e)}
