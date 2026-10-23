$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $projectRoot
$env:MEALLOOP_MODE = 'LOCAL'
if (-not (Test-Path '.venv/Scripts/python.exe') -or -not (Test-Path 'frontend/node_modules')) { throw 'Run ./scripts/setup.ps1 first.' }
foreach ($port in @(8080, 15173)) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    if ($listener) { throw "Port $port is already in use. Stop its existing server or use the separate fallback commands in README.md." }
}
New-Item -ItemType Directory -Force .run | Out-Null
$backendProcess = Start-Process -FilePath "$projectRoot/.venv/Scripts/python.exe" -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--app-dir', 'backend', '--host', '127.0.0.1', '--port', '8080') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput "$projectRoot/.run/backend.log" -RedirectStandardError "$projectRoot/.run/backend-error.log"
try {
    $healthy = $false
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        if ($backendProcess.HasExited) { throw "Backend stopped. Inspect .run/backend-error.log." }
        try {
            $response = Invoke-RestMethod 'http://127.0.0.1:8080/api/health' -TimeoutSec 2
            if ($response.status -eq 'ok') { $healthy = $true; break }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $healthy) { throw 'Backend did not become healthy. Inspect .run/backend-error.log.' }
    Write-Host 'MealLoop OS: http://127.0.0.1:15173   API docs: http://127.0.0.1:8080/docs'
    Write-Host 'Press Ctrl+C to stop both servers.'
    Push-Location frontend
    try { & npm.cmd run dev; if ($LASTEXITCODE -ne 0) { Write-Warning "Frontend stopped with code $LASTEXITCODE." } }
    finally { Pop-Location }
} finally {
    if (-not $backendProcess.HasExited) { Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue }
}
