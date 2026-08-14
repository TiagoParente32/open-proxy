import os
import sys
import subprocess

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

def _sudoers_entry_for_user(username: str) -> str:
    return f'{username} ALL=(root) NOPASSWD: {NETWORKSETUP}\n'

def _sudoers_ok() -> bool:
    """Return True if 'sudo -n networksetup' works without a password prompt."""
    try:
        r = subprocess.run(
            ['sudo', '-n', NETWORKSETUP, '-help'],
            capture_output=True, timeout=5
        )
        return r.returncode == 0
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
