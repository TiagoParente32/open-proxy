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
# Newest first: dist-electron\ accumulates zips from earlier versions.
$zip = Get-ChildItem dist-electron -Filter "*win*.zip" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
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

# Stand in for a connected agent: an MCP server running from this install with
# its stdin held open, like a client keeps it. Before the fix this made the
# update script wait its full 30s and then force-kill it.
$psi = New-Object Diagnostics.ProcessStartInfo
$psi.FileName = Join-Path $appDir.FullName "resources\backend\OpenProxy-server\OpenProxy-server.exe"
$psi.Arguments = "--mcp"
$psi.UseShellExecute = $false
$psi.RedirectStandardInput = $true
$psi.CreateNoWindow = $true
$mcp = [Diagnostics.Process]::Start($psi)
Write-Host "OK Fake agent MCP server running (PID $($mcp.Id))"

# Wait for the app to exit, then clean up the server
try { Wait-Process -Id $app.Id -ErrorAction SilentlyContinue } catch {}
Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
Write-Host "OK Done. Server stopped."

Start-Sleep -Seconds 1
if (-not $mcp.HasExited) {
    Write-Host "x The update left the agent's MCP server running (PID $($mcp.Id))"
    $mcp.Kill(); exit 1
}
Write-Host "OK The update stopped the agent's MCP server"

# -- 6. MCP launcher check against the relaunched app ----------------------
# The update swapped the install folder; the launcher the backend writes on
# startup must now point into it and still serve MCP ("register once, keep
# updating" for agents).
$shim = Join-Path $env:USERPROFILE ".openproxy\bin\openproxy-mcp.cmd"
Write-Host ""
Write-Host "-> Waiting for the relaunched app (up to 90s)..."
$up = $false
for ($i = 0; $i -lt 90; $i++) {
    try {
        $c = New-Object Net.Sockets.TcpClient
        $c.Connect("127.0.0.1", 8765); $c.Close(); $up = $true; break
    } catch { Start-Sleep -Seconds 1 }
}
if (-not $up) { Write-Host "x Relaunched app never opened port 8765"; exit 1 }
# The swap is done by now, so the log is complete. Nothing should have kept
# the script waiting anywhere near its 30s limit.
$log = Get-ChildItem $env:TEMP -Directory -Filter "openproxy_update_*" |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($log -and (Select-String -Path (Join-Path $log.FullName "update.log") -Pattern "\(2\d/30\)" -Quiet)) {
    Write-Host "x The update script waited out its exit loop - see $($log.FullName)\update.log"; exit 1
}
Write-Host "OK The update script didn't have to wait out its exit loop"
Start-Sleep -Seconds 2
if (-not (Test-Path $shim)) { Write-Host "x MCP launcher missing: $shim"; exit 1 }
$installDir = Split-Path -Parent $exePath
if (-not (Select-String -Path $shim -SimpleMatch $installDir -Quiet)) {
    Write-Host "x MCP launcher does not point at the relaunched app:"; Get-Content $shim | Select-Object -Last 1; exit 1
}
Write-Host "OK Launcher points at the relaunched install: $(Get-Content $shim | Select-Object -Last 1)"
$init = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test-update","version":"0"}}}'
$reply = $init | & cmd /c $shim 2>$null | Select-Object -First 1
if ("$reply" -match '"serverInfo"') {
    Write-Host "OK MCP launcher answers initialize from the updated app"
} else {
    Write-Host "x MCP launcher did not answer initialize: $reply"; exit 1
}
