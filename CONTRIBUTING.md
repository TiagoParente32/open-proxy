# Contributing to OpenProxy

Thanks for your interest in improving OpenProxy! This document explains how to get a development environment running, how we work, and what to expect when you open a pull request.

By participating you agree to follow our [Code of Conduct](CODE_OF_CONDUCT.md).

## Table of Contents

- [Ways to contribute](#ways-to-contribute)
- [Development setup](#development-setup)
- [Project layout](#project-layout)
- [Making changes](#making-changes)
- [Pull requests](#pull-requests)
- [Releases](#releases)
- [License](#license)

## Ways to contribute

- **Report bugs** using the [bug report template](https://github.com/TiagoParente32/open-proxy/issues/new?template=bug_report.yml). Include your OS, OpenProxy version, and steps to reproduce.
- **Suggest features** using the [feature request template](https://github.com/TiagoParente32/open-proxy/issues/new?template=feature_request.yml). Explain the problem you are trying to solve, not only the solution you have in mind.
- **Improve the docs**: the README and the in-app Devices guides are a big part of the product. Typos, clearer wording, and missing steps are all welcome.
- **Fix bugs or build features**: pick an open issue (look for `good first issue` or `help wanted`) or open a new one first so we can agree on the approach before you invest time.

## Development setup

### Prerequisites

| Tool | Version | Needed for |
|---|---|---|
| Node.js | 18+ | Electron shell and Vue UI |
| Python | 3.10+ | Backend (`main.py`) |
| ADB | any recent | Android device features |
| OpenSSL | any recent | Android system-certificate hashing |
| Xcode command line tools | latest | iOS Simulator features (macOS only) |

### Install

```bash
# Electron + root dependencies
npm install

# Vue frontend
cd ui && npm install && cd ..

# Python backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Run in development

```bash
./run.sh      # macOS / Linux
.\run.ps1     # Windows
```

Electron builds the Vue UI, spawns the Python backend from your local `venv`, and opens the window. Restart the app after changing `main.py` or anything in `electron/`. For UI-only changes, `npm run build` inside `ui/` and reload the window.

### Build an installer

See [Building for Distribution](README.md#-building-for-distribution) in the README. Each platform must be built on its own OS.

## Project layout

```
open-proxy/
├── electron/           # Electron main process + preload (window, tray, IPC, Python lifecycle)
├── ui/                 # Vue 3 + Vite frontend (all UI lives here)
├── main.py             # Python backend: mitmproxy addon, WebSocket API, device helpers, updater
├── requirements.txt    # Python dependencies
├── OpenProxy.spec      # PyInstaller spec for the backend binary
├── build.sh            # macOS build
├── build.ps1           # Windows build
├── build-linux.sh      # Linux build
└── .github/workflows/  # Release automation
```

The three pieces talk to each other over a local WebSocket. Keep that boundary clean: the UI should not shell out or touch the filesystem directly, and the backend should not know about Electron.

## Making changes

1. **Fork** the repository and create a branch from `main`:
   ```bash
   git checkout -b feature/short-description
   ```
   Use `feature/`, `fix/`, `docs/` or `chore/` prefixes.
2. **Keep changes focused.** One logical change per pull request makes review faster and history easier to follow.
3. **Match the existing style.**
   - Python: PEP 8, 4-space indentation, type hints where they help.
   - JavaScript / Vue: 2-space indentation, single quotes, no semicolons unless already present in the file. Plain CSS, no component libraries.
   - Prefer small, well-named functions over comments explaining a large one.
4. **Test on the platforms you touched.** There is no automated test suite yet, so please describe in the PR what you exercised manually (for example "verified Map Local on Windows 11 and macOS 15").
5. **Update the docs** if you changed user-facing behaviour: the README, and the in-app Devices guide text in `ui/` where relevant.
6. **Do not commit build output** (`dist/`, `dist-electron/`, `backend-dist/`, `ui/dist/`) or your `venv`. They are already ignored by `.gitignore`.

### Commit messages

Use short imperative subjects, optionally prefixed with a type:

```
feat: prompt to trust the mitmproxy CA on this machine
fix: macOS privilege elevation before applying an update
docs: clarify Firefox proxy setup
chore: bump electron-builder
```

## Pull requests

- Open the PR against `main` and fill in the pull request template.
- Link the issue it closes (`Closes #123`).
- Include screenshots or a short recording for UI changes.
- Keep the PR up to date with `main` if it falls behind; we squash-merge, so you do not need to tidy your commit history.
- A maintainer will review, may ask for changes, and merges once approved.

## Releases

Releases are fully automated by [`.github/workflows/release.yml`](.github/workflows/release.yml):

1. A maintainer adds the `release` label to a pull request.
2. When that PR is squash-merged into `main`, the workflow bumps the version in `package.json`, tags the commit, builds macOS, Windows and Linux artifacts, and publishes a GitHub Release.
3. Running apps pick up the new version through the in-app auto-updater.

Contributors do not need to touch version numbers; leave `package.json` and `version.json` alone in your PR.

## License

OpenProxy is licensed under the [GNU General Public License v3.0](LICENSE). By submitting a contribution you agree that it will be distributed under the same license.
