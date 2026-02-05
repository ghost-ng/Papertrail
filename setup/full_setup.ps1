# Full Development Setup Script
# This script runs all setup commands in sequence:
# 1. Generate environment keys
# 2. Run migrations
# 3. Create mock data
# 4. Setup admin group
#
# Usage: .\full_setup.ps1 [options]
#
# Options:
#   -SkipEnvKeys     Skip generating environment keys
#   -SkipMigrations  Skip running migrations
#   -SkipMockData    Skip creating mock data
#   -UsersPerOffice  Number of users per office (default: 5)
#   -Password        Password for mock users (default: password123)
#   -ClearMockData   Clear existing mock data before creating

param(
    [switch]$SkipEnvKeys,
    [switch]$SkipMigrations,
    [switch]$SkipMockData,
    [int]$UsersPerOffice = 5,
    [string]$Password = "password123",
    [switch]$ClearMockData
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host ""
Write-Host "================================" -ForegroundColor Cyan
Write-Host "  Papertrail Development Setup  " -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

Push-Location $ProjectRoot
try {
    # Activate virtual environment
    Write-Host "Activating virtual environment..." -ForegroundColor Yellow
    & "$ProjectRoot\venv\Scripts\Activate.ps1"
    Write-Host ""

    # Step 1: Generate environment keys
    if (-not $SkipEnvKeys) {
        Write-Host "Step 1: Checking environment keys..." -ForegroundColor Cyan
        Write-Host "-" * 40

        if (-not (Test-Path "$ProjectRoot\.env")) {
            Write-Host "Generating .env file..." -ForegroundColor Yellow
            python manage.py generate_env_keys --env-file --include-debug
        } else {
            Write-Host ".env file already exists, skipping generation" -ForegroundColor Green
            Write-Host "(Delete .env and re-run to regenerate)"
        }
        Write-Host ""
    }

    # Step 2: Run migrations
    if (-not $SkipMigrations) {
        Write-Host "Step 2: Running migrations..." -ForegroundColor Cyan
        Write-Host "-" * 40

        python manage.py migrate
        Write-Host ""
    }

    # Step 3: Setup admin group
    Write-Host "Step 3: Setting up admin group..." -ForegroundColor Cyan
    Write-Host "-" * 40

    python manage.py setup_admin_group
    Write-Host ""

    # Step 4: Create mock data
    if (-not $SkipMockData) {
        Write-Host "Step 4: Creating mock data..." -ForegroundColor Cyan
        Write-Host "-" * 40

        $mockArgs = @()
        $mockArgs += "--users-per-office"
        $mockArgs += $UsersPerOffice
        $mockArgs += "--password"
        $mockArgs += $Password

        if ($ClearMockData) {
            $mockArgs += "--clear"
        }

        python manage.py create_mock_data @mockArgs
        Write-Host ""
    }

    # Summary
    Write-Host "================================" -ForegroundColor Green
    Write-Host "  Setup Complete!               " -ForegroundColor Green
    Write-Host "================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "  1. Create a superuser:  python manage.py createsuperuser"
    Write-Host "  2. Run the server:      python manage.py runserver"
    Write-Host "  3. Open browser:        http://localhost:8000"
    Write-Host ""
    Write-Host "Mock user credentials:" -ForegroundColor Yellow
    Write-Host "  Password: $Password"
    Write-Host "  (Check console output above for email addresses)"
    Write-Host ""
}
finally {
    Pop-Location
}
