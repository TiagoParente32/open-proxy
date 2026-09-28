import os
import sys
import json
import ssl
import asyncio
import hashlib
import sqlite3
import subprocess

from server.ios_simulator import list_ios_simulators


class IosSetupMixin:
    """WebSocket-driven iOS Simulator listing / cert install / cert revert
    (macOS only)."""

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
