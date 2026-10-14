$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
& (Join-Path $projectRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'runner.py') uninstall-task
if ($LASTEXITCODE -ne 0) { throw 'Task removal failed.' }
Write-Host 'Task removed. Login session, history and notification click support are preserved.'
