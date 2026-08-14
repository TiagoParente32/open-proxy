import os
import json
import asyncio
import subprocess

from server import system_helpers
from server.system_helpers import get_executable_path
from server.adb import list_adb_devices


class AndroidSetupMixin:
    """WebSocket-driven ADB device listing / cert install / cert revert."""

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
        serial_flag = ["-s", serial]

        # Emulators reach the host machine via the special alias 10.0.2.2.
        # Physical devices need the real LAN IP since they're on the actual network.
        proxy_host = "10.0.2.2" if device_type == "emulator" else system_helpers.LOCAL_IP

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
