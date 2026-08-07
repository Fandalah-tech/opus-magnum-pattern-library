param(
  [string]$RepositoryPath = '',
  [int]$MaxCpuPercent = 50,
  [int]$IdleSeconds = 15
)

$ErrorActionPreference = 'Stop'
$AgentRoot = Join-Path $env:LOCALAPPDATA 'OpusMagnumAgent'
$AgentScript = Join-Path $AgentRoot 'om_local_agent.ps1'
$TaskName = 'Opus Magnum User Agent'
$OldTaskName = 'Opus Magnum Local Agent'
$RawUrl = 'https://raw.githubusercontent.com/Fandalah-tech/opus-magnum-pattern-library/main/tools/om_local_agent.ps1'
$CurrentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name

New-Item -ItemType Directory -Force -Path $AgentRoot | Out-Null
Invoke-WebRequest -Uri ($RawUrl + '?t=' + [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()) -OutFile $AgentScript -UseBasicParsing
Unblock-File -Path $AgentScript

if ($RepositoryPath) { $RepositoryPath = (Resolve-Path $RepositoryPath).Path }

# Remove the previous SYSTEM-based scheduled task if it exists. This does not
# remove or disable the legacy GitHub Actions Runner service; migration remains reversible.
if (Get-ScheduledTask -TaskName $OldTaskName -ErrorAction SilentlyContinue) {
  try { Stop-ScheduledTask -TaskName $OldTaskName -ErrorAction SilentlyContinue } catch {}
  Unregister-ScheduledTask -TaskName $OldTaskName -Confirm:$false
}

$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$AgentScript`" -Command Run -MaxCpuPercent $MaxCpuPercent -IdleSeconds $IdleSeconds"
if ($RepositoryPath) { $arguments += " -RepositoryPath `"$RepositoryPath`"" }

$action = New-ScheduledTaskAction -Execute 'PowerShell.exe' -Argument $arguments
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $CurrentUser
$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal -UserId $CurrentUser -LogonType Interactive -RunLevel Limited
$task = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'OM Agent interactif: surveille Opus Magnum, traite la file OMSIM et respecte la limite CPU configuree.'
Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null

# Convenience launchers. They execute in the signed-in user session and require no elevation.
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

# Start immediately in this user's session.
& PowerShell.exe -NoProfile -ExecutionPolicy Bypass -File $AgentScript -Command Start -MaxCpuPercent $MaxCpuPercent -IdleSeconds $IdleSeconds -RepositoryPath $RepositoryPath
Start-Sleep -Seconds 2
$status = & PowerShell.exe -NoProfile -ExecutionPolicy Bypass -File $AgentScript -Command Status

$runner = Get-Service -Name 'actions.runner.*' -ErrorAction SilentlyContinue | Select-Object -First 1
Write-Host ''
Write-Host 'OM Agent utilisateur installe.' -ForegroundColor Green
Write-Host "Utilisateur : $CurrentUser"
Write-Host "Tache au logon : $TaskName"
Write-Host "Agent : $AgentScript"
Write-Host "Commandes : $AgentRoot\OM Agent - Start/Pause/Stop/Status.cmd"
Write-Host "CPU max configure : $MaxCpuPercent%"
Write-Host "Journal : $AgentRoot\agent.log"
if ($runner) {
  Write-Host "Runner historique : $($runner.Status) ($($runner.Name)) - laisse intact pendant la migration."
}
Write-Host ''
Write-Host 'Etat courant :'
$status | ForEach-Object { Write-Host $_ }
