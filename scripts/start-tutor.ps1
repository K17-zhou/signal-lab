[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)][int]$Port = 8081,
    [switch]$Cpu,
    [ValidateNotNullOrEmpty()][string]$ModelPath = 'model/Qwen3.5-4B-Q4_K_M.gguf'
)

$ErrorActionPreference = 'Stop'
$projectPath = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runnerPath = Join-Path $projectPath '.cache/runtimes/llama-b11814/llama-server.exe'
if (-not (Test-Path -LiteralPath $runnerPath -PathType Leaf)) {
    throw 'Place the verified llama.cpp runtime under .cache/runtimes/llama-b11814.'
}
$modelLocation = if ([IO.Path]::IsPathRooted($ModelPath)) {
    $ModelPath
} else {
    Join-Path $projectPath $ModelPath
}
$modelFile = Get-Item -LiteralPath $modelLocation -ErrorAction SilentlyContinue
if (-not $modelFile -or $modelFile.PSIsContainer) {
    throw "Model file not found: $modelLocation"
}
$modelHashes = @{
    '1282439264' = 'd2387ca2dbfee2ffabce7120d3770dadca0b293052bc2f0e138fdc940d9bc7b5'
    '2497281120' = '3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597'
    '2740937888' = '00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4'
}
$expectedHash = $modelHashes[$modelFile.Length.ToString()]
if (-not $expectedHash -or
    (Get-FileHash -Algorithm SHA256 -LiteralPath $modelFile.FullName).Hash -ne $expectedHash) {
    throw "Model file does not match a verified Qwen GGUF release: $($modelFile.FullName)"
}
$modelAlias = if ($env:SIGNAL_LAB_TUTOR_MODEL) { $env:SIGNAL_LAB_TUTOR_MODEL.Trim() } else { 'signal-lab-tutor' }
$env:TEMP = (New-Item -ItemType Directory -Force (Join-Path $projectPath '.cache/tmp')).FullName
$env:TMP = $env:TEMP
$deviceArgs = if ($Cpu) { @('--device', 'none', '-ngl', '0') } else { @('--device', 'Vulkan0', '-ngl', '99') }
Push-Location $projectPath
try {
    & $runnerPath -m $modelFile.FullName --alias $modelAlias --host 127.0.0.1 --port $Port `
        -c 2048 -np 1 -t 4 -b 256 -ub 128 --reasoning off @deviceArgs
    if ($LASTEXITCODE -ne 0) { throw 'Local model service stopped with an error.' }
} finally {
    Pop-Location
}
