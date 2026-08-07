param(
    [switch]$Preview
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:TWS_HTTP_BACKEND = "curl"
$arguments = @("-m", "x_ai_digest", "--config", (Join-Path $projectRoot "config.json"), "run")
if ($Preview) { $arguments += "--preview" }

& (Join-Path $projectRoot ".venv\Scripts\python.exe") @arguments
exit $LASTEXITCODE

