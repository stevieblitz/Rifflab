# Install the separately downloaded RiffLab AI Engine for the current Windows user.
# Usage: powershell -ExecutionPolicy Bypass -File install-ai-engine.ps1 -SourceFolder "C:\path\to\RiffLabAI"
param([Parameter(Mandatory=$true)][string]$SourceFolder)
$ErrorActionPreference = 'Stop'
$source = (Resolve-Path $SourceFolder).Path
if (!(Test-Path (Join-Path $source 'RiffLabAI.exe'))) { throw 'RiffLabAI.exe not found in SourceFolder.' }
$target = Join-Path $env:LOCALAPPDATA 'RiffLab\AI'
New-Item -ItemType Directory -Path $target -Force | Out-Null
Copy-Item -Path (Join-Path $source '*') -Destination $target -Recurse -Force
if (!(Test-Path (Join-Path $target 'RiffLabAI.exe'))) { throw 'AI Engine installation failed.' }
Write-Host "AI Engine installed to $target"
