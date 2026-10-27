<#
.SYNOPSIS
    Install the backend into a virtual environment and build the frontend.
.PARAMETER SkipFrontend
    Skip installing frontend dependencies and building the frontend.
#>
param([switch]$SkipFrontend)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Venv = if ($env:YV_VENV) { $env:YV_VENV } else { Join-Path $Root "backend\.venv" }
$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }

Write-Host "Creating virtual environment at $Venv"
& $Python -m venv $Venv
if ($LASTEXITCODE -ne 0) { throw "Failed to create the virtual environment." }
$VenvPython = Join-Path $Venv "Scripts\python.exe"
& $VenvPython -m pip install --quiet --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Failed to upgrade pip." }
& $VenvPython -m pip install --quiet -e "$(Join-Path $Root 'backend')[dev]"
if ($LASTEXITCODE -ne 0) { throw "Failed to install the backend." }

if ($SkipFrontend) {
    Write-Host "Skipping the frontend build."
}
elseif (Get-Command npm.cmd -ErrorAction SilentlyContinue) {
    Push-Location (Join-Path $Root "frontend")
    try {
        npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw "npm ci failed." }
        npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw "The frontend build failed." }
    }
    finally {
        Pop-Location
    }
}
else {
    throw "npm was not found. Install Node.js 20 or later, or rerun with -SkipFrontend."
}

Write-Host "Setup complete. Start the application with scripts\start.ps1"
