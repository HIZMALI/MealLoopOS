param([switch]$Run)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $projectRoot
$pythonVersion = & python -c "import sys; print(sys.version_info >= (3, 11))"
if ($LASTEXITCODE -ne 0 -or $pythonVersion -ne 'True') { throw 'Python 3.11+ is required on PATH.' }
$nodeVersionOk = & node -e "const [a,b]=process.versions.node.split('.').map(Number);process.exit((a===20&&b>=19)||(a===22&&b>=12)||a>=23?0:1)"
if ($LASTEXITCODE -ne 0) { throw 'Node.js 20.19+ or 22.12+ is required. Node 24 LTS is recommended.' }
if (-not (Test-Path '.venv/Scripts/python.exe')) { & python -m venv .venv }
if ($LASTEXITCODE -ne 0) { throw 'Could not create Python environment.' }
& ./.venv/Scripts/python.exe -m pip install -r backend/requirements-lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
Push-Location frontend
try { & npm.cmd ci; if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' } }
finally { Pop-Location }
$workbook = 'data/raw/Food waste data school Finland 2024-2025.xlsx'
if (-not (Test-Path $workbook)) {
    & ./.venv/Scripts/python.exe scripts/download_dataset.py
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Official data unavailable. Start the app empty and upload the workbook manually.' }
}
if (Test-Path $workbook) {
    & ./.venv/Scripts/python.exe scripts/import_dataset.py $workbook
    if ($LASTEXITCODE -ne 0) { throw 'Dataset validation failed. Review the errors above.' }
}
Write-Host 'Setup complete. Run ./scripts/start.ps1 to launch MealLoop OS.'
if ($Run) { & "$PSScriptRoot/start.ps1" }
