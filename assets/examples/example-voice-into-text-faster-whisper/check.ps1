# Quick check: is this computer able to run faster-whisper, and how fast?
# Usage:  .\check.ps1

$ErrorActionPreference = "Continue"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

Write-Host ""
Write-Host "=== System ===" -ForegroundColor Cyan

$os = Get-CimInstance Win32_OperatingSystem
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$ramGB = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
$gpus = @(Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name)
$freeGB = [math]::Round((Get-PSDrive C).Free / 1GB, 1)

Write-Host ("OS      : {0} (build {1})" -f $os.Caption, $os.BuildNumber)
Write-Host ("CPU     : {0}" -f $cpu.Name.Trim())
Write-Host ("Cores   : {0} physical / {1} logical" -f $cpu.NumberOfCores, $cpu.NumberOfLogicalProcessors)
Write-Host ("RAM     : {0} GB" -f $ramGB)
Write-Host ("GPU     : {0}" -f ($gpus -join ", "))
Write-Host ("Disk C: : {0} GB free" -f $freeGB)

$hasCuda = $gpus | Where-Object { $_ -match "NVIDIA" }
if ($hasCuda) {
    Write-Host "CUDA    : NVIDIA GPU detected - GPU transcription is possible" -ForegroundColor Green
} else {
    Write-Host "CUDA    : no NVIDIA GPU - runs on CPU (int8), which is fine" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Verdict ===" -ForegroundColor Cyan

$problems = @()
if ($cpu.NumberOfLogicalProcessors -lt 4) { $problems += "only $($cpu.NumberOfLogicalProcessors) CPU threads; expect slow transcription" }
if ($ramGB -lt 4) { $problems += "less than 4 GB RAM; use tiny or base models only" }
elseif ($ramGB -lt 8) { $problems += "less than 8 GB RAM; prefer small or base models" }
if ($freeGB -lt 10) { $problems += "less than 10 GB free disk; models need 3-5 GB" }

if ($problems.Count -eq 0) {
    Write-Host "OK - this machine can run every whisper model." -ForegroundColor Green
    Write-Host "Recommended default: small (good accuracy, ~3x realtime)"
} else {
    foreach ($p in $problems) { Write-Host "Note: $p" -ForegroundColor Yellow }
}

Write-Host ""
Write-Host "=== Python environment ===" -ForegroundColor Cyan

$uv = Get-Command uv -ErrorAction SilentlyContinue
if ($uv) {
    Write-Host ("uv      : {0}" -f (& uv --version 2>&1))
} else {
    Write-Host "uv      : not found  (install: winget install --id=astral-sh.uv -e)" -ForegroundColor Yellow
}

$python = Join-Path $here ".venv\Scripts\python.exe"
if (Test-Path $python) {
    Write-Host ("venv    : {0}" -f $python)
    & $python -c @"
import importlib.metadata as md
for pkg in ('faster-whisper', 'ctranslate2', 'av', 'onnxruntime'):
    try:
        print(f'{pkg:14s}: {md.version(pkg)}')
    except md.PackageNotFoundError:
        print(f'{pkg:14s}: MISSING')
import ctranslate2
print(f'CUDA devices  : {ctranslate2.get_cuda_device_count()}')
"@
} else {
    Write-Host "venv    : not created yet" -ForegroundColor Yellow
    Write-Host "          run: uv sync"
}

Write-Host ""
Write-Host "=== Model cache ===" -ForegroundColor Cyan
$cache = Join-Path $env:USERPROFILE ".cache\huggingface\hub"
$models = @()
if (Test-Path $cache) {
    $models = @(Get-ChildItem $cache -Directory |
                Where-Object { $_.Name -like "models--Systran--faster-whisper-*" })
}
if ($models.Count -gt 0) {
    Write-Host "$cache"
    foreach ($m in $models) {
        $bytes = (Get-ChildItem $m.FullName -Recurse -File -ErrorAction SilentlyContinue |
                  Measure-Object Length -Sum).Sum
        Write-Host ("  - {0,-12} {1,6} MB" -f ($m.Name -replace '^models--Systran--faster-whisper-', ''),
                                             [math]::Round($bytes / 1MB))
    }
} else {
    Write-Host "empty - the first run will download the chosen model"
}

Write-Host ""
