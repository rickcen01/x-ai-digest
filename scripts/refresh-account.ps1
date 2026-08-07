param(
    [switch]$Manual
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:TWS_HTTP_BACKEND = "curl"
$arguments = @("-m", "x_ai_digest", "--config", (Join-Path $projectRoot "config.json"), "refresh-account")
if ($Manual) { $arguments += "--manual" }

& (Join-Path $projectRoot ".venv\Scripts\python.exe") @arguments
exit $LASTEXITCODE
