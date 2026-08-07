param(
  [string]$RepositoryPath = "",
  [int]$IntervalMinutes = 5
)

$ErrorActionPreference = 'Stop'
$AgentRoot = Join-Path $env:ProgramData 'OpusMagnumAgent'
$LogPath = Join-Path $AgentRoot 'agent.log'
$InstalledScript = Join-Path $AgentRoot 'om_local_agent.ps1'
$RawSelfUrl = 'https://raw.githubusercontent.com/Fandalah-tech/opus-magnum-pattern-library/main/tools/om_local_agent.ps1'
New-Item -ItemType Directory -Force -Path $AgentRoot | Out-Null

function Write-AgentLog {
  param([string]$Message)
  $line = "{0:u} {1}" -f (Get-Date), $Message
  Add-Content -Path $LogPath -Value $line -Encoding UTF8
}

function Update-Self {
  try {
    $temp = Join-Path $AgentRoot 'om_local_agent.next.ps1'
    Invoke-WebRequest -Uri ($RawSelfUrl + '?t=' + [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()) -OutFile $temp -UseBasicParsing
    if ((Get-Item $temp).Length -lt 500) { throw 'Téléchargement incomplet.' }
    $currentHash = if (Test-Path $InstalledScript) { (Get-FileHash $InstalledScript -Algorithm SHA256).Hash } else { '' }
    $nextHash = (Get-FileHash $temp -Algorithm SHA256).Hash
    if ($currentHash -ne $nextHash) {
      Copy-Item $temp $InstalledScript -Force
      Unblock-File $InstalledScript
      Write-AgentLog 'Agent local mis à jour; la nouvelle version sera utilisée au prochain passage.'
    }
    Remove-Item $temp -Force -ErrorAction SilentlyContinue
  } catch {
    Write-AgentLog "Mise à jour autonome ignorée: $($_.Exception.Message)"
  }
}

function Find-Repository {
  if ($RepositoryPath -and (Test-Path (Join-Path $RepositoryPath '.git'))) {
    return (Resolve-Path $RepositoryPath).Path
  }

  $candidates = @(
    (Join-Path $env:USERPROFILE 'opus-magnum-pattern-library'),
    (Join-Path $env:USERPROFILE 'Documents\GitHub\opus-magnum-pattern-library'),
    (Join-Path $env:USERPROFILE 'source\repos\opus-magnum-pattern-library'),
    'C:\GitHub\opus-magnum-pattern-library',
    'C:\Repos\opus-magnum-pattern-library'
  )

  foreach ($candidate in $candidates) {
    if (Test-Path (Join-Path $candidate '.git')) { return (Resolve-Path $candidate).Path }
  }

  $found = Get-ChildItem -Path $env:USERPROFILE -Directory -Filter 'opus-magnum-pattern-library' -Recurse -ErrorAction SilentlyContinue |
    Where-Object { Test-Path (Join-Path $_.FullName '.git') } |
    Select-Object -First 1
  if ($found) { return $found.FullName }
  return $null
}

function Ensure-RunnerService {
  $service = Get-Service -Name 'actions.runner.*' -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match 'opus-magnum-pattern-library|Bruno-OMSIM|Fandalah' } |
    Select-Object -First 1

  if (-not $service) { $service = Get-Service -Name 'actions.runner.*' -ErrorAction SilentlyContinue | Select-Object -First 1 }
  if (-not $service) { Write-AgentLog 'Aucun service GitHub Actions Runner détecté.'; return }

  Set-Service -Name $service.Name -StartupType Automatic
  if ($service.Status -ne 'Running') {
    Start-Service -Name $service.Name
    Write-AgentLog "Runner redémarré: $($service.Name)"
  }

  & sc.exe failure $service.Name reset= 86400 actions= restart/60000/restart/60000/restart/60000 | Out-Null
  & sc.exe failureflag $service.Name 1 | Out-Null
}

function Sync-Repository {
  param([string]$Repo)
  if (-not $Repo) { Write-AgentLog 'Dépôt local introuvable; synchronisation ignorée.'; return }

  Push-Location $Repo
  try {
    $dirty = git status --porcelain 2>$null
    if ($LASTEXITCODE -ne 0) { Write-AgentLog 'Git est inaccessible ou le dépôt est invalide.'; return }
    git fetch origin feature/disjoint-solver-readiness --prune 2>&1 | ForEach-Object { Write-AgentLog $_ }
    if (-not $dirty) {
      $branch = git branch --show-current
      if ($branch -eq 'feature/disjoint-solver-readiness') {
        git pull --ff-only origin feature/disjoint-solver-readiness 2>&1 | ForEach-Object { Write-AgentLog $_ }
      }
    } else {
      Write-AgentLog 'Modifications locales détectées; pull automatique ignoré.'
    }
  } finally { Pop-Location }
}

function Prevent-Sleep {
  & powercfg.exe /change standby-timeout-ac 0 | Out-Null
  & powercfg.exe /change hibernate-timeout-ac 0 | Out-Null
  & powercfg.exe /change monitor-timeout-ac 20 | Out-Null
}

try {
  Update-Self
  Prevent-Sleep
  Ensure-RunnerService
  $repo = Find-Repository
  Sync-Repository -Repo $repo
  Write-AgentLog "Vérification terminée. Repo=$repo"
  exit 0
} catch {
  Write-AgentLog "ERREUR: $($_.Exception.Message)"
  exit 1
}
