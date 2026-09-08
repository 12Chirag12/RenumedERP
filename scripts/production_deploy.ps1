# Production preparation: migrate DB, collect static files, run deployment checks.
# Run from the project root (or anywhere — script cds to repo root).
#
# Usage:
#   .\scripts\production_deploy.ps1
#   .\scripts\production_deploy.ps1 -SkipCheck   # skip `manage.py check --deploy`

param(
    [switch]$SkipCheck
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$venvPy = Join-Path $root "venv\Scripts\python.exe"
$altVenv = Join-Path $root ".venv\Scripts\python.exe"
if (Test-Path $venvPy) {
    $python = $venvPy
} elseif (Test-Path $altVenv) {
    $python = $altVenv
} else {
    throw "No venv found. Create venv at $venvPy and install requirements."
}

$manage = Join-Path $root "manage.py"
Write-Host "Using: $python"
Write-Host "Running migrations..."
& $python $manage migrate --noinput
Write-Host "Collecting static files..."
& $python $manage collectstatic --noinput
if (-not $SkipCheck) {
    Write-Host "Deployment checks..."
    & $python $manage check --deploy
}
Write-Host "Done."
