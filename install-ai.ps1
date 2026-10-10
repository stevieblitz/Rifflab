$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$envRoot = Join-Path $env:LOCALAPPDATA 'RiffLab\python311'
$python = Join-Path $envRoot 'Scripts\python.exe'
if (-not (Test-Path $python)) {
  Write-Host 'Creating shared RiffLab Python environment (one time)...' -ForegroundColor Cyan
  New-Item -ItemType Directory -Force -Path (Split-Path $envRoot) | Out-Null
  py -3.11 -m venv $envRoot
  if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 x64 is required.' }
}
Write-Host 'Checking existing AI installation...' -ForegroundColor Cyan
& $python (Join-Path $PSScriptRoot 'verify-ai.py')
if ($LASTEXITCODE -eq 0) {
  Write-Host 'AI is already installed. Nothing to download.' -ForegroundColor Green
  exit 0
}
Write-Host 'Installing or repairing AI dependencies in the shared environment...' -ForegroundColor Cyan
& $python -m pip install -r (Join-Path $PSScriptRoot 'requirements-full.txt')
if ($LASTEXITCODE -ne 0) { throw 'AI installation failed. Please copy the pip error output.' }
& $python (Join-Path $PSScriptRoot 'verify-ai.py')
if ($LASTEXITCODE -ne 0) { throw 'AI verification failed. See missing/broken module above.' }
Write-Host 'AI installation complete.' -ForegroundColor Green
