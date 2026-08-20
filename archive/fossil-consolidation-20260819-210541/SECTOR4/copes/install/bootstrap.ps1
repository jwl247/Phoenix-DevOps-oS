<#
    CoPES Bootstrap Script (PowerShell 7)
    Purpose: Set up CoPES on Windows so it becomes usable after cloning.
    Run this from the root of the CoPES folder.
#>

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   CoPES Bootstrap - Phase 1 Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check PowerShell version
if ($PSVersionTable.PSVersion.Major -lt 7) {
    Write-Host "ERROR: PowerShell 7 or higher is required." -ForegroundColor Red
    Write-Host "Please install PowerShell 7 and run this script again." -ForegroundColor Yellow
    exit 1
}

Write-Host "[OK] PowerShell 7 detected." -ForegroundColor Green

# 2. Check for Python
try {
    $pythonVersion = python --version 2>&1
    if ($pythonVersion -notmatch "Python 3\.(1[0-9]|[2-9][0-9])") {
        throw "Python version too old"
    }
    Write-Host "[OK] Python detected: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Python 3.10 or higher is required." -ForegroundColor Red
    Write-Host "Please install Python 3.10+ and make sure it's added to PATH." -ForegroundColor Yellow
    exit 1
}

# 3. Create virtual environment if it doesn't exist
$venvPath = ".\.venv"
if (-not (Test-Path $venvPath)) {
    Write-Host "Creating Python virtual environment..." -ForegroundColor Yellow
    python -m venv $venvPath
    Write-Host "[OK] Virtual environment created." -ForegroundColor Green
} else {
    Write-Host "[OK] Virtual environment already exists." -ForegroundColor Green
}

# 4. Activate virtual environment and install dependencies
Write-Host "Activating virtual environment and installing dependencies..." -ForegroundColor Yellow

& "$venvPath\Scripts\Activate.ps1"

if (Test-Path "pyproject.toml") {
    pip install --upgrade pip
    pip install -e .
    Write-Host "[OK] Dependencies installed from pyproject.toml." -ForegroundColor Green
} else {
    Write-Host "WARNING: pyproject.toml not found. Skipping dependency install." -ForegroundColor Yellow
}

# 5. Create required directories
$dirs = @("clonepool", "intake", "bin", "src", "templates")
foreach ($dir in $dirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null
        Write-Host "Created directory: $dir" -ForegroundColor Yellow
    }
}
Write-Host "[OK] Required directories verified." -ForegroundColor Green

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   CoPES Bootstrap Complete" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor White
Write-Host "1. Activate the environment anytime with:" -ForegroundColor White
Write-Host "   .\.venv\Scripts\Activate.ps1" -ForegroundColor Gray
Write-Host ""
Write-Host "2. You can now start working with helix.py and the intake system." -ForegroundColor White
Write-Host ""
Write-Host "CoPES is now in a usable state after cloning." -ForegroundColor Green
