# Installs EAT ME autostart via the user's Startup folder (no admin needed).
# Creates a hidden VBS that waits 60s after logon, runs the app, and
# restarts it automatically if it ever crashes.
$ErrorActionPreference = 'Stop'

$root = $PSScriptRoot
$pyw  = Join-Path $root '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $pyw)) {
  Write-Host "[!] .venv not found. Run install.bat first." -ForegroundColor Red
  exit 1
}
if (-not (Test-Path (Join-Path $root 'tools\cloudflared.exe'))) {
  Write-Host "[!] tools\cloudflared.exe missing (needed for the tunnel)." -ForegroundColor Yellow
}

$script  = Join-Path $root 'run_public.py'
$startup = [Environment]::GetFolderPath('Startup')
$vbsPath = Join-Path $startup 'eatme-autostart.vbs'

$vbs = @"
' EAT ME autostart (auto-generated). Waits 1 min after logon, runs hidden,
' and restarts the app if it crashes.
Set sh = CreateObject("WScript.Shell")
WScript.Sleep 60000
sh.CurrentDirectory = "$root"
Do
  sh.Run """$pyw"" ""$script""", 0, True
  WScript.Sleep 5000
Loop
"@

Set-Content -Path $vbsPath -Value $vbs -Encoding ASCII
Write-Host "OK: autostart installed." -ForegroundColor Green
Write-Host "File: $vbsPath"
Write-Host "It starts ~1 minute after you log into Windows, hidden, and self-restarts."
Write-Host "Stop now: run stop.bat   |   Turn off autostart: autostart-off.bat"
