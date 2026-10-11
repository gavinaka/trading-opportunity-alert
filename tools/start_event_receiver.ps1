param(
  [int]$Port = 8787,
  [switch]$NotifyCandidates
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Cloudflared = Join-Path $Root "tools\cloudflared\cloudflared.exe"
$StateDir = Join-Path $Root "runtime_state\processes"
$WebhookStdout = Join-Path $Root "runtime_state\webhooks\server_stdout.log"
$WebhookStderr = Join-Path $Root "runtime_state\webhooks\server_stderr.log"
$TunnelStdout = Join-Path $Root "runtime_state\webhooks\cloudflared_stdout.log"
$TunnelStderr = Join-Path $Root "runtime_state\webhooks\cloudflared_stderr.log"
$ProcessState = Join-Path $StateDir "event_receiver.json"

if (-not (Test-Path $Python)) {
  throw "Python venv not found: $Python"
}
if (-not (Test-Path $Cloudflared)) {
  throw "cloudflared not found: $Cloudflared"
}
$WebhookSecret = [Environment]::GetEnvironmentVariable("WEBHOOK_SECRET", "Process")
if ([string]::IsNullOrWhiteSpace($WebhookSecret)) {
  $WebhookSecret = [Environment]::GetEnvironmentVariable("WEBHOOK_SECRET", "User")
}
if ([string]::IsNullOrWhiteSpace($WebhookSecret)) {
  throw "WEBHOOK_SECRET is required before starting a public tunnel. Rotate/configure it first."
}
$env:WEBHOOK_SECRET = $WebhookSecret

New-Item -ItemType Directory -Force $StateDir | Out-Null
New-Item -ItemType Directory -Force (Split-Path -Parent $WebhookStdout) | Out-Null

function Get-WebhookProcesses {
  Get-CimInstance Win32_Process |
    Where-Object {
      $_.Name -like "python*" -and
      $_.CommandLine -like "*-m trading_alerts*" -and
      $_.CommandLine -like "*serve-webhook*"
    }
}

function Get-TunnelProcesses {
  Get-CimInstance Win32_Process |
    Where-Object {
      $_.Name -eq "cloudflared.exe" -and
      $_.CommandLine -like "*tunnel*" -and
      $_.CommandLine -like "*http://127.0.0.1:$Port*"
    }
}

function Get-TunnelUrl {
  if (-not (Test-Path $TunnelStderr)) {
    return $null
  }
  $match = Select-String -Path $TunnelStderr -Pattern 'https://[-a-zA-Z0-9]+\.trycloudflare\.com' | Select-Object -Last 1
  if ($null -eq $match) {
    return $null
  }
  return $match.Matches[0].Value
}

function Start-TunnelWithRetry {
  Set-Content -Encoding UTF8 -Path $TunnelStdout -Value ""
  Set-Content -Encoding UTF8 -Path $TunnelStderr -Value ""
  for ($attempt = 1; $attempt -le 3; $attempt++) {
    $process = Start-Process `
      -FilePath $Cloudflared `
      -ArgumentList @("tunnel", "--url", "http://127.0.0.1:$Port") `
      -WorkingDirectory $Root `
      -WindowStyle Hidden `
      -RedirectStandardOutput $TunnelStdout `
      -RedirectStandardError $TunnelStderr `
      -PassThru

    for ($i = 0; $i -lt 12; $i++) {
      Start-Sleep -Seconds 1
      $url = Get-TunnelUrl
      if ($url) {
        return @{ process = $process; url = $url }
      }
      if ($process.HasExited) {
        break
      }
    }

    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
  }
  throw "cloudflared quick tunnel failed to provide a trycloudflare URL; see $TunnelStderr"
}

Get-WebhookProcesses | ForEach-Object {
  Stop-Process -Id $_.ProcessId -Force
}

$webhookArgs = @("-m", "trading_alerts", "--config", "config.json", "serve-webhook", "--port", "$Port", "--require-secret")
if ($NotifyCandidates) {
  $webhookArgs += "--notify-candidates"
}
$webhook = Start-Process `
  -FilePath $Python `
  -ArgumentList $webhookArgs `
  -WorkingDirectory $Root `
  -WindowStyle Hidden `
  -RedirectStandardOutput $WebhookStdout `
  -RedirectStandardError $WebhookStderr `
  -PassThru

Start-Sleep -Seconds 1

$tunnels = @(Get-TunnelProcesses)
if ($tunnels.Count -eq 0) {
  $tunnelResult = Start-TunnelWithRetry
  $tunnel = $tunnelResult.process
  $publicUrl = $tunnelResult.url
} else {
  $tunnel = Get-Process -Id $tunnels[0].ProcessId
  $publicUrl = Get-TunnelUrl
  if (-not $publicUrl) {
    throw "existing cloudflared tunnel found but no trycloudflare URL is available in $TunnelStderr"
  }
}

$payload = [ordered]@{
  started_at = (Get-Date).ToString("o")
  port = $Port
  webhook_pid = $webhook.Id
  tunnel_pid = $tunnel.Id
  notify_candidates = [bool]$NotifyCandidates
  public_url = $publicUrl
  webhook_url = "$publicUrl/tv-webhook"
  webhook_url_hint = "Check runtime_state\webhooks\cloudflared_stderr.log for the trycloudflare URL."
}
$payload | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 $ProcessState
$payload | ConvertTo-Json -Depth 4
