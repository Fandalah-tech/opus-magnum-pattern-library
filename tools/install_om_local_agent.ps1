param(
  [string]$RepositoryPath = '',
  [int]$MaxCpuPercent = 50,
  [int]$IdleSeconds = 15
)

$ErrorActionPreference = 'Stop'
$AgentRoot = Join-Path $env:LOCALAPPDATA 'OpusMagnumAgent'
$AgentScript = Join-Path $AgentRoot 'om_local_agent.ps1'
$WatchdogScript = Join-Path $AgentRoot 'om_agent_watchdog.ps1'
$TaskName = 'Opus Magnum User Agent'
$OldTaskName = 'Opus Magnum Local Agent'
$AgentRawUrl = 'https://raw.githubusercontent.com/Fandalah-tech/opus-magnum-pattern-library/main/tools/om_local_agent.ps1'
$WatchdogRawUrl = 'https://raw.githubusercontent.com/Fandalah-tech/opus-magnum-pattern-library/main/tools/om_agent_watchdog.ps1'
$CurrentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name

New-Item -ItemType Directory -Force -Path $AgentRoot | Out-Null
$stamp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
Invoke-WebRequest -Uri ($AgentRawUrl + '?t=' + $stamp) -OutFile $AgentScript -UseBasicParsing
Invoke-WebRequest -Uri ($WatchdogRawUrl + '?t=' + $stamp) -OutFile $WatchdogScript -UseBasicParsing
Unblock-File -Path $AgentScript -ErrorAction SilentlyContinue
Unblock-File -Path $WatchdogScript -ErrorAction SilentlyContinue

if ($RepositoryPath) { $RepositoryPath = (Resolve-Path $RepositoryPath).Path }

if (Get-ScheduledTask -TaskName $OldTaskName -ErrorAction SilentlyContinue) {
  try { Stop-ScheduledTask -TaskName $OldTaskName -ErrorAction SilentlyContinue } catch {}
  Unregister-ScheduledTask -TaskName $OldTaskName -Confirm:$false
}
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
  try { Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue } catch {}
}

$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$WatchdogScript`" -MaxCpuPercent $MaxCpuPercent -IdleSeconds $IdleSeconds"
if ($RepositoryPath) { $arguments += " -RepositoryPath `"$RepositoryPath`"" }

$action = New-ScheduledTaskAction -Execute 'PowerShell.exe' -Argument $arguments
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $CurrentUser
$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -RestartCount 999 `
  -RestartInterval (New-TimeSpan -Minutes 1) `
  -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal -UserId $CurrentUser -LogonType Interactive -RunLevel Limited
$task = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'OM Agent watchdog interactif: relance automatiquement l agent, empeche la veille pendant le calcul et traite la file OMSIM.'
Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null

$commands = @{
  'OM Agent - Start.cmd' = 'Start'
  'OM Agent - Pause.cmd' = 'Pause'
  'OM Agent - Stop.cmd' = 'Stop'
  'OM Agent - Status.cmd' = 'Status'
}
foreach ($entry in $commands.GetEnumerator()) {
  $path = Join-Path $AgentRoot $entry.Key
  $line = "@echo off`r`nPowerShell.exe -NoProfile -ExecutionPolicy Bypass -File `"$AgentScript`" -Command $($entry.Value) -MaxCpuPercent $MaxCpuPercent -IdleSeconds $IdleSeconds"
  if ($RepositoryPath) { $line += " -RepositoryPath `"$RepositoryPath`"" }
  $line += "`r`n"
  Set-Content -Path $path -Value $line -Encoding ASCII
}

Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 4
$status = & PowerShell.exe -NoProfile -ExecutionPolicy Bypass -File $AgentScript -Command Status

$runner = Get-Service -Name 'actions.runner.*' -ErrorAction SilentlyContinue | Select-Object -First 1
Write-Host ''
Write-Host 'OM Agent utilisateur installe.' -ForegroundColor Green
Write-Host "Utilisateur : $CurrentUser"
Write-Host "Tache watchdog au logon : $TaskName"
Write-Host "Agent : $AgentScript"
Write-Host "Watchdog : $WatchdogScript"
Write-Host "Commandes : $AgentRoot\OM Agent - Start/Pause/Stop/Status.cmd"
Write-Host "CPU max configure : $MaxCpuPercent%"
Write-Host "Journal agent : $AgentRoot\agent.log"
Write-Host "Journal watchdog : $AgentRoot\watchdog.log"
if ($runner) {
  Write-Host "Runner historique : $($runner.Status) ($($runner.Name)) - non requis par l OM Agent."
}
Write-Host ''
Write-Host 'Etat courant :'
$status | ForEach-Object { Write-Host $_ }
