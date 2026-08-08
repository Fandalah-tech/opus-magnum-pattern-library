param(
  [int]$Port = 8765,
  [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo
$env:PYTHONPATH = $Repo

$arguments = @('tools/om_agent_dashboard_v5.py','--port',"$Port")
if (-not $NoBrowser) { $arguments += '--open' }

Write-Host "Opus Magnum Codex - OM Agent v5 non-repeating" -ForegroundColor Cyan
Write-Host "Dashboard: http://127.0.0.1:$Port/" -ForegroundColor Green
Write-Host "Workers plafonnes a 8 - watchdog 25 s - budget generation 90 s - registre global des tentatives." -ForegroundColor DarkGray
python @arguments
