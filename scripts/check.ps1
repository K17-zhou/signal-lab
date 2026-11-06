[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
trap {
    Write-Error -ErrorRecord $_ -ErrorAction Continue
    exit 1
}

$projectPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$pythonPath = Join-Path $projectPath '.venv/Scripts/python.exe'
$frontendPath = Join-Path $projectPath 'frontend'

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw 'Project Python environment is missing. Follow README.md to install dependencies.'
}
if (-not (Test-Path -LiteralPath (Join-Path $frontendPath 'node_modules/.bin/playwright.cmd') -PathType Leaf)) {
    throw 'Frontend dependencies are missing. Run npm ci in frontend first.'
}

function Invoke-CheckCommand {
    param([string]$Executable, [string[]]$Arguments)

    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

$runPath = $projectPath
$runName = 'check-' + [Guid]::NewGuid().ToString('N')
foreach ($part in '.cache', 'qa', 'task7', $runName) {
    $runPath = Join-Path $runPath $part
    $directory = Get-Item -LiteralPath $runPath -Force -ErrorAction SilentlyContinue
    if ($part -eq $runName -and $null -ne $directory) {
        throw "Check artifact directory already exists at $runPath"
    }
    if ($null -eq $directory) {
        $directory = [IO.Directory]::CreateDirectory($runPath)
    }
    if ($directory -isnot [IO.DirectoryInfo] -or ($directory.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Check artifacts require a project-local directory at $runPath"
    }
}

$tempPath = [IO.Directory]::CreateDirectory((Join-Path $runPath 'tmp')).FullName
$stopFile = Join-Path $runPath 'stop-fixture'
$environment = @{
    TEMP = $tempPath
    TMP = $tempPath
    TMPDIR = $tempPath
    PYTHONUTF8 = '1'
    PYTHONDONTWRITEBYTECODE = '1'
    npm_config_cache = Join-Path $runPath 'npm'
    PLAYWRIGHT_REUSE_FIXTURE = '1'
    SIGNAL_LAB_DB_PATH = Join-Path $runPath 'pytest.sqlite3'
    SIGNAL_LAB_STUDY_ASSIGNMENTS = ''
    SIGNAL_LAB_E2E_STOP_FILE = $stopFile
}
$previousEnvironment = @{}
$fixture = $null

Write-Host "Check artifacts: $runPath"
Push-Location -LiteralPath (Join-Path $projectPath 'backend')
try {
    foreach ($name in $environment.Keys) {
        $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name)
        Set-Item -LiteralPath "Env:$name" -Value $environment[$name]
    }

    Invoke-CheckCommand $pythonPath @('-m', 'pytest', '-q', '--basetemp', (Join-Path $tempPath 'pytest'))

    Set-Location -LiteralPath $frontendPath
    Invoke-CheckCommand 'npm.cmd' @('test', '--', '--run')
    Invoke-CheckCommand 'npm.cmd' @('run', 'build')

    $fixtureUrl = 'http://127.0.0.1:18082'
    $fixtureLog = Join-Path $runPath 'fixture.stderr.log'
    $fixtureStart = @{
        FilePath = $pythonPath
        ArgumentList = 'frontend/e2e/serve_study.py'
        WorkingDirectory = $projectPath
        WindowStyle = 'Hidden'
        RedirectStandardOutput = Join-Path $runPath 'fixture.stdout.log'
        RedirectStandardError = $fixtureLog
        PassThru = $true
    }
    $fixture = Start-Process @fixtureStart

    $startup = [Diagnostics.Stopwatch]::StartNew()
    $health = $null
    while ($startup.Elapsed.TotalSeconds -lt 30 -and -not $fixture.HasExited) {
        # The launch log confirms this fixture bound the port before reusing it.
        if (Select-String -LiteralPath $fixtureLog -SimpleMatch "Uvicorn running on $fixtureUrl" -Quiet) {
            try {
                $health = Invoke-RestMethod -Uri "$fixtureUrl/api/health" -UseBasicParsing -TimeoutSec 2
            } catch {
                $health = $null
            }
            if ($health -and $health.status -eq 'ok') { break }
        }
        Start-Sleep -Milliseconds 200
    }
    if ($fixture.HasExited -or -not $health -or $health.status -ne 'ok') {
        throw "Browser test fixture did not become healthy at $fixtureUrl. See $fixtureLog"
    }

    Invoke-CheckCommand 'npx.cmd' @('--no-install', 'playwright', 'test', '--output', (Join-Path $runPath 'playwright'))
} finally {
    try {
        if ($null -ne $fixture) {
            try {
                if (-not $fixture.HasExited) {
                    # Signal this check's fixture, then wait for its venv launcher to exit.
                    New-Item -ItemType File -Path $stopFile | Out-Null
                    if (-not $fixture.WaitForExit(10000)) {
                        throw "Browser test fixture did not stop. See $fixtureLog"
                    }
                }
            } finally {
                $fixture.Dispose()
            }
        }
    } finally {
        foreach ($name in $previousEnvironment.Keys) {
            if ($null -eq $previousEnvironment[$name]) {
                Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
            } else {
                Set-Item -LiteralPath "Env:$name" -Value $previousEnvironment[$name]
            }
        }
        Pop-Location
    }
}

exit 0
