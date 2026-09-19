$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$projectPython = Join-Path $PSScriptRoot ".venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $projectPython)) {
    $bundledPython = Join-Path $env:USERPROFILE ".cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -m venv .venv
    } elseif (Test-Path -LiteralPath $bundledPython) {
        & $bundledPython -m venv .venv
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv .venv
    } else {
        throw "Install Python 3.12, then run setup.ps1 again."
    }
    if ($LASTEXITCODE -ne 0) { throw "Creating the Python environment failed." }
}
& $projectPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Installing dependencies failed. Check your network connection." }
Write-Host "Setup complete. Run: powershell -ExecutionPolicy Bypass -File .\run.ps1"

