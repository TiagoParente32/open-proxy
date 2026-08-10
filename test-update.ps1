# test-update.ps1 — End-to-end auto-update test on Windows
#
# What this does:
#   1. Builds the app (always, unless -NoBuild is passed — main.py and the
#      UI are compiled/bundled at build time, so a stale dist-electron\ zip
#      silently tests old code otherwise)
#   2. Finds the built win zip and the unpacked app produced alongside it
#   3. Starts a local HTTP server serving that zip as the "new version"
#   4. Launches the unpacked app with OPENPROXY_UPDATE_TEST_URL set so it
#      immediately sees a fake v99.9.9 update pointing at your local server
#
# Usage:
#   .\test-update.ps1            → build, then run the test
#   .\test-update.ps1 -NoBuild   → skip build, use existing dist-electron\ zip
#
# When the app opens:
#   - The update banner should appear within a couple of seconds
#   - Click "Update Now" to test the full download + replace flow
#   - The app will quit and relaunch from the unpacked app directory
#   - Check %TEMP%\openproxy_update_*\update.log if anything goes wrong
param([switch]$NoBuild)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$PORT = 9999

# ── 1. Build (unless skipped) ─────────────────────────────────────────────
if (-not $NoBuild) {
    Write-Host "-> Building (pass -NoBuild to reuse the existing dist-electron\ zip)..."
    & ./build.ps1
}

# ── 2. Find the win zip ───────────────────────────────────────────────────
$zip = Get-ChildItem dist-electron -Filter "*win*.zip" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $zip) {
    Write-Host "x No win zip found in dist-electron\. Run .\build.ps1 first."
    exit 1
}
Write-Host "OK Using zip: $($zip.FullName)"

# ── 3. Find the unpacked app (electron-builder's win-unpacked dir) ────────
$appDir = Get-ChildItem dist-electron -Directory -Filter "*win-unpacked*" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $appDir) {
    Write-Host "x No win-unpacked app dir found in dist-electron\. Run .\build.ps1 first."
    exit 1
}
$exePath = Join-Path $appDir.FullName "OpenProxy.exe"
if (-not (Test-Path $exePath)) {
    Write-Host "x OpenProxy.exe not found under $($appDir.FullName)"
    exit 1
}
Write-Host "OK Using app: $exePath"

# Copy the zip to a known filename so the URL is stable
$tempZip = Join-Path $env:TEMP "openproxy_test_update.zip"
Copy-Item $zip.FullName $tempZip -Force
Write-Host "OK Copied zip to $tempZip"

# ── 4. Start local HTTP server ─────────────────────────────────────────────
# Kill anything already listening on the port from a previous run
Get-NetTCPConnection -LocalPort $PORT -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

Write-Host "-> Starting HTTP server on port $PORT..."
$server = Start-Process python -ArgumentList "-m", "http.server", "$PORT", "--directory", $env:TEMP `
    -PassThru -WindowStyle Hidden
Write-Host "OK Server running (PID $($server.Id))"

Start-Sleep -Seconds 1

# ── 5. Launch the app with the test env var ─────────────────────────────────
$updateUrl = "http://127.0.0.1:$PORT/openproxy_test_update.zip"
Write-Host ""
Write-Host "----------------------------------------------------"
Write-Host "  Opening: $exePath"
Write-Host "  Fake update URL: $updateUrl"
Write-Host ""
Write-Host "  The update banner should appear within a couple of seconds."
Write-Host "  Click 'Update Now' to test the full replace flow."
Write-Host ""
Write-Host "  Logs (if update fails): $env:TEMP\openproxy_update_*\update.log"
Write-Host "----------------------------------------------------"
Write-Host ""

$env:OPENPROXY_UPDATE_TEST_URL = $updateUrl
$app = Start-Process $exePath -PassThru
$env:OPENPROXY_UPDATE_TEST_URL = $null

# Wait for the app to exit, then clean up the server
try { Wait-Process -Id $app.Id -ErrorAction SilentlyContinue } catch {}
Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
Write-Host "OK Done. Server stopped."
