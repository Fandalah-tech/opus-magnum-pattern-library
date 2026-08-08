param(
  [int]$Port = 8765,
  [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo
$env:PYTHONPATH = $Repo

$arguments = @('tools/om_agent_dashboard_v4.py','--port',"$Port")
if (-not $NoBrowser) { $arguments += '--open' }

Write-Host "Opus Magnum Codex - OM Agent v4 unattended" -ForegroundColor Cyan
Write-Host "Dashboard: http://127.0.0.1:$Port/" -ForegroundColor Green
Write-Host "Workers plafonnes a 12 · watchdog 35 s · Top 3 semantiquement distinct." -ForegroundColor DarkGray
Write-Host "Ctrl+C ferme seulement le serveur du dashboard." -ForegroundColor DarkGray
python @arguments
