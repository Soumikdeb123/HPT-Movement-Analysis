param([string]$ListenAddress = '127.0.0.1')
$ErrorActionPreference = 'Stop'
$analysisDirectory = $PSScriptRoot
$python = Join-Path $analysisDirectory '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $python)) { throw 'Install the Python 3.11 environment described in README.md first.' }
$auth = Invoke-RestMethod 'http://127.0.0.1:3000/health' -TimeoutSec 10
if ($auth.database -ne 'connected') { throw 'Start the login database and auth service first.' }
$listener = Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue
if ($listener) {
    Write-Host 'Port 8000 is already in use. Current health response:'
    Invoke-RestMethod 'http://127.0.0.1:8000/health' -TimeoutSec 10
    exit
}
$env:HPT_AUTH_API_URL = 'http://127.0.0.1:3000'
$env:HPT_API_HOST = $ListenAddress
$env:HPT_API_PORT = '8000'
$env:HPT_YOLO_MODEL = Join-Path $analysisDirectory 'yolov8x.pt'
if (!(Test-Path -LiteralPath $env:HPT_YOLO_MODEL)) { throw 'Missing yolov8x.pt model. Complete the model setup first.' }
Push-Location $analysisDirectory
try {
    Write-Host "HPT analysis service: http://${ListenAddress}:8000 (keep this terminal open)"
    if ($ListenAddress -eq '0.0.0.0') { Write-Warning 'LAN test mode: use only a trusted private network and consented test footage. Do not expose this HTTP prototype to the internet.' }
    & $python (Join-Path $analysisDirectory 'run_server.py')
    if ($LASTEXITCODE -ne 0) { throw 'Analysis service stopped with an error.' }
} finally { Pop-Location }
