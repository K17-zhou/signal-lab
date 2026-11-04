[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)][int]$Port = 8081,
    [switch]$Cpu
)

$ErrorActionPreference = 'Stop'
$projectPath = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runnerPath = Join-Path $projectPath '.cache/runtimes/llama-b11814/llama-server.exe'
$modelPath = Join-Path $projectPath '.cache/models/Qwen3-1.7B-Q4_K_M.gguf'
if (-not (Test-Path -LiteralPath $runnerPath -PathType Leaf)) {
    throw 'Place the verified llama.cpp runtime under .cache/runtimes/llama-b11814.'
}
if (-not (Test-Path -LiteralPath $modelPath -PathType Leaf)) {
    throw 'Place Qwen3-1.7B-Q4_K_M.gguf under the project .cache/models directory.'
}
if ((Get-Item -LiteralPath $modelPath).Length -ne 1282439264 -or
    (Get-FileHash -Algorithm SHA256 -LiteralPath $modelPath).Hash -ne 'd2387ca2dbfee2ffabce7120d3770dadca0b293052bc2f0e138fdc940d9bc7b5') {
    throw 'Model checksum differs from the pinned ggml-org release.'
}
$env:TEMP = (New-Item -ItemType Directory -Force (Join-Path $projectPath '.cache/tmp')).FullName
$env:TMP = $env:TEMP
$deviceArgs = if ($Cpu) { @('--device', 'none', '-ngl', '0') } else { @('--device', 'Vulkan0', '-ngl', '99') }
& $runnerPath -m $modelPath --alias qwen3-1.7b --host 127.0.0.1 --port $Port `
    -c 2048 -np 1 -t 4 -b 256 -ub 128 --reasoning off @deviceArgs
if ($LASTEXITCODE -ne 0) { throw 'Local model service stopped with an error.' }
