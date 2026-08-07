param(
  [ValidateSet('Run','Start','Pause','Stop','Status')]
  [string]$Command = 'Run',
  [string]$RepositoryPath = '',
  [int]$MaxCpuPercent = 50,
  [int]$IdleSeconds = 15,
  [string]$ResearchBranch = 'feature/disjoint-solver-readiness',
  [string]$OpusRoot = ''
)

$ErrorActionPreference = 'Stop'
$AgentRoot = Join-Path $env:LOCALAPPDATA 'OpusMagnumAgent'
$LogPath = Join-Path $AgentRoot 'agent.log'
$StatePath = Join-Path $AgentRoot 'state.json'
$StatusPath = Join-Path $AgentRoot 'status.json'
$PidPath = Join-Path $AgentRoot 'agent.pid'
$InstalledScript = Join-Path $AgentRoot 'om_local_agent.ps1'
New-Item -ItemType Directory -Force -Path $AgentRoot | Out-Null

function Write-AgentLog {
  param([string]$Message)
  $line = "{0:u} {1}" -f (Get-Date), $Message
  Add-Content -Path $LogPath -Value $line -Encoding UTF8
}

function Write-JsonAtomic {
  param([string]$Path, [object]$Value)
  $temp = "$Path.tmp"
  $Value | ConvertTo-Json -Depth 8 | Set-Content -Path $temp -Encoding UTF8
  Move-Item -Path $temp -Destination $Path -Force
}

function Invoke-GitLogged {
  param([string[]]$Arguments)
  $previousPreference = $ErrorActionPreference
  try {
    $script:ErrorActionPreference = 'Continue'
    $output = & git @Arguments 2>&1
    $code = $LASTEXITCODE
  } finally {
    $script:ErrorActionPreference = $previousPreference
  }
  foreach ($line in @($output)) { Write-AgentLog ([string]$line) }
  return [PSCustomObject]@{ ExitCode = $code; Output = @($output) }
}

function Get-DesiredState {
  if (-not (Test-Path $StatePath)) { return 'running' }
  try {
    $state = Get-Content -Raw -Path $StatePath | ConvertFrom-Json
    if ($state.desired_state -in @('running','paused','stopped')) { return [string]$state.desired_state }
  } catch {}
  return 'running'
}

function Set-DesiredState {
  param([ValidateSet('running','paused','stopped')][string]$State)
  Write-JsonAtomic -Path $StatePath -Value ([ordered]@{
    desired_state = $State
    changed_at = (Get-Date).ToUniversalTime().ToString('o')
    changed_by = $env:USERNAME
  })
}

function Get-AgentProcess {
  if (-not (Test-Path $PidPath)) { return $null }
  try {
    $pidValue = [int](Get-Content -Raw -Path $PidPath)
    return Get-Process -Id $pidValue -ErrorAction Stop
  } catch {
    Remove-Item $PidPath -Force -ErrorAction SilentlyContinue
    return $null
  }
}

function Show-AgentStatus {
  $proc = Get-AgentProcess
  if (Test-Path $StatusPath) {
    try {
      $status = Get-Content -Raw -Path $StatusPath | ConvertFrom-Json
      $status | Add-Member -NotePropertyName process_alive -NotePropertyValue ([bool]$proc) -Force
      $status | ConvertTo-Json -Depth 8
      return
    } catch {}
  }
  [ordered]@{
    process_alive = [bool]$proc
    desired_state = Get-DesiredState
    status = if ($proc) { 'starting' } else { 'stopped' }
  } | ConvertTo-Json
}

function Resolve-OpusRoot {
  if ($OpusRoot -and (Test-Path $OpusRoot)) { return (Resolve-Path $OpusRoot).Path }
  $candidates = @(
    (Join-Path $env:USERPROFILE 'Documents\My Games\Opus Magnum'),
    (Join-Path $env:USERPROFILE 'OneDrive\Documents\My Games\Opus Magnum')
  ) | Select-Object -Unique
  foreach ($candidate in $candidates) {
    if (Test-Path $candidate) { return (Resolve-Path $candidate).Path }
  }
  return $candidates[0]
}

function Find-Repository {
  if ($RepositoryPath -and (Test-Path (Join-Path $RepositoryPath '.git'))) {
    return (Resolve-Path $RepositoryPath).Path
  }
  $candidates = @(
    'C:\actions-runner\_work\opus-magnum-pattern-library\opus-magnum-pattern-library',
    'C:\GitHub\opus-magnum-pattern-library',
    'C:\Repos\opus-magnum-pattern-library',
    (Join-Path $env:USERPROFILE 'opus-magnum-pattern-library'),
    (Join-Path $env:USERPROFILE 'Documents\GitHub\opus-magnum-pattern-library'),
    (Join-Path $env:USERPROFILE 'source\repos\opus-magnum-pattern-library')
  ) | Select-Object -Unique
  foreach ($candidate in $candidates) {
    if (Test-Path (Join-Path $candidate '.git')) { return (Resolve-Path $candidate).Path }
  }
  return $null
}

function Get-PorcelainPath {
  param([string]$Line)
  if ([string]::IsNullOrWhiteSpace($Line) -or $Line.Length -lt 4) { return '' }
  $path = $Line.Substring(3).Trim()
  if ($path -match ' -> ') { $path = ($path -split ' -> ')[-1] }
  $path = $path.Trim('"') -replace '\\','/'
  return $path
}

function Test-RuntimeDirtyPath {
  param([string]$Path)
  if ([string]::IsNullOrWhiteSpace($Path)) { return $false }
  return (
    $Path -like 'reports/rotor-a41-*' -or
    $Path -eq 'reports/live-search-status.json' -or
    $Path -eq 'reports/om-agent-status.json' -or
    $Path -like '.om-bridge/results/*'
  )
}

function Sync-Repository {
  param([string]$Repo)
  if (-not $Repo) { Write-AgentLog 'Depot local introuvable.'; return $false }
  Push-Location $Repo
  $runtimeStashed = $false
  try {
    $statusResult = Invoke-GitLogged -Arguments @('status','--porcelain','--untracked-files=all')
    if ($statusResult.ExitCode -ne 0) { Write-AgentLog 'Git inaccessible ou depot invalide.'; return $false }
    $dirty = @($statusResult.Output | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })
    if ($dirty.Count -gt 0) {
      $unsafe = @()
      foreach ($line in $dirty) {
        $path = Get-PorcelainPath -Line ([string]$line)
        if (-not (Test-RuntimeDirtyPath -Path $path)) { $unsafe += [string]$line }
      }
      if ($unsafe.Count -gt 0) {
        Write-AgentLog ('Depot modifie hors runtime; synchronisation/file suspendue: ' + ($unsafe -join ' | '))
        return $false
      }

      Write-AgentLog 'Checkpoint/runtime OMSIM detecte apres interruption; preservation temporaire avant synchronisation.'
      $stash = Invoke-GitLogged -Arguments @(
        'stash','push','--include-untracked','-m','om-agent-runtime-recovery','--',
        'reports/rotor-a41-*','reports/live-search-status.json','reports/om-agent-status.json','.om-bridge/results'
      )
      if ($stash.ExitCode -ne 0) {
        Write-AgentLog 'Impossible de preserver le checkpoint/runtime; synchronisation suspendue.'
        return $false
      }
      $runtimeStashed = $true
    }

    $fetch = Invoke-GitLogged -Arguments @('fetch','origin',$ResearchBranch,'--prune')
    if ($fetch.ExitCode -ne 0) { return $false }

    $branchResult = Invoke-GitLogged -Arguments @('branch','--show-current')
    if ($branchResult.ExitCode -ne 0) { return $false }
    $branch = ([string]($branchResult.Output | Select-Object -First 1)).Trim()
    if ($branch -ne $ResearchBranch) {
      $checkout = Invoke-GitLogged -Arguments @('checkout',$ResearchBranch)
      if ($checkout.ExitCode -ne 0) { return $false }
    }

    $pull = Invoke-GitLogged -Arguments @('pull','--ff-only','origin',$ResearchBranch)
    if ($pull.ExitCode -ne 0) { return $false }

    if ($runtimeStashed) {
      $restore = Invoke-GitLogged -Arguments @('stash','pop')
      if ($restore.ExitCode -ne 0) {
        Write-AgentLog 'Conflit lors de la restauration du checkpoint/runtime; stash conserve pour recuperation manuelle.'
        return $false
      }
      Write-AgentLog 'Checkpoint/runtime OMSIM restaure; reprise de la file autorisee.'
    }
    return $true
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

function Get-NextTask {
  param([string]$Repo)
  $pending = Join-Path $Repo '.om-bridge\tasks\pending'
  if (-not (Test-Path $pending)) { return $null }
  $tasks = @(Get-ChildItem -Path $pending -Filter '*.json' -File)
  if ($tasks.Count -eq 0) { return $null }
  $ranked = foreach ($candidate in $tasks) {
    [PSCustomObject]@{
      File = $candidate
      Priority = Get-TaskPriority -TaskFile $candidate
      Modified = $candidate.LastWriteTimeUtc
    }
  }
  return ($ranked | Sort-Object @{Expression='Priority';Descending=$true}, @{Expression='Modified';Descending=$false}, @{Expression={ $_.File.Name };Descending=$false} | Select-Object -First 1)
}

function Get-CpuAffinityMask {
  $logical = [Environment]::ProcessorCount
  if ($MaxCpuPercent -lt 5) { $script:MaxCpuPercent = 5 }
  if ($MaxCpuPercent -gt 100) { $script:MaxCpuPercent = 100 }
  $cores = [Math]::Max(1, [Math]::Floor($logical * $MaxCpuPercent / 100.0))
  $usable = [Math]::Min($cores, 63)
  [UInt64]$mask = 0
  for ($i = 0; $i -lt $usable; $i++) { $mask = $mask -bor ([UInt64]1 -shl $i) }
  return [PSCustomObject]@{ Mask = $mask; Cores = $usable; Logical = $logical }
}

function Stop-ProcessTree {
  param([int]$ProcessId)
  try { & taskkill.exe /PID $ProcessId /T /F 2>$null | Out-Null } catch {}
}

function Get-WorkerExitCode {
  param([System.Diagnostics.Process]$Process, [string]$Repo, [string]$TaskId)
  try { $Process.WaitForExit() } catch {}
  try {
    $code = [int]$Process.ExitCode
    if ($code -ge 0) { return $code }
  } catch {}
  $summaryPath = Join-Path $Repo ".om-bridge\results\$TaskId\summary.json"
  if (Test-Path $summaryPath) {
    try {
      $summary = Get-Content -Raw -Path $summaryPath | ConvertFrom-Json
      if ($null -ne $summary.exit_code) {
        Write-AgentLog "ExitCode recupere du summary worker: $($summary.exit_code)"
        return [int]$summary.exit_code
      }
    } catch { Write-AgentLog "Summary worker illisible: $($_.Exception.Message)" }
  }
  Write-AgentLog 'ExitCode worker indisponible; classification en echec par securite.'
  return 1
}

function Invoke-Task {
  param([string]$Repo, [object]$Selected, [string]$ResolvedOpusRoot)
  $task = $Selected.File
  $taskData = Get-Content -Raw -Path $task.FullName | ConvertFrom-Json
  $taskId = if ($taskData.id) { [string]$taskData.id } else { $task.BaseName }
  $stdoutPath = Join-Path $AgentRoot 'worker.stdout.log'
  $stderrPath = Join-Path $AgentRoot 'worker.stderr.log'
  Remove-Item $stdoutPath,$stderrPath -Force -ErrorAction SilentlyContinue

  Push-Location $Repo
  try {
    $env:PYTHONPATH = $Repo
    $env:OM_OPUS_MAGNUM_ROOT = $ResolvedOpusRoot
    Write-AgentLog "Execution PRIORITE=$($Selected.Priority): $($task.Name)"

    $args = @('tools/om_worker.py','--task',$task.FullName,'--results-root','.om-bridge/results')
    $proc = Start-Process -FilePath 'python' -ArgumentList $args -WorkingDirectory $Repo -PassThru -NoNewWindow -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    try {
      $affinity = Get-CpuAffinityMask
      $proc.PriorityClass = 'BelowNormal'
      $proc.ProcessorAffinity = [IntPtr]([Int64]$affinity.Mask)
      Write-AgentLog "Worker PID=$($proc.Id), CPU cap~$MaxCpuPercent% ($($affinity.Cores)/$($affinity.Logical) logical CPUs), priority=BelowNormal."
    } catch {
      Write-AgentLog "Controle CPU partiel: $($_.Exception.Message)"
    }

    while (-not $proc.HasExited) {
      Start-Sleep -Seconds 2
      $proc.Refresh()
      $desired = Get-DesiredState
      if ($desired -ne 'running') {
        Write-AgentLog "Interruption worker demandee: $desired"
        Stop-ProcessTree -ProcessId $proc.Id
        try { $proc.WaitForExit() } catch {}
        return [PSCustomObject]@{ Interrupted = $true; ExitCode = 130 }
      }
    }

    $exitCode = Get-WorkerExitCode -Process $proc -Repo $Repo -TaskId $taskId
    if (Test-Path $stdoutPath) { Get-Content $stdoutPath | ForEach-Object { Write-AgentLog "worker: $_" } }
    if (Test-Path $stderrPath) { Get-Content $stderrPath | ForEach-Object { Write-AgentLog "worker-err: $_" } }
    $destinationFolder = if ($exitCode -eq 0) { '.om-bridge\tasks\completed' } else { '.om-bridge\tasks\failed' }
    New-Item -ItemType Directory -Force -Path $destinationFolder | Out-Null
    Invoke-GitLogged -Arguments @('mv','--',$task.FullName,(Join-Path $destinationFolder $task.Name)) | Out-Null
    Invoke-GitLogged -Arguments @('config','user.name','om-local-agent') | Out-Null
    Invoke-GitLogged -Arguments @('config','user.email','om-local-agent@users.noreply.github.com') | Out-Null
    Invoke-GitLogged -Arguments @('add','.om-bridge','reports') | Out-Null
    $diffCheck = Invoke-GitLogged -Arguments @('diff','--cached','--quiet')
    if ($diffCheck.ExitCode -ne 0) {
      $commit = Invoke-GitLogged -Arguments @('commit','-m',"Process OMSIM queue task $($task.BaseName)")
      if ($commit.ExitCode -eq 0) {
        $pull = Invoke-GitLogged -Arguments @('pull','--rebase','origin',$ResearchBranch)
        if ($pull.ExitCode -eq 0) { Invoke-GitLogged -Arguments @('push','origin',"HEAD:$ResearchBranch") | Out-Null }
      }
    }
    Write-AgentLog "Tache terminee code=${exitCode}: $($task.Name)"
    return [PSCustomObject]@{ Interrupted = $false; ExitCode = $exitCode }
  } finally { Pop-Location }
}

function New-OpusWatcher {
  param([string]$ResolvedOpusRoot)
  if (-not (Test-Path $ResolvedOpusRoot)) {
    Write-AgentLog "Dossier Opus Magnum introuvable: $ResolvedOpusRoot"
    return $null
  }
  $watcher = New-Object System.IO.FileSystemWatcher
  $watcher.Path = $ResolvedOpusRoot
  $watcher.Filter = '*.*'
  $watcher.IncludeSubdirectories = $true
  $watcher.NotifyFilter = [IO.NotifyFilters]'FileName, LastWrite, Size, DirectoryName'
  $watcher.EnableRaisingEvents = $true
  Write-AgentLog "Surveillance Opus Magnum active: $ResolvedOpusRoot"
  return $watcher
}

function Write-RuntimeStatus {
  param([string]$RuntimeStatus, [string]$Repo, [string]$ResolvedOpusRoot, [string]$CurrentTask, [Nullable[datetime]]$LastOpusChange)
  $affinity = Get-CpuAffinityMask
  Write-JsonAtomic -Path $StatusPath -Value ([ordered]@{
    status = $RuntimeStatus
    desired_state = Get-DesiredState
    pid = $PID
    user = $env:USERNAME
    repository = $Repo
    research_branch = $ResearchBranch
    opus_root = $ResolvedOpusRoot
    current_task = $CurrentTask
    max_cpu_percent = $MaxCpuPercent
    logical_cpus_allowed = $affinity.Cores
    logical_cpus_total = $affinity.Logical
    last_opus_change = if ($LastOpusChange) { $LastOpusChange.Value.ToUniversalTime().ToString('o') } else { $null }
    heartbeat = (Get-Date).ToUniversalTime().ToString('o')
  })
}

function Start-AgentProcess {
  Set-DesiredState -State 'running'
  $existing = Get-AgentProcess
  if ($existing) { Write-Host "OM Agent deja actif (PID $($existing.Id))."; return }
  $scriptPath = if (Test-Path $InstalledScript) { $InstalledScript } else { $PSCommandPath }
  $args = @('-NoProfile','-ExecutionPolicy','Bypass','-File',"`"$scriptPath`"",'-Command','Run','-MaxCpuPercent',$MaxCpuPercent,'-IdleSeconds',$IdleSeconds)
  if ($RepositoryPath) { $args += @('-RepositoryPath',"`"$RepositoryPath`"") }
  if ($ResearchBranch) { $args += @('-ResearchBranch',"`"$ResearchBranch`"") }
  if ($OpusRoot) { $args += @('-OpusRoot',"`"$OpusRoot`"") }
  $p = Start-Process -FilePath 'PowerShell.exe' -ArgumentList $args -WindowStyle Hidden -PassThru
  Write-Host "OM Agent demarre (PID $($p.Id))."
}

if ($Command -eq 'Start') { Start-AgentProcess; exit 0 }
if ($Command -eq 'Pause') { Set-DesiredState -State 'paused'; Write-Host 'OM Agent en pause demandee.'; exit 0 }
if ($Command -eq 'Stop') { Set-DesiredState -State 'stopped'; Write-Host 'Arret OM Agent demande.'; exit 0 }
if ($Command -eq 'Status') { Show-AgentStatus; exit 0 }

$existing = Get-AgentProcess
if ($existing -and $existing.Id -ne $PID) {
  Write-AgentLog "Une instance existe deja PID=$($existing.Id); sortie."
  exit 0
}
Set-Content -Path $PidPath -Value $PID -Encoding ASCII
if (-not (Test-Path $StatePath)) { Set-DesiredState -State 'running' }
$repo = Find-Repository
$resolvedOpusRoot = Resolve-OpusRoot
$watcher = New-OpusWatcher -ResolvedOpusRoot $resolvedOpusRoot
$lastOpusChange = $null
$currentTask = ''
Write-AgentLog "OM Agent session utilisateur demarre. User=$env:USERNAME PID=$PID Repo=$repo"

try {
  while ($true) {
    $desired = Get-DesiredState
    if ($desired -eq 'stopped') { break }

    if ($watcher) {
      $change = $watcher.WaitForChanged([IO.WatcherChangeTypes]::All, 1)
      if (-not $change.TimedOut) {
        $lastOpusChange = Get-Date
        Write-AgentLog "Opus change: $($change.ChangeType) $($change.Name)"
      }
    }

    if ($desired -eq 'paused') {
      Write-RuntimeStatus -RuntimeStatus 'paused' -Repo $repo -ResolvedOpusRoot $resolvedOpusRoot -CurrentTask '' -LastOpusChange $lastOpusChange
      Start-Sleep -Seconds 2
      continue
    }

    if (-not $repo) { $repo = Find-Repository }
    Write-RuntimeStatus -RuntimeStatus 'syncing' -Repo $repo -ResolvedOpusRoot $resolvedOpusRoot -CurrentTask '' -LastOpusChange $lastOpusChange
    if (-not (Sync-Repository -Repo $repo)) {
      Write-RuntimeStatus -RuntimeStatus 'blocked' -Repo $repo -ResolvedOpusRoot $resolvedOpusRoot -CurrentTask '' -LastOpusChange $lastOpusChange
      Start-Sleep -Seconds $IdleSeconds
      continue
    }

    $selected = Get-NextTask -Repo $repo
    if (-not $selected) {
      Write-RuntimeStatus -RuntimeStatus 'idle' -Repo $repo -ResolvedOpusRoot $resolvedOpusRoot -CurrentTask '' -LastOpusChange $lastOpusChange
      Start-Sleep -Seconds $IdleSeconds
      continue
    }

    $currentTask = $selected.File.Name
    Write-RuntimeStatus -RuntimeStatus 'working' -Repo $repo -ResolvedOpusRoot $resolvedOpusRoot -CurrentTask $currentTask -LastOpusChange $lastOpusChange
    $result = Invoke-Task -Repo $repo -Selected $selected -ResolvedOpusRoot $resolvedOpusRoot
    $currentTask = ''
    if ($result.Interrupted) { continue }
    Start-Sleep -Seconds 2
  }
} catch {
  Write-AgentLog "ERREUR AGENT: $($_.Exception.Message)"
  Write-RuntimeStatus -RuntimeStatus 'error' -Repo $repo -ResolvedOpusRoot $resolvedOpusRoot -CurrentTask $currentTask -LastOpusChange $lastOpusChange
  exit 1
} finally {
  if ($watcher) { $watcher.Dispose() }
  Remove-Item $PidPath -Force -ErrorAction SilentlyContinue
  Write-RuntimeStatus -RuntimeStatus 'stopped' -Repo $repo -ResolvedOpusRoot $resolvedOpusRoot -CurrentTask '' -LastOpusChange $lastOpusChange
  Write-AgentLog 'OM Agent arrete.'
}
