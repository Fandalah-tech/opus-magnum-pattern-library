param(
  [string]$RepositoryPath = ""
)

$ErrorActionPreference = 'Stop'

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
  [Security.Principal.WindowsBuiltInRole]::Administrator
)) {
  throw "Ouvre PowerShell en tant qu'administrateur, puis relance la commande."
}

$AgentRoot = Join-Path $env:ProgramData 'OpusMagnumAgent'
$AgentScript = Join-Path $AgentRoot 'om_local_agent.ps1'
$TaskName = 'Opus Magnum Local Agent'
$RawUrl = 'https://raw.githubusercontent.com/Fandalah-tech/opus-magnum-pattern-library/main/tools/om_local_agent.ps1'

New-Item -ItemType Directory -Force -Path $AgentRoot | Out-Null
Invoke-WebRequest -Uri $RawUrl -OutFile $AgentScript -UseBasicParsing
Unblock-File -Path $AgentScript

$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$AgentScript`""
if ($RepositoryPath) {
  $resolved = (Resolve-Path $RepositoryPath).Path
  $arguments += " -RepositoryPath `"$resolved`""
}

$action = New-ScheduledTaskAction -Execute 'PowerShell.exe' -Argument $arguments
$triggers = @(
  (New-ScheduledTaskTrigger -AtStartup),
  (New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5))
)
$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 4)

$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$task = New-ScheduledTask -Action $action -Trigger $triggers -Settings $settings -Principal $principal -Description "Maintient le runner OMSIM actif, empeche la veille et synchronise le depot lorsqu'il est propre."
Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 3

$runner = Get-Service -Name 'actions.runner.*' -ErrorAction SilentlyContinue | Select-Object -First 1
$taskInfo = Get-ScheduledTaskInfo -TaskName $TaskName

Write-Host ''
Write-Host 'Agent local Opus Magnum installe.' -ForegroundColor Green
Write-Host "Tache : $TaskName"
Write-Host "Dernier resultat : $($taskInfo.LastTaskResult)"
Write-Host "Runner : $($runner.Name) - $($runner.Status)"
Write-Host "Journal : $AgentRoot\agent.log"
