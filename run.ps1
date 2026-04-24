Write-Host "Building UI..."
Set-Location ui
npm run build
Set-Location ..

Write-Host "Starting app..."
python main.py