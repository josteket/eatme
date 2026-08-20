# Removes EAT ME autostart and stops the running app.
$ErrorActionPreference = 'SilentlyContinue'

$startup = [Environment]::GetFolderPath('Startup')
$vbsPath = Join-Path $startup 'eatme-autostart.vbs'
if (Test-Path $vbsPath) { Remove-Item $vbsPath -Force }

# Stop the autostart watcher (VBS) and the app so it does not restart itself
Get-CimInstance Win32_Process -Filter "Name='wscript.exe'" |
  Where-Object { $_.CommandLine -like '*eatme-autostart.vbs*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
taskkill /IM pythonw.exe /F 2>$null | Out-Null
taskkill /IM cloudflared.exe /F 2>$null | Out-Null

Write-Host "Autostart removed and app stopped." -ForegroundColor Green
