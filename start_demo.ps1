# One-command demo starter. Run from PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\start_demo.ps1
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\Activate.ps1")) {
    Write-Host "Virtual environment not found. Run: python -m venv .venv ; .venv\Scripts\activate ; pip install -r requirements.txt" -ForegroundColor Red
    exit 1
}
. .venv\Scripts\Activate.ps1

Write-Host "`n[1/3] Resetting demo data..." -ForegroundColor Cyan
python -m scripts.seed_demo --reset --yes

Write-Host "`n[2/3] Running tests..." -ForegroundColor Cyan
pytest -q
if ($LASTEXITCODE -ne 0) { Write-Host "Tests failed - fix before presenting!" -ForegroundColor Red }

Write-Host "`n[3/3] Starting SafeCircle at http://127.0.0.1:5000  (Ctrl+C to stop)" -ForegroundColor Green
Write-Host "Password for all demo accounts: Demo@1234`n"
Start-Process "http://127.0.0.1:5000"
flask --app app run
