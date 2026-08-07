param(
  [string]$RepositoryPath = '',
  [int]$MaxCpuPercent = 50,
  [int]$IdleSeconds = 15,
  [int]$CheckSeconds = 30,
  [int]$RefreshMinutes = 60
)

$ErrorActionPreference = 'Continue'
$AgentRoot = Join-Path $env:LOCALAPPDATA 'OpusMagnumAgent'
$AgentScript = Join-Path $AgentRoot 'om_local_agent.ps1'
$PidPath = Join-Path $AgentRoot 'agent.pid'
$StatePath = Join-Path $AgentRoot 'state.json'
$WatchdogLog = Join-Path $AgentRoot 'watchdog.log'
$RawUrl = 'https://raw.githubusercontent.com/Fandalah-tech/opus-magnum-pattern-library/main/tools/om_local_agent.ps1'
New-Item -ItemType Directory -Force -Path $AgentRoot | Out-Null

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class OmPowerState {
  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern uint SetThreadExecutionState(uint esFlags);
}
'@ -ErrorAction SilentlyContinue

$ES_CONTINUOUS = [uint32]0x80000000
$ES_SYSTEM_REQUIRED = [uint32]0x00000001

function Write-WatchdogLog([string]$Message) {
  Add-Content -Path $WatchdogLog -Value ((Get-Date).ToUniversalTime().ToString('u') + ' ' + $Message) -Encoding UTF8
}

function Get-DesiredState {
  if (-not (Test-Path $StatePath)) { return 'running' }
  try {
    $state = Get-Content -Raw $StatePath | ConvertFrom-Json
    if ($state.desired_state -in @('running','paused','stopped')) { return [string]$state.desired_state }
  } catch {}
  return 'running'
}

function Get-AgentProcess {
  if (-not (Test-Path $PidPath)) { return $null }
  try {
    $pidValue = [int](Get-Content -Raw $PidPath)
    return Get-Process -Id $pidValue -ErrorAction Stop
  } catch {
    Remove-Item $PidPath -Force -ErrorAction SilentlyContinue
    return $null
  }
}

function Refresh-AgentScript {
  try {
    $tmp = "$AgentScript.download"
    $uri = $RawUrl + '?watchdog=' + [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    Invoke-WebRequest -Uri $uri -OutFile $tmp -UseBasicParsing
    if ((Get-Item $tmp).Length -lt 1000) { throw 'Downloaded agent script is unexpectedly small.' }
    Move-Item $tmp $AgentScript -Force
    Unblock-File $AgentScript -ErrorAction SilentlyContinue
    Write-WatchdogLog 'Agent script refreshed from main.'
    return $true
  } catch {
    Write-WatchdogLog ('Agent refresh failed: ' + $_.Exception.Message)
    Remove-Item "$AgentScript.download" -Force -ErrorAction SilentlyContinue
    return (Test-Path $AgentScript)
  }
}

function Start-Agent {
  if (-not (Test-Path $AgentScript)) {
    if (-not (Refresh-AgentScript)) { return }
  }
  $args = @('-NoProfile','-ExecutionPolicy','Bypass','-File',$AgentScript,'-Command','Run','-MaxCpuPercent',$MaxCpuPercent,'-IdleSeconds',$IdleSeconds)
  if ($RepositoryPath) { $args += @('-RepositoryPath',$RepositoryPath) }
  $proc = Start-Process -FilePath 'PowerShell.exe' -ArgumentList $args -WindowStyle Hidden -PassThru
  Write-WatchdogLog "Agent launched PID=$($proc.Id)."
}

Write-WatchdogLog "Watchdog started. User=$env:USERNAME PID=$PID"
$nextRefresh = Get-Date
try {
  while ($true) {
    $desired = Get-DesiredState
    $proc = Get-AgentProcess

    if ($desired -eq 'running') {
      [void][OmPowerState]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED)
      if (-not $proc) {
        if ((Get-Date) -ge $nextRefresh) {
          [void](Refresh-AgentScript)
          $nextRefresh = (Get-Date).AddMinutes([Math]::Max(5,$RefreshMinutes))
        }
        Start-Agent
        Start-Sleep -Seconds 5
      }
    } else {
      [void][OmPowerState]::SetThreadExecutionState($ES_CONTINUOUS)
    }

    Start-Sleep -Seconds ([Math]::Max(10,$CheckSeconds))
  }
} finally {
  [void][OmPowerState]::SetThreadExecutionState($ES_CONTINUOUS)
  Write-WatchdogLog 'Watchdog stopped.'
}
