# Установка в .venv без изменения глобального Python.
[CmdletBinding()]
param([string]$PythonExecutable = "")
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    $venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        if ($PythonExecutable) {
            & $PythonExecutable -m venv .venv
        } elseif (Get-Command py -ErrorAction SilentlyContinue) {
            & py -3 -m venv .venv
        } else {
            & python -m venv .venv
        }
        if ($LASTEXITCODE -ne 0) { throw "Virtualenv creation failed" }
    }
    & $venvPython -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11+ required'; print(sys.version)"
    if ($LASTEXITCODE -ne 0) { throw "Python 3.11+ required" }
    & $venvPython -m pip install -e ".[dev]"
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed" }
    & $venvPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw "Dependency conflicts" }
    Write-Host "Ready. Select .venv\Scripts\python.exe in PyCharm and run main.py"
} finally {
    Pop-Location
}
