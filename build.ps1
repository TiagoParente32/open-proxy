# ─────────────────────────────────────────────
# OpenProxy build script (Windows)
# Usage:
#   .\build.ps1          → interactive menu
#   .\build.ps1 app      → build .exe folder only
#   .\build.ps1 zip      → build .exe folder + package as ZIP
# ─────────────────────────────────────────────

param([string]$Mode = "")

$ErrorActionPreference = "Stop"
$APP_NAME = "OpenProxy"

$PyInstallerArgs = @(
    "--name", $APP_NAME,
    "--windowed",
    "--icon=icon.ico",
    "--add-data", "ui/dist;ui/dist",
    "--add-data", "icon.ico;.",
    "--add-data", "icon.png;.",
    "main.py"
)

# ── Resolve mode ──────────────────────────────
if (-not $Mode) {
    Write-Host ""
    Write-Host "What do you want to build?"
    Write-Host "  1) App only  (dist\OpenProxy\ folder with .exe)"
    Write-Host "  2) ZIP       (.exe folder packaged as a ZIP)"
    Write-Host ""
    $choice = Read-Host "Choice [1/2]"
    $Mode = if ($choice -eq "2") { "zip" } else { "app" }
}

# ── Build UI ──────────────────────────────────
Write-Host ""
Write-Host ">> Building UI..."
Push-Location ui
npm run build
Pop-Location

# ── Clean previous dist ───────────────────────
Write-Host ">> Cleaning dist\..."
if (Test-Path dist) { Remove-Item -Recurse -Force dist }

# ── PyInstaller ───────────────────────────────
Write-Host ">> Running PyInstaller..."
pyinstaller @PyInstallerArgs

Write-Host ""
Write-Host "OK App built -> dist\$APP_NAME\"

# ── ZIP ───────────────────────────────────────
if ($Mode -eq "zip") {
    $version = python -c 'import re; print(re.search(r"APP_VERSION\s*=\s*[\"'"'"'](.*?)[\"'"'"']", open("main.py").read()).group(1))'
    $zipName = "${APP_NAME}-${version}-windows.zip"

    Write-Host ">> Creating ZIP: $zipName..."
    Compress-Archive -Path "dist\$APP_NAME" -DestinationPath "dist\$zipName"

    Write-Host ""
    Write-Host "OK ZIP built -> dist\$zipName"
}

Write-Host ""
Write-Host "Done!"
