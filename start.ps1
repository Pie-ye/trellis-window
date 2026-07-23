# Start Trellis Window on Windows (default 0.0.0.0:8775).
# Usage (PowerShell):
#   .\start.ps1
#   $env:TRELLIS_WINDOW_PORT=9000; .\start.ps1

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$HostAddr = if ($env:TRELLIS_WINDOW_HOST) { $env:TRELLIS_WINDOW_HOST } else { "0.0.0.0" }
$Port = if ($env:TRELLIS_WINDOW_PORT) { $env:TRELLIS_WINDOW_PORT } else { "8775" }

$VenvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

function Find-Python {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) { return $py.Source }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { return $py.Source }
    return $null
}

function Ensure-Venv {
    if (Test-Path $VenvPython) { return }
    Write-Host "Creating virtualenv .venv ..."
    $py = Find-Python
    if (-not $py) {
        Write-Error "Python not found. Install Python 3.10+ from https://www.python.org/downloads/ and ensure 'python' is on PATH."
    }
    & $py -m venv .venv
    if (-not (Test-Path $VenvPython)) {
        Write-Error "Failed to create .venv (missing Scripts\python.exe)."
    }
}

function Test-UvicornInstalled {
    & $VenvPython -c "import uvicorn" 2>$null
    return ($LASTEXITCODE -eq 0)
}

function Ensure-Deps {
    if (Test-UvicornInstalled) { return }
    Write-Host "Installing dependencies from requirements.txt ..."
    & $VenvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        Write-Error "pip upgrade failed. Try: .\.venv\Scripts\python.exe -m ensurepip --upgrade"
    }
    & $VenvPython -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        Write-Error "pip install failed. Check network / requirements.txt."
    }
    if (-not (Test-UvicornInstalled)) {
        Write-Error "uvicorn still missing after install. Delete .venv and re-run .\start.ps1"
    }
}

Ensure-Venv
Ensure-Deps

Write-Host "Trellis Window → http://${HostAddr}:${Port}/  (local: http://127.0.0.1:${Port}/)"
& $VenvPython -m uvicorn server.app:app --host $HostAddr --port $Port
