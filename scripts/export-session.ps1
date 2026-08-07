param(
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Output)) {
    $Output = Join-Path $projectRoot "data\x-session.xsession"
}
& (Join-Path $projectRoot ".venv\Scripts\python.exe") -m x_ai_digest --config (Join-Path $projectRoot "config.json") export-session --output $Output
exit $LASTEXITCODE

