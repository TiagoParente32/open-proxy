import asyncio

import websockets
from mitmproxy import options
from mitmproxy.tools.dump import DumpMaster
from mitmproxy.addons import asgiapp
from mitmproxy.addons.onboardingapp import app as _onboarding_wsgi_app

from server.constants import APP_VERSION
from server.updater import check_for_updates
from server import system_helpers
from server.system_helpers import _watch_local_ip

# Global refs so background threads can reach the bridge and its event loop
_global_bridge = None
_global_loop   = None


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
            ip_onboarding = asgiapp.WSGIApp(_onboarding_wsgi_app, system_helpers.LOCAL_IP, None)
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
