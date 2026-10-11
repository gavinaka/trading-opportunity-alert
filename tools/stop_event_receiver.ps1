param(
  [int]$Port = 8787
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$StateDir = Join-Path $Root "runtime_state\processes"
$ProcessState = Join-Path $StateDir "event_receiver.json"

function Stop-IfExists([int]$ProcessId) {
  if ($ProcessId -gt 0) {
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
  }
}

if (Test-Path $ProcessState) {
  $state = Get-Content -Raw $ProcessState | ConvertFrom-Json
  Stop-IfExists ([int]$state.webhook_pid)
  Stop-IfExists ([int]$state.tunnel_pid)
}

Get-CimInstance Win32_Process |
  Where-Object {
    $_.Name -like "python*" -and
    $_.CommandLine -like "*-m trading_alerts*" -and
    $_.CommandLine -like "*serve-webhook*"
  } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Get-CimInstance Win32_Process |
  Where-Object {
    $_.Name -eq "cloudflared.exe" -and
    $_.CommandLine -like "*tunnel*" -and
    $_.CommandLine -like "*http://127.0.0.1:$Port*"
  } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

if (Test-Path $ProcessState) {
  Remove-Item -LiteralPath $ProcessState -Force
}

Write-Output "event receiver stopped"
