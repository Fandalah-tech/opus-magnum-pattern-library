param(
  [string]$RepositoryPath = "",
  [int]$IntervalMinutes = 1
)

$ErrorActionPreference = 'Stop'
$AgentRoot = Join-Path $env:ProgramData 'OpusMagnumAgent'
$LogPath = Join-Path $AgentRoot 'agent.log'
$InstalledScript = Join-Path $AgentRoot 'om_local_agent.ps1'
$RawSelfUrl = 'https://raw.githubusercontent.com/Fandalah-tech/opus-magnum-pattern-library/main/tools/om_local_agent.ps1'
$ResearchBranch = 'feature/disjoint-solver-readiness'
$TaskName = 'Opus Magnum Local Agent'
$OpusRoot = 'C:\Users\bruno\Documents\My Games\Opus Magnum'
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
    $triggers = @(
      (New-ScheduledTaskTrigger -AtStartup),
      (New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes))
    )
    Set-ScheduledTask -TaskName $TaskName -Action $task.Actions -Trigger $triggers -Settings $settings -Principal $task.Principal | Out-Null
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

function Get-TaskPriority {
  param([System.IO.FileInfo]$TaskFile)
  try {
    $data = Get-Content -Raw -Path $TaskFile.FullName | ConvertFrom-Json
    if ($null -ne $data.priority) { return [int]$data.priority }
  } catch {
    Write-AgentLog "Priorite illisible pour $($TaskFile.Name): $($_.Exception.Message)"
  }
  return 0
}

function Process-NextTask {
  param([string]$Repo)
  $pending = Join-Path $Repo '.om-bridge\tasks\pending'
  if (-not (Test-Path $pending)) { return }

  $tasks = @(Get-ChildItem -Path $pending -Filter '*.json' -File)
  if ($tasks.Count -eq 0) { Write-AgentLog 'File locale vide.'; return }

  $ranked = foreach ($candidate in $tasks) {
    [PSCustomObject]@{
      File = $candidate
      Priority = Get-TaskPriority -TaskFile $candidate
      Modified = $candidate.LastWriteTimeUtc
    }
  }
  $selected = $ranked | Sort-Object @{Expression='Priority';Descending=$true}, @{Expression='Modified';Descending=$false}, @{Expression={ $_.File.Name };Descending=$false} | Select-Object -First 1
  $task = $selected.File

  Push-Location $Repo
  try {
    Write-AgentLog "Execution directe PRIORITE=$($selected.Priority): $($task.Name)"
    $env:PYTHONPATH = $Repo
    $env:OM_OPUS_MAGNUM_ROOT = $OpusRoot
    if (Test-Path $OpusRoot) {
      Write-AgentLog "Source Opus Magnum: $OpusRoot"
    } else {
      Write-AgentLog "ATTENTION source Opus Magnum introuvable: $OpusRoot"
    }
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
