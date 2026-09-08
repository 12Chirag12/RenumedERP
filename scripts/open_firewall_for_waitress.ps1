# Open an inbound TCP port on Windows Firewall for Waitress (run as Administrator).
#
# Usage:
#   .\scripts\open_firewall_for_waitress.ps1
#   .\scripts\open_firewall_for_waitress.ps1 -Port 8080
#   .\scripts\open_firewall_for_waitress.ps1 -Remove

param(
    [int]$Port = 0,
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$ruleName = "RenumedERP-Waitress"

$root = Split-Path -Parent $PSScriptRoot
if ($Port -le 0) {
    $envFile = Join-Path $root ".env"
    if (Test-Path $envFile) {
        Get-Content $envFile | ForEach-Object {
            if ($_ -match '^\s*WAITRESS_LISTEN\s*=\s*.+:(\d+)\s*$') {
                $Port = [int]$Matches[1]
            }
        }
    }
    if ($Port -le 0) { $Port = 8000 }
}

if ($Remove) {
    Remove-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
    Write-Host "Removed firewall rule '$ruleName' (if it existed)."
    exit 0
}

$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Rule '$ruleName' already exists. Removing to recreate on port $Port."
    Remove-NetFirewallRule -DisplayName $ruleName
}

New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port | Out-Null
Write-Host "Allowed inbound TCP $Port ($ruleName)."
