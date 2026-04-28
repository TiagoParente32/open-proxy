# ─────────────────────────────────────────────────────────────────
# OpenProxy build script — Windows
# Produces: dist-electron\OpenProxy-*.exe installer (and .zip)
#
# Usage:
#   .\build.ps1           → NSIS installer + ZIP
#   .\build.ps1 --dir     → unpackaged app (fast, for testing)
# ─────────────────────────────────────────────────────────────────
param([string]$Mode = "")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Read version from root package.json
$version = node -p "require('./package.json').version"
Write-Host "Building OpenProxy v$version"

# ── 1. Vue UI ────────────────────────────────────────────────────
Write-Host ""
Write-Host "→ [1/3] Building Vue UI..."
Set-Location ui
npm install --silent
npm run build
Set-Location ..

# ── 2. Python backend (PyInstaller) ──────────────────────────────
Write-Host ""
Write-Host "→ [2/3] Bundling Python backend..."
$pythonExe = if (Test-Path "venv\Scripts\python.exe") { "venv\Scripts\python.exe" } else { "python" }

if (Test-Path "backend-dist") { Remove-Item -Recurse -Force "backend-dist" }
if (Test-Path "build-pyinstaller") { Remove-Item -Recurse -Force "build-pyinstaller" }

& $pythonExe -m PyInstaller `
  --name "OpenProxy-server" `
  --distpath backend-dist `
  --workpath build-pyinstaller `
  --clean `
  --noconfirm `
  main.py

if (Test-Path "build-pyinstaller") { Remove-Item -Recurse -Force "build-pyinstaller" }
if (Test-Path "OpenProxy-server.spec") { Remove-Item "OpenProxy-server.spec" }

# ── 3. Electron packaging ─────────────────────────────────────────
Write-Host ""
Write-Host "→ [3/3] Packaging with electron-builder..."
if ($Mode -eq "--dir") {
    npx electron-builder --dir
} else {
    npx electron-builder --win
}

Write-Host ""
Write-Host "✓ Done! Output in dist-electron\"
Get-ChildItem dist-electron -ErrorAction SilentlyContinue
