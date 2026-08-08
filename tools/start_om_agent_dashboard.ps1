param(
  [int]$Port = 8765,
  [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo
$env:PYTHONPATH = $Repo

$arguments = @('tools/om_agent_dashboard_v2.py','--port',"$Port")
if (-not $NoBrowser) { $arguments += '--open' }

Write-Host "Opus Magnum Codex - OM Agent v2" -ForegroundColor Cyan
Write-Host "Dashboard: http://127.0.0.1:$Port/" -ForegroundColor Green
Write-Host "Ctrl+C ferme seulement le serveur du dashboard." -ForegroundColor DarkGray
python @arguments
