$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

Write-Host "== Deal Watcher Setup ==" -ForegroundColor Cyan

if (-not (Get-Command py -ErrorAction SilentlyContinue) -and
    -not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python is not available in PATH. Install Python 3.11+ or open a new PowerShell session."
}

$PythonCommand = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { "py" }

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,
        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
    }
}

if (-not (Test-Path ".venv")) {
    Invoke-Checked { & $PythonCommand -m venv .venv } "Creating virtual environment"
}

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
Invoke-Checked { & $VenvPython -m pip install --upgrade pip } "Upgrading pip"
Invoke-Checked { & $VenvPython -m pip install -r requirements.txt } "Installing Python dependencies"
Invoke-Checked { & $VenvPython -m playwright install chromium } "Installing Playwright Chromium"
Invoke-Checked { & $VenvPython -m src.cli init } "Initializing SQLite database"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host ""
    Write-Host ".env was created. Add the Telegram Bot Token and Chat ID." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Setup completed." -ForegroundColor Green
Write-Host "Next step:"
Write-Host "  notepad .env"
Write-Host "Then preview a URL:"
Write-Host '  .\.venv\Scripts\python.exe -m src.cli preview "AMAZON_SA_URL" --target 250'
