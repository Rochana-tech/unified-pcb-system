param(
    [ValidateSet("demo", "external")][string]$Mode = "demo",
    [int]$Port = 8002,
    [int]$CorrectionSeconds = 20,
    [switch]$NoDemoBackup,
    [switch]$Mqtt
)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$projectPython = Join-Path $PSScriptRoot ".venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $projectPython)) {
    & (Join-Path $PSScriptRoot "setup.ps1")
    if ($LASTEXITCODE -ne 0) { throw "Setup failed." }
}
$launchArgs = @("main.py", "--mode", $Mode, "--port", "$Port", "--correction-seconds", "$CorrectionSeconds")
if ($NoDemoBackup) { $launchArgs += "--no-demo-backup" }
if ($Mqtt) { $launchArgs += "--mqtt" }
& $projectPython @launchArgs

