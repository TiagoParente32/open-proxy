import os
import sys
import json

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
            # constants.py lives inside server/, but version.json / package.json
            # live at the project root — go up one more level.
            root = os.path.dirname(root)
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

# Raw byte cap for images inlined as base64 into a UI broadcast. Kept well
# under the ~1MB WS message limit browsers enforce (base64 alone inflates
# size ~33%, plus JSON/header overhead) so a large image can't kill every
# connected client's WebSocket the moment it's captured.
MAX_INLINE_IMAGE_BYTES = 700_000
