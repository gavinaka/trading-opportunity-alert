Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "Python venv not found" }

Push-Location $Root
try {
  & $Python -m pytest -q
  if ($LASTEXITCODE -ne 0) { throw "pytest failed" }
  & $Python -m compileall -q src
  if ($LASTEXITCODE -ne 0) { throw "compileall failed" }

  $patterns = @(
    'https://api\.telegram\.org/bot[0-9]{6,12}:[A-Za-z0-9_-]{20,}',
    '(?i)(token|secret|password|credential)\s*[:=]\s*["''][A-Za-z0-9_./:+-]{16,}["'']',
    '-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----'
  )
  $matchedFiles = @()
  foreach ($pattern in $patterns) {
    $hits = & rg -l --hidden `
      -g '!.git/**' -g '!.venv/**' -g '!runtime_state/**' -g '!tools/cloudflared/**' `
      -g '*.py' -g '*.ps1' -g '*.json' -g '*.md' `
      --pcre2 -- $pattern .
    if ($LASTEXITCODE -eq 0) { $matchedFiles += $hits }
    elseif ($LASTEXITCODE -ne 1) { throw "secret scan failed" }
  }
  $matchedFiles = @($matchedFiles | Sort-Object -Unique)
  if ($matchedFiles.Count -gt 0) {
    throw "Potential embedded credentials detected in: $($matchedFiles -join ', ')"
  }
  Write-Output "[PASS] tests, syntax and credential-pattern scan"
} finally {
  Pop-Location
}
