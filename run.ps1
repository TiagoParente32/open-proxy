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

# Electron spawns and manages the Python backend itself
Write-Host "Launching Electron..."
npm start
