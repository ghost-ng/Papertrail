# Create Mock Data for Development
# Usage: .\create_mock_data.ps1 [options]
#
# Options:
#   -UsersPerOffice  Number of users per office (default: 5)
#   -Password        Password for all mock users (default: password123)
#   -Clear           Clear existing mock data first
#   -DryRun          Show what would be created without creating

param(
    [int]$UsersPerOffice = 5,
    [string]$Password = "password123",
    [switch]$Clear,
    [switch]$DryRun
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot

Push-Location $ProjectRoot
try {
    # Build arguments
    $args = @()
    $args += "--users-per-office"
    $args += $UsersPerOffice

    $args += "--password"
    $args += $Password

    if ($Clear) {
        $args += "--clear"
    }

    if ($DryRun) {
        $args += "--dry-run"
    }

    # Activate venv and run command
    & "$ProjectRoot\venv\Scripts\Activate.ps1"
    python manage.py create_mock_data @args
}
finally {
    Pop-Location
}
