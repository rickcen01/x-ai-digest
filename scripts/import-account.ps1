param(
    [string]$Source = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if ([string]::IsNullOrWhiteSpace($Source)) {
    $computerFolder = ([string][char]0x7535) + ([string][char]0x8111)
    $Source = Join-Path "D:\" "$computerFolder\Crawler-main\project\Ticketbully\twscrape-main\twscrape\accounts.db"
}
$arguments = @("-m", "x_ai_digest", "--config", (Join-Path $projectRoot "config.json"), "import-account", "--source", $Source)
if ($Force) { $arguments += "--force" }

& $python @arguments
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$target = Join-Path $projectRoot "data\accounts.db"
if (Test-Path -LiteralPath $target) {
    & icacls.exe $target /inheritance:r /grant:r "$env:USERNAME`:(R,W)" | Out-Null
}
