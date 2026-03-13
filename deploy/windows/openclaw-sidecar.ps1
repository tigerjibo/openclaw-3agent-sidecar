param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot | Split-Path -Parent)
)

$envFile = Join-Path $ProjectRoot '.env'
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -match '^\s*$') {
            return
        }
        $parts = $_ -split '=', 2
        if ($parts.Count -eq 2) {
            [System.Environment]::SetEnvironmentVariable($parts[0], $parts[1])
        }
    }
}

Push-Location $ProjectRoot
try {
    & openclaw-sidecar
}
finally {
    Pop-Location
}
