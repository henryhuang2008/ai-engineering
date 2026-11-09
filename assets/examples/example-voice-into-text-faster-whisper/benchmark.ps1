# Benchmark the model sizes on one file.
# Usage:  .\benchmark.ps1 "D:\videos\sample.mp4" --models base small medium

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $here ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "Run setup first: uv sync" -ForegroundColor Yellow
    exit 1
}

$env:PYTHONUTF8 = "1"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Push-Location $here
try {
    & $python (Join-Path $here "benchmark.py") @args
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
