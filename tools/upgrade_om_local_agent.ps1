param(
  [int]$MaxCpuPercent = 50,
  [int]$IdleSeconds = 15,
  [string]$RepositoryPath = ''
)

$ErrorActionPreference = 'Stop'

function Find-OmRepository {
  param([string]$Explicit)
  if ($Explicit -and (Test-Path (Join-Path $Explicit '.git'))) { return (Resolve-Path $Explicit).Path }
  $candidates = @(
    'C:\actions-runner\_work\opus-magnum-pattern-library\opus-magnum-pattern-library',
    'C:\GitHub\opus-magnum-pattern-library',
    'C:\Repos\opus-magnum-pattern-library',
    (Join-Path $env:USERPROFILE 'Documents\GitHub\opus-magnum-pattern-library'),
    (Join-Path $env:USERPROFILE 'source\repos\opus-magnum-pattern-library')
  ) | Select-Object -Unique
  foreach ($candidate in $candidates) {
    if (Test-Path (Join-Path $candidate '.git')) { return (Resolve-Path $candidate).Path }
  }
  throw 'Depot opus-magnum-pattern-library introuvable.'
}

$repo = Find-OmRepository -Explicit $RepositoryPath
Write-Host "Depot : $repo"
Push-Location $repo
try {
  git config --global --add safe.directory ($repo -replace '\\','/') 2>$null
  git fetch origin main --prune
  if ($LASTEXITCODE -ne 0) { throw 'git fetch origin main a echoue.' }
  $installer = Join-Path $env:TEMP 'install_om_local_agent.ps1'
  $content = & git show 'origin/main:tools/install_om_local_agent.ps1'
  if ($LASTEXITCODE -ne 0) { throw 'Impossible de lire install_om_local_agent.ps1 depuis origin/main.' }
  $content | Set-Content -Path $installer -Encoding UTF8
} finally { Pop-Location }

PowerShell.exe -NoProfile -ExecutionPolicy Bypass -File $installer -RepositoryPath $repo -MaxCpuPercent $MaxCpuPercent -IdleSeconds $IdleSeconds
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ''
Write-Host 'Mise a niveau OM Agent terminee.' -ForegroundColor Green
Write-Host 'Le watchdog, la protection contre la veille et la reprise automatique sont maintenant actifs.'
