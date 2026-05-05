$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Electron handles the UI build and Python backend startup automatically
Write-Host "Launching Electron..."
npm start
