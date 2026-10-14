# Проверки пакетов, тестов и точки входа; необязательная проверка Ollama.
[CmdletBinding()]
param([switch]$CheckOllama)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$previousQtPlatform = $env:QT_QPA_PLATFORM
Push-Location $projectRoot
try {
    $venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) { throw "Run scripts/setup_windows.ps1 first" }
    & $venvPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw "Dependency conflicts" }
    $env:QT_QPA_PLATFORM = "offscreen"
    & $venvPython -m pytest -q --junitxml=test-results.xml
    if ($LASTEXITCODE -ne 0) { throw "Tests failed. See test-results.xml" }
    & $venvPython scripts/smoke_gui.py
    if ($LASTEXITCODE -ne 0) { throw "GUI entry point failed" }
    if ($CheckOllama) {
        $result = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 15
        $result.models | Select-Object name
        if (-not $result.models) { throw "Ollama has no installed models" }
    }
    Write-Host "Checks passed. Verify the interactive Windows workflow using docs/validation.md"
} finally {
    if ($null -eq $previousQtPlatform) {
        Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
    } else {
        $env:QT_QPA_PLATFORM = $previousQtPlatform
    }
    Pop-Location
}
