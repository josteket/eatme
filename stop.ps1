# Stops EAT ME: the autostart VBS watcher, the app (pythonw) and the tunnel.
$ErrorActionPreference = 'SilentlyContinue'

# Kill only the autostart watcher (our VBS), not other scripts
Get-CimInstance Win32_Process -Filter "Name='wscript.exe'" |
  Where-Object { $_.CommandLine -like '*eatme-autostart.vbs*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

taskkill /IM pythonw.exe /F 2>$null | Out-Null
taskkill /IM cloudflared.exe /F 2>$null | Out-Null

Write-Host "EAT ME stopped." -ForegroundColor Green
Write-Host "It will start again after your next Windows logon (if autostart is on)."
