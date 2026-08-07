param(
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

if ([string]::IsNullOrWhiteSpace($Python)) {
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $Python = $pythonCommand.Source
    }
}

if ([string]::IsNullOrWhiteSpace($Python) -or -not (Test-Path -LiteralPath $Python)) {
    throw "Python not found. Pass -Python <path> or install Python 3.11+ first."
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    & $Python -m venv (Join-Path $projectRoot ".venv")
}

& $venvPython -m pip install --disable-pip-version-check --prefer-binary -e "$projectRoot[dev]"

Write-Output "Environment ready: $venvPython"
