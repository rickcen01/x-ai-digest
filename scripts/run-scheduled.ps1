$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $projectRoot "logs"
if (-not (Test-Path -LiteralPath $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}
$logPath = Join-Path $logDir "scheduled.log"

try {
    & (Join-Path $PSScriptRoot "run.ps1") *>> $logPath
    exit $LASTEXITCODE
}
catch {
    $_ | Out-String | Add-Content -LiteralPath $logPath
    exit 1
}

