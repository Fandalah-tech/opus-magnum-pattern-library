param(
  [string]$RepositoryPath = "",
  [int]$IntervalMinutes = 5
)

$ErrorActionPreference = 'Stop'
$AgentRoot = Join-Path $env:ProgramData 'OpusMagnumAgent'
$LogPath = Join-Path $AgentRoot 'agent.log'
$InstalledScript = Join-Path $AgentRoot 'om_local_agent.ps1'
$RawSelfUrl = 'https://raw.githubusercontent.com/Fandalah-tech/opus-magnum-pattern-library/main/tools/om_local_agent.ps1'
$ResearchBranch = 'feature/disjoint-solver-readiness'
$TaskName = 'Opus Magnum Local Agent'
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
    if ((Get-Item $temp).Length -lt 500) { throw 'Telechargement incomplet.' }
    $currentHash = if (Test-Path $InstalledScript) { (Get-FileHash $InstalledScript -Algorithm SHA256).Hash } else { '' }
    $nextHash = (Get-FileHash $temp -Algorithm SHA256).Hash
    if ($currentHash -ne $nextHash) {
      Copy-Item $temp $InstalledScript -Force
      Unblock-File $InstalledScript
      Write-AgentLog 'Agent local mis a jour; la nouvelle version sera utilisee au prochain passage.'
    }
    Remove-Item $temp -Force -ErrorAction SilentlyContinue
  } catch {
    Write-AgentLog "Mise a jour autonome ignoree: $($_.Exception.Message)"
  }
}

function Ensure-TaskSettings {
  try {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 6)
    Set-ScheduledTask -TaskName $TaskName -Action $task.Actions -Trigger $task.Triggers -Settings $settings -Principal $task.Principal | Out-Null
  } catch {
    Write-AgentLog "Reglage de la tache ignore: $($_.Exception.Message)"
  }
}

function Find-Repository {
  if ($RepositoryPath -and (Test-Path (Join-Path $RepositoryPath '.git'))) {
    return (Resolve-Path $RepositoryPath).Path
  }
  $profiles = @($env:USERPROFILE, 'C:\Users\bruno') | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique
  $candidates = @('C:\GitHub\opus-magnum-pattern-library', 'C:\Repos\opus-magnum-pattern-library')
  foreach ($profile in $profiles) {
    $candidates += Join-Path $profile 'opus-magnum-pattern-library'
    $candidates += Join-Path $profile 'Documents\GitHub\opus-magnum-pattern-library'
    $candidates += Join-Path $profile 'source\repos\opus-magnum-pattern-library'
  }
  foreach ($candidate in $candidates) {
    if (Test-Path (Join-Path $candidate '.git')) { return (Resolve-Path $candidate).Path }
  }
  foreach ($profile in $profiles) {
    $found = Get-ChildItem -Path $profile -Directory -Filter 'opus-magnum-pattern-library' -Recurse -ErrorAction SilentlyContinue |
      Where-Object { Test-Path (Join-Path $_.FullName '.git') } | Select-Object -First 1
    if ($found) { return $found.FullName }
  }
  return $null
}

function Ensure-RunnerService {
  $service = Get-Service -Name 'actions.runner.*' -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match 'opus-magnum-pattern-library|Bruno-OMSIM|Fandalah' } | Select-Object -First 1
  if (-not $service) { $service = Get-Service -Name 'actions.runner.*' -ErrorAction SilentlyContinue | Select-Object -First 1 }
  if (-not $service) { Write-AgentLog 'Aucun service GitHub Actions Runner detecte.'; return }
  Set-Service -Name $service.Name -StartupType Automatic
  if ($service.Status -ne 'Running') {
    Start-Service -Name $service.Name
    Write-AgentLog "Runner redemarre: $($service.Name)"
  }
  & sc.exe failure $service.Name reset= 86400 actions= restart/60000/restart/60000/restart/60000 | Out-Null
  & sc.exe failureflag $service.Name 1 | Out-Null
}

function Sync-Repository {
  param([string]$Repo)
  if (-not $Repo) { Write-AgentLog 'Depot local introuvable; synchronisation ignoree.'; return $false }
  Push-Location $Repo
  try {
    $dirty = git status --porcelain 2>$null
    if ($LASTEXITCODE -ne 0) { Write-AgentLog 'Git est inaccessible ou le depot est invalide.'; return $false }
    git fetch origin $ResearchBranch --prune 2>&1 | ForEach-Object { Write-AgentLog $_ }
    if ($dirty) { Write-AgentLog 'Modifications locales detectees; traitement de file ignore.'; return $false }
    $branch = git branch --show-current
    if ($branch -ne $ResearchBranch) {
      git checkout $ResearchBranch 2>&1 | ForEach-Object { Write-AgentLog $_ }
      if ($LASTEXITCODE -ne 0) { return $false }
    }
    git pull --ff-only origin $ResearchBranch 2>&1 | ForEach-Object { Write-AgentLog $_ }
    return ($LASTEXITCODE -eq 0)
  } finally { Pop-Location }
}

function Process-NextTask {
  param([string]$Repo)
  $pending = Join-Path $Repo '.om-bridge\tasks\pending'
  if (-not (Test-Path $pending)) { return }
  $task = Get-ChildItem -Path $pending -Filter '*.json' -File | Sort-Object LastWriteTime, Name | Select-Object -First 1
  if (-not $task) { Write-AgentLog 'File locale vide.'; return }

  Push-Location $Repo
  try {
    Write-AgentLog "Execution directe de la tache: $($task.Name)"
    $env:PYTHONPATH = $Repo
    & python tools/om_worker.py --task $task.FullName --results-root '.om-bridge/results'
    $exitCode = $LASTEXITCODE
    $destinationFolder = if ($exitCode -eq 0) { '.om-bridge\tasks\completed' } else { '.om-bridge\tasks\failed' }
    New-Item -ItemType Directory -Force -Path $destinationFolder | Out-Null
    git mv -- $task.FullName (Join-Path $destinationFolder $task.Name) 2>&1 | ForEach-Object { Write-AgentLog $_ }
    git config user.name 'om-local-agent'
    git config user.email 'om-local-agent@users.noreply.github.com'
    git add .om-bridge reports 2>&1 | ForEach-Object { Write-AgentLog $_ }
    git diff --cached --quiet
    if ($LASTEXITCODE -ne 0) {
      git commit -m "Process OMSIM queue task $($task.BaseName)" 2>&1 | ForEach-Object { Write-AgentLog $_ }
      git pull --rebase origin $ResearchBranch 2>&1 | ForEach-Object { Write-AgentLog $_ }
      git push origin "HEAD:$ResearchBranch" 2>&1 | ForEach-Object { Write-AgentLog $_ }
    }
    Write-AgentLog "Tache terminee avec code $exitCode: $($task.Name)"
  } catch {
    Write-AgentLog "ERREUR pendant la tache $($task.Name): $($_.Exception.Message)"
  } finally { Pop-Location }
}

function Prevent-Sleep {
  & powercfg.exe /change standby-timeout-ac 0 | Out-Null
  & powercfg.exe /change hibernate-timeout-ac 0 | Out-Null
  & powercfg.exe /change monitor-timeout-ac 20 | Out-Null
}

try {
  Update-Self
  Ensure-TaskSettings
  Prevent-Sleep
  Ensure-RunnerService
  $repo = Find-Repository
  if (Sync-Repository -Repo $repo) { Process-NextTask -Repo $repo }
  Write-AgentLog "Verification terminee. Repo=$repo"
  exit 0
} catch {
  Write-AgentLog "ERREUR: $($_.Exception.Message)"
  exit 1
}
