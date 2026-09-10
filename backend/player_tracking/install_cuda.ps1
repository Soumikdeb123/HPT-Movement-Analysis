$ErrorActionPreference = 'Stop'

$backendRoot = $PSScriptRoot
$pythonExecutable = Join-Path $backendRoot '.venv\Scripts\python.exe'
$installTemp = Join-Path $backendRoot '..\..\runtime\pip-temp'

if (-not (Test-Path -LiteralPath $pythonExecutable)) {
    throw 'Create backend\player_tracking\.venv before installing CUDA PyTorch.'
}

# Keep the multi-gigabyte wheel and extraction files off a small system drive.
New-Item -ItemType Directory -Force -Path $installTemp | Out-Null
$env:TEMP = $installTemp
$env:TMP = $installTemp

& $pythonExecutable -m pip install --upgrade --force-reinstall --no-deps `
    torch==2.5.1 torchvision==0.20.1 `
    --index-url https://download.pytorch.org/whl/cu124

if ($LASTEXITCODE -ne 0) {
    throw 'CUDA PyTorch installation failed.'
}

& $pythonExecutable -c "import torch; print('torch:', torch.__version__); print('CUDA available:', torch.cuda.is_available()); print('device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
