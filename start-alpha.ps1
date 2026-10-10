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
& $python (Join-Path $PSScriptRoot 'verify-ui.py')
if ($LASTEXITCODE -ne 0) {
  Write-Host 'Installing missing UI packages...' -ForegroundColor Cyan
  & $python -m pip install -r (Join-Path $PSScriptRoot 'requirements-preview.txt')
  if ($LASTEXITCODE -ne 0) { throw 'UI dependency installation failed.' }
  & $python (Join-Path $PSScriptRoot 'verify-ui.py')
  if ($LASTEXITCODE -ne 0) { throw 'UI verification failed.' }
}
Write-Host 'Starting RiffLab Alpha...' -ForegroundColor Cyan
& $python (Join-Path $PSScriptRoot 'app.py')
if ($LASTEXITCODE -ne 0) { throw 'RiffLab exited with an error. Copy the error output.' }
