param([int]$Port = 8787)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$State = Join-Path $Root "runtime_state\processes\event_receiver.json"
$Heartbeat = Join-Path $Root "runtime_state\processes\webhook_heartbeat.json"

$result = [ordered]@{
  status = "stopped"
  webhook_process = $false
  tunnel_process = $false
  health_reachable = $false
  heartbeat_fresh = $false
}

if (Test-Path $State) {
  $saved = Get-Content -Raw -LiteralPath $State | ConvertFrom-Json
  $result.webhook_process = $null -ne (Get-Process -Id ([int]$saved.webhook_pid) -ErrorAction SilentlyContinue)
  $result.tunnel_process = $null -ne (Get-Process -Id ([int]$saved.tunnel_pid) -ErrorAction SilentlyContinue)
}
try {
  $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2
  $result.health_reachable = $health.status -eq "ok"
} catch {}
if (Test-Path $Heartbeat) {
  $beat = Get-Content -Raw -LiteralPath $Heartbeat | ConvertFrom-Json
  $age = (Get-Date).ToUniversalTime() - [DateTimeOffset]::Parse($beat.updated_at).UtcDateTime
  $result.heartbeat_fresh = $age.TotalSeconds -le 30
}
if ($result.webhook_process -and $result.tunnel_process -and $result.health_reachable -and $result.heartbeat_fresh) {
  $result.status = "healthy"
} elseif ($result.webhook_process -or $result.tunnel_process -or $result.health_reachable) {
  $result.status = "degraded"
}
$result | ConvertTo-Json -Depth 3
if ($result.status -ne "healthy") { exit 2 }
