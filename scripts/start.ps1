[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)][int]$Port = 8000,
    [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'
$projectPath = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pythonPath = Join-Path $projectPath '.venv/Scripts/python.exe'
$frontendPath = Join-Path $projectPath 'frontend'

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Project Python environment is missing. Follow README.md to install dependencies.'
}

if (-not $SkipBuild) {
    if (-not (Test-Path -LiteralPath (Join-Path $frontendPath 'node_modules'))) {
        throw 'Frontend dependencies are missing. Run npm ci in frontend first.'
    }
    Push-Location $frontendPath
    try {
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    }
    finally { Pop-Location }
}
elseif (-not (Test-Path -LiteralPath (Join-Path $frontendPath 'dist/index.html'))) {
    throw 'Frontend has not been built. Run this script without -SkipBuild first.'
}

Write-Host "Signal Lab: http://127.0.0.1:$Port (Ctrl+C to stop)"
Push-Location (Join-Path $projectPath 'backend')
try {
    & $pythonPath -m uvicorn app.main:app --host 127.0.0.1 --port $Port
    if ($LASTEXITCODE -ne 0) { throw 'Experiment service stopped with an error.' }
}
finally { Pop-Location }
