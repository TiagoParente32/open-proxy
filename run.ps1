$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Build UI if dist is missing
if (-not (Test-Path "ui\dist\index.html")) {
    Write-Host "Building UI..."
    Set-Location ui
    npm install --silent
    npm run build
    Set-Location ..
}

# Start Python backend in background
Write-Host "Starting Python backend..."
$pythonExe = if (Test-Path "venv\Scripts\python.exe") { "venv\Scripts\python.exe" } else { "python" }
$pythonProc = Start-Process -FilePath $pythonExe -ArgumentList "main.py" -PassThru -NoNewWindow

Start-Sleep -Seconds 1

# Launch Electron (blocks until window closes)
Write-Host "Launching Electron..."
npm start

# Kill Python when Electron exits
Stop-Process -Id $pythonProc.Id -Force -ErrorAction SilentlyContinue
