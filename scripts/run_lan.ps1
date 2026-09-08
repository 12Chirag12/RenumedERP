# Production-style WSGI server for LAN testing (Windows).
# Usage: from project root with venv activated —
#   .\scripts\run_lan.ps1
#   .\scripts\run_lan.ps1 -Listen "0.0.0.0:8080"
# Requires: pip install -r requirements.txt, DEBUG=False .env suitable for LAN, collectstatic done.
#
# Concurrency: default 48 threads (~30–35 concurrent users). Set WAITRESS_THREADS / WAITRESS_LISTEN in `.env`, or pass -Listen to override listen only.

param(
    [string]$Listen = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if ($Listen) {
    $env:WAITRESS_LISTEN = $Listen
}

$venvPy = Join-Path $root "venv\Scripts\python.exe"
$altVenv = Join-Path $root ".venv\Scripts\python.exe"
if (Test-Path $venvPy) {
    $python = $venvPy
} elseif (Test-Path $altVenv) {
    $python = $altVenv
} else {
    $python = "python"
}

& $python (Join-Path $root "backend\serve_waitress.py")
