# <img src="icon.png" width="36" align="absmiddle" alt="OpenProxy Icon" /> OpenProxy

OpenProxy is a fast, modern, lightweight network debugging proxy built for developers. It combines the raw power of `mitmproxy` with a sleek, native-feeling desktop UI built in **Electron**, **Vue 3**, and **Python**.

Whether you need to mock API responses, rewrite routing rules on the fly, throttle your network, or automatically inject SSL certificates into an Android emulator, OpenProxy handles it without the bloat of traditional Java-based proxies.

![OpenProxy Interface](screenshots/example.png)

## ✨ Key Features

* **Traffic Interception**: View, inspect, and filter HTTP/HTTPS requests in real-time.
* **Map Local (Mocking)**: Trick your app into receiving custom JSON/HTML responses without touching your backend.
* **Map Remote (Rewrites)**: Transparently route production URLs to your `localhost` development server.
* **Live Breakpoints**: Pause requests or responses mid-flight, edit their headers/bodies, and release them.
* **VPN Mode**: Route device traffic through a WireGuard tunnel — no manual proxy configuration needed.
* **Smart Android Setup**: 1-click ADB integration. Automatically detects rooted emulators to inject System Certificates, or gracefully falls back to User Certificates.
* **Network Throttling**: Simulate "Fast 3G" or "Slow 3G" network conditions.
* **Aggressive Cache Busting**: One-click toggle to strip caching headers and force fresh responses.
* **Auto-Update**: The app checks for new releases on startup and can update itself in one click.
* **Pro-Grade UI**: Ultra-compact toolbar, dark mode, right-click context menus, and split-pane layout.

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3, `mitmproxy` (proxy engine), `websockets` |
| **Frontend** | Vue 3, Vite, raw CSS (no component libraries) |
| **Desktop shell** | Electron — serves the Vue app and manages the Python subprocess |

The app is structured as three loosely coupled pieces:
- **Electron** (`electron/`) — the native window, OS menus, tray icon, and IPC bridge. It spawns the Python backend on startup and loads the built Vue frontend.
- **Vue UI** (`ui/`) — the entire interface, communicating with the Python backend over a local WebSocket.
- **Python backend** (`main.py`) — runs `mitmproxy` and streams proxy state to the UI.

---

## 💻 Local Development

### Prerequisites

* Node.js 18+
* Python 3.10+
* ADB (Android Debug Bridge) in your system PATH *(Android features only)*
* OpenSSL *(Android root certificate hashing only)*

### 1. Install Dependencies

**Electron & root deps:**
```bash
npm install
```

**Vue frontend:**
```bash
cd ui && npm install && cd ..
```

**Python backend:**
```bash
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Run in Dev Mode

```bash
# macOS / Linux
./run.sh

# Windows
.\run.ps1
```

This launches Electron. On startup Electron will:
1. Build the Vue UI automatically (`npm run build` inside `ui/`)
2. Spawn the Python backend from the local `venv`
3. Load the built UI in the window

> The Python backend and the Vue frontend communicate over a local WebSocket — there is no HTTP server involved in serving the UI.

---

## 📦 Building for Distribution

The build is a **3-step pipeline**: Vue UI → Python binary (PyInstaller) → Electron installer (electron-builder).

### macOS

```bash
./build.sh          # → DMG + ZIP (arm64 + x64) in dist-electron/
./build.sh --dir    # unpackaged app only (faster, for testing)
```

> Must be run on a Mac. Produces both Apple Silicon and Intel builds in one run.

### Windows

```powershell
.\build.ps1         # → NSIS .exe installer + .zip in dist-electron\
.\build.ps1 --dir   # unpackaged app only (faster, for testing)
```

> Must be run on a Windows machine.

### Linux

```bash
# Install required packaging tools (first time only)
sudo apt install fakeroot dpkg rpm

./build-linux.sh            # → .deb + .rpm + .AppImage + .tar.gz (x64) in dist-electron/
./build-linux.sh --arm64    # → same targets for arm64 (must run on arm64 hardware)
./build-linux.sh --dir      # unpackaged app only (fastest, for testing)
```

> `.deb` and `.rpm` can both be built from Ubuntu in one run — no Fedora machine needed.  
> arm64 builds require arm64 hardware because PyInstaller compiles native binaries.

### What each step produces

| Step | Tool | Output |
|---|---|---|
| 1. Vue UI | Vite | `ui/dist/` |
| 2. Python backend | PyInstaller | `backend-dist/OpenProxy-server/` |
| 3. Installer | electron-builder | `dist-electron/` |

### Distribution targets

| Platform | Targets | Notes |
|---|---|---|
| macOS | `.dmg`, `.zip` (arm64 + x64) | DMG for fresh install, ZIP used by auto-update |
| Windows | NSIS `.exe`, `.zip` | EXE for fresh install, ZIP used by auto-update |
| Linux | `.deb`, `.rpm`, `.AppImage`, `.tar.gz` (x64) | DEB/RPM install to app launcher; AppImage used by auto-update |

---

## 🔄 Auto-Update

The app checks GitHub Releases on startup (after an 8-second delay). If a newer version is found, a banner appears at the top of the window.

- **Update Now** — downloads the release zip/AppImage for your platform and architecture, launches a background script that replaces the app and relaunches it.
- The update check is also accessible from the native app menu → **Check for Updates**.

To publish a release, upload all distribution targets to a GitHub Release tagged `vX.Y.Z`. The version is read from `APP_VERSION` in `main.py` — bump that and `version` in `package.json` together before building.

---

## 🤖 Android Certificate Notes

Modern Android (API 24+) ignores user-installed certificates by default. To intercept traffic from your own apps:
1. **The Easy Way (Root)**: Create a "Google APIs" emulator (NOT "Google Play"). Run it from the terminal with `emulator -avd <name> -writable-system`. Click OpenProxy's **Certificate → Android Emulator** to automatically inject the system cert.
2. **The App Config Way (Non-Root)**: Add a `network_security_config.xml` to your Android Studio project to explicitly trust user certificates during debug builds.

---

## 🍎 iOS Certificate Notes

The iOS Simulator on macOS shares your Mac's network stack, so you configure the Mac's proxy settings — the simulator inherits them automatically.

1. Start OpenProxy — note the proxy port (starts at 9090) and your local IP shown in the toolbar.
2. Set your Mac's HTTP/HTTPS proxy:
   - System Settings → Network → Wi-Fi → Details → Proxies
   - Enable **Web Proxy (HTTP)** and **Secure Web Proxy (HTTPS)**
   - Server: your local IP (e.g. `192.168.1.x`) or `127.0.0.1`, Port: as shown in OpenProxy
3. In the iOS Simulator, open Safari and go to `http://mitm.it`
4. Download and install the mitmproxy certificate profile.
5. Enable certificate trust: Settings → General → About → Certificate Trust Settings → toggle the mitmproxy cert **ON**.

> When you're done, remember to disable the Mac's proxy settings so your regular traffic stops routing through OpenProxy.

The full setup guide is also available in-app — open **Certificate** in the toolbar and select the iOS Simulator tab.
