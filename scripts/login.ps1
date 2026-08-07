$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
& (Join-Path $projectRoot ".venv\Scripts\python.exe") -m x_ai_digest --config (Join-Path $projectRoot "config.json") login-browser
exit $LASTEXITCODE
