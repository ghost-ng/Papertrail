# Generate Django Environment Keys
# Usage: .\generate_env_keys.ps1 [options]
#
# Options:
#   -EnvFile       Create/update .env file in project root
#   -Output        Specify custom output file path
#   -IncludeDebug  Include DEBUG=True setting
#   -Append        Append to existing file instead of overwriting

param(
    [switch]$EnvFile,
    [string]$Output,
    [switch]$IncludeDebug,
    [switch]$Append
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot

Push-Location $ProjectRoot
try {
    # Build arguments
    $args = @()

    if ($EnvFile) {
        $args += "--env-file"
    }

    if ($Output) {
        $args += "--output"
        $args += $Output
    }

    if ($IncludeDebug) {
        $args += "--include-debug"
    }

    if ($Append) {
        $args += "--append"
    }

    # Activate venv and run command
    & "$ProjectRoot\venv\Scripts\Activate.ps1"
    python manage.py generate_env_keys @args
}
finally {
    Pop-Location
}
