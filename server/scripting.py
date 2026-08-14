import os
import json
import uuid
import types
import asyncio
import traceback

from server.constants import OPENPROXY_DATA_DIR, SCRIPTS_DIR, SCRIPTS_META_FILE

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
