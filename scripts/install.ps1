param([switch]$InstallTask)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    python -m venv (Join-Path $projectRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required.' }
}
& $pythonPath -m pip install --index-url https://mirrors.aliyun.com/pypi/simple -e "$projectRoot[test]"
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check network and retry.' }
& $pythonPath (Join-Path $PSScriptRoot 'runner.py') init
if ($LASTEXITCODE -ne 0) { throw 'Configuration initialization failed.' }
if ($InstallTask) {
    & $pythonPath (Join-Path $PSScriptRoot 'runner.py') install-task
    if ($LASTEXITCODE -ne 0) { throw 'Task registration failed.' }
}
Write-Host 'Ready. Run .\watcher.cmd login, then .\watcher.cmd discover.'
