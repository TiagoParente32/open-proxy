from server.bridge.core import BridgeCore
from server.bridge.proxy_hooks import ProxyHooksMixin
from server.bridge.android_setup import AndroidSetupMixin
from server.bridge.ios_setup import IosSetupMixin
from server.bridge.macos_proxy_control import MacProxyControlMixin
from server.bridge.ws_handler import WsHandlerMixin


# ProxyUIBridge is both the mitmproxy addon (added to DumpMaster in
# run_proxy_forever — see ProxyHooksMixin's request/response/websocket_message/
# error/running hooks) and the WebSocket server's connection handler (see
# WsHandlerMixin.websocket_handler). Split across mixins by concern so each
# file stays focused; BridgeCore holds the one __init__ and the shared
# broadcast/state helpers every other mixin relies on.
class ProxyUIBridge(
    BridgeCore,
    ProxyHooksMixin,
    AndroidSetupMixin,
    IosSetupMixin,
    MacProxyControlMixin,
    WsHandlerMixin,
):
    pass
