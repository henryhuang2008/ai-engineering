# Run transcribe.py using this folder's virtual environment.
# Usage:  .\transcribe.ps1 "D:\videos\my video.mp4" --model medium --language zh
# (No param block on purpose: every argument is passed through unchanged,
#  so flags like -o or -m are not captured by PowerShell parameter binding.)

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $here ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "Virtual environment not found. Run this once:" -ForegroundColor Yellow
    Write-Host "  uv sync"
    exit 1
}

$env:PYTHONUTF8 = "1"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

if ($args.Count -eq 0) {
    & $python (Join-Path $here "transcribe.py") --help
    exit $LASTEXITCODE
}

& $python (Join-Path $here "transcribe.py") @args
exit $LASTEXITCODE
