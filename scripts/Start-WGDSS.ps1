param(
    [switch]$NoBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDirectory = Join-Path $repoRoot "backend"
$frontendDirectory = Join-Path $repoRoot "frontend"
$backendPython = Join-Path $backendDirectory "venv\Scripts\python.exe"
$requirementsFile = Join-Path $backendDirectory "requirements-dev.txt"

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,
        [Parameter(Mandatory = $true)]
        [string]$FailureMessage
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw $FailureMessage
    }
}

function Wait-ForEndpoint {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [int]$TimeoutSeconds = 30
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Endpoint -Url $Url) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Test-Endpoint {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url
    )

    try {
        Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2 | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

if (-not (Test-Path $backendPython)) {
    $pythonLauncher = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($null -ne $pythonLauncher) {
        Invoke-CheckedCommand {
            & $pythonLauncher.Source -3 -m venv (Join-Path $backendDirectory "venv")
        } "Unable to create the backend Python virtual environment."
    }
    else {
        $pythonLauncher = Get-Command "python.exe" -ErrorAction SilentlyContinue
        if ($null -eq $pythonLauncher) {
            throw "Python 3 was not found. Install Python 3 and run this launcher again."
        }
        Invoke-CheckedCommand {
            & $pythonLauncher.Source -m venv (Join-Path $backendDirectory "venv")
        } "Unable to create the backend Python virtual environment."
    }

    Invoke-CheckedCommand {
        & $backendPython -m pip install -r $requirementsFile
    } "Backend dependency installation failed."
}
else {
    & $backendPython -c "import fastapi, sqlalchemy, uvicorn" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Invoke-CheckedCommand {
            & $backendPython -m pip install -r $requirementsFile
        } "Backend dependency repair failed."
    }
}

$npmCommand = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
if ($null -eq $npmCommand) {
    $npmCommand = Get-Command "npm" -ErrorAction SilentlyContinue
}
if ($null -eq $npmCommand) {
    throw "npm was not found. Install the current Node.js LTS release and run this launcher again."
}

if (-not (Test-Path (Join-Path $frontendDirectory "node_modules"))) {
    Push-Location $frontendDirectory
    try {
        Invoke-CheckedCommand {
            & $npmCommand.Source install
        } "Frontend dependency installation failed."
    }
    finally {
        Pop-Location
    }
}

Write-Host "Applying database migrations..." -ForegroundColor Cyan
Push-Location $backendDirectory
try {
    Invoke-CheckedCommand {
        & $backendPython -m alembic upgrade head
    } "Database migration failed."
}
finally {
    Pop-Location
}

Write-Host "Starting WGDSS backend and frontend..." -ForegroundColor Cyan
$backendReady = Test-Endpoint -Url "http://127.0.0.1:8000/"
if (-not $backendReady) {
    Start-Process -FilePath "cmd.exe" `
        -ArgumentList @("/k", "venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000") `
        -WorkingDirectory $backendDirectory | Out-Null
}
else {
    Write-Host "Backend is already running; reusing it." -ForegroundColor DarkCyan
}

$frontendReady = Test-Endpoint -Url "http://127.0.0.1:5173/"
if (-not $frontendReady) {
    Start-Process -FilePath "cmd.exe" `
        -ArgumentList @("/k", "npm run dev -- --host 127.0.0.1") `
        -WorkingDirectory $frontendDirectory | Out-Null
}
else {
    Write-Host "Frontend is already running; reusing it." -ForegroundColor DarkCyan
}

$backendReady = Wait-ForEndpoint -Url "http://127.0.0.1:8000/"
$frontendReady = Wait-ForEndpoint -Url "http://127.0.0.1:5173/"

if (-not $backendReady -or -not $frontendReady) {
    throw "WGDSS did not become ready in time. Review the backend and frontend terminal windows for the startup error."
}

Write-Host "WGDSS is ready at http://localhost:5173" -ForegroundColor Green
Write-Host "API documentation is at http://localhost:8000/docs" -ForegroundColor Green

if (-not $NoBrowser) {
    Start-Process "http://localhost:5173"
}
