# Start Trellis Window on Windows (default 0.0.0.0:8775).
# Usage (PowerShell):
#   .\start.ps1
#   $env:TRELLIS_WINDOW_PORT=9000; .\start.ps1

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$HostAddr = if ($env:TRELLIS_WINDOW_HOST) { $env:TRELLIS_WINDOW_HOST } else { "0.0.0.0" }
$Port = if ($env:TRELLIS_WINDOW_PORT) { $env:TRELLIS_WINDOW_PORT } else { "8775" }

$VenvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating virtualenv .venv ..."
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py) {
        $py = Get-Command py -ErrorAction SilentlyContinue
    }
    if (-not $py) {
        Write-Error "Python not found. Install Python 3.10+ from https://www.python.org/downloads/ and ensure 'python' is on PATH."
    }
    & $py.Source -m venv .venv
    if (-not (Test-Path $VenvPython)) {
        Write-Error "Failed to create .venv (missing Scripts\python.exe)."
    }
    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install -r requirements.txt
}

Write-Host "Trellis Window → http://${HostAddr}:${Port}/  (local: http://127.0.0.1:${Port}/)"
& $VenvPython -m uvicorn server.app:app --host $HostAddr --port $Port
