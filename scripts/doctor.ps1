$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:TWS_HTTP_BACKEND = "curl"
& (Join-Path $projectRoot ".venv\Scripts\python.exe") -m x_ai_digest --config (Join-Path $projectRoot "config.json") doctor
exit $LASTEXITCODE

