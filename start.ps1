# Start Trellis Window on Windows (default 0.0.0.0:8775).
#
# Usage:
#   .\start.ps1
#   .\start.ps1 -ForceReinstall
#   .\start.ps1 -HostAddr 127.0.0.1 -Port 8775
#   $env:TRELLIS_WINDOW_PORT=9000; .\start.ps1
#
# Notes:
#   Dependency probe must NOT throw NativeCommandError when import fails
#   ($ErrorActionPreference = Stop + python stderr).

[CmdletBinding()]
param(
    [switch]$ForceReinstall,
    [string]$HostAddr = $(if ($env:TRELLIS_WINDOW_HOST) { $env:TRELLIS_WINDOW_HOST } else { "0.0.0.0" }),
    [string]$Port = $(if ($env:TRELLIS_WINDOW_PORT) { $env:TRELLIS_WINDOW_PORT } else { "8775" })
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$VenvDir = Join-Path $PSScriptRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$ReqFile = Join-Path $PSScriptRoot "requirements.txt"

function Write-Fail([string]$Message) {
    Write-Host ""
    Write-Host "[ERROR] $Message" -ForegroundColor Red
    Write-Host "Venv:   $VenvPython"
    Write-Host "Try:"
    Write-Host "  Remove-Item -Recurse -Force .venv"
    Write-Host "  .\start.ps1"
    Write-Host "Or manual install:"
    Write-Host "  .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
    Write-Host "  .\.venv\Scripts\python.exe -m uvicorn server.app:app --host 127.0.0.1 --port 8775"
    exit 1
}

function Find-Python {
    # Prefer Windows Python Launcher for a real 3.x install
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        try {
            $prev = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            $ver = & py -3 -c "import sys; print(sys.executable)" 2>&1
            $ErrorActionPreference = $prev
            if ($LASTEXITCODE -eq 0 -and $ver) {
                $path = ($ver | Select-Object -Last 1).ToString().Trim()
                if (Test-Path $path) { return $path }
            }
        } catch {
            # fall through
        }
    }
    foreach ($name in @("python", "python3")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source) { return $cmd.Source }
    }
    return $null
}

function Test-VenvPythonImport([string]$ModuleName) {
    # Safe under $ErrorActionPreference = Stop: never let failed import abort the script.
    if (-not (Test-Path $VenvPython)) { return $false }
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        # Merge stderr into success stream so PS does not raise NativeCommandError
        $null = & $VenvPython -c "import $ModuleName" 2>&1 | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $prev
    }
}

function Ensure-Venv {
    if ($ForceReinstall -and (Test-Path $VenvDir)) {
        Write-Host "ForceReinstall: removing .venv ..."
        Remove-Item -Recurse -Force $VenvDir
    }
    if (Test-Path $VenvPython) { return }

    Write-Host "Creating virtualenv .venv ..."
    $py = Find-Python
    if (-not $py) {
        Write-Fail "Python not found. Install Python 3.10+ from https://www.python.org/downloads/ (check 'Add python.exe to PATH') or install the 'py' launcher."
    }
    Write-Host "Using Python: $py"
    & $py -m venv $VenvDir
    if (-not (Test-Path $VenvPython)) {
        Write-Fail "Failed to create .venv (missing Scripts\python.exe). Try: $py -m venv .venv"
    }
}

function Ensure-Pip {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $null = & $VenvPython -m pip --version 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) { return }
    } finally {
        $ErrorActionPreference = $prev
    }

    Write-Host "Bootstrapping pip (ensurepip) ..."
    $ErrorActionPreference = "Continue"
    try {
        $null = & $VenvPython -m ensurepip --upgrade 2>&1
    } finally {
        $ErrorActionPreference = $prev
    }

    $ErrorActionPreference = "Continue"
    try {
        $null = & $VenvPython -m pip --version 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "pip is not available inside .venv. Re-install Python with pip, or run: .\.venv\Scripts\python.exe -m ensurepip --upgrade"
        }
    } finally {
        $ErrorActionPreference = $prev
    }
}

function Ensure-Deps {
    if (-not $ForceReinstall) {
        if ((Test-VenvPythonImport "uvicorn") -and (Test-VenvPythonImport "fastapi")) {
            return
        }
    }

    Write-Host "Installing dependencies from requirements.txt ..."
    Ensure-Pip

    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $VenvPython -m pip install --upgrade pip
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "pip upgrade failed."
        }
        & $VenvPython -m pip install -r $ReqFile
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "pip install -r requirements.txt failed (network / proxy / mirror?)."
        }
    } finally {
        $ErrorActionPreference = $prev
    }

    if (-not (Test-VenvPythonImport "uvicorn")) {
        Write-Fail "uvicorn still missing after install."
    }
}

# --- main ---
try {
    Ensure-Venv
    Ensure-Deps
} catch {
    Write-Fail $_.Exception.Message
}

Write-Host "Trellis Window → http://${HostAddr}:${Port}/  (local: http://127.0.0.1:${Port}/)"
Write-Host "Folder picker paths are on THIS machine (where the server runs)."
& $VenvPython -m uvicorn server.app:app --host $HostAddr --port $Port
exit $LASTEXITCODE
