#Requires -RunAsAdministrator
param(
    [string]$AppDir = $PSScriptRoot
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Write-Step { param([string]$Msg) Write-Host "`n  >> $Msg" -ForegroundColor Cyan }
function Write-OK   { param([string]$Msg) Write-Host "     OK: $Msg" -ForegroundColor Green }
function Write-Warn { param([string]$Msg) Write-Host "     ATENTIE: $Msg" -ForegroundColor Yellow }
function Write-Fail { param([string]$Msg) Write-Host "     EROARE: $Msg" -ForegroundColor Red }

Write-Host ""
Write-Host "  +==========================================+" -ForegroundColor White
Write-Host "  |   Calendar Stiinta - Installer           |" -ForegroundColor White
Write-Host "  +==========================================+" -ForegroundColor White
Write-Host ""

# ── 1. Python ──────────────────────────────────────────────────────────────────
Write-Step "Verificare Python..."

# Build candidate list: PATH names + common install locations
$pyCandidates = @("python", "python3", "py")
# User-local installs (Python 3.10–3.13)
foreach ($minor in @(13,12,11,10)) {
    $p = "$env:LOCALAPPDATA\Programs\Python\Python3$minor\python.exe"
    if (Test-Path $p) { $pyCandidates = @($p) + $pyCandidates }
}
# System-wide installs
foreach ($minor in @(13,12,11,10)) {
    foreach ($root in @("C:\Python3$minor", "C:\Program Files\Python3$minor")) {
        $p = "$root\python.exe"
        if (Test-Path $p) { $pyCandidates = @($p) + $pyCandidates }
    }
}

$pyCmd = $null
foreach ($candidate in $pyCandidates) {
    try {
        $ver = & $candidate --version 2>&1
        if ($ver -match "Python 3\.(\d+)") {
            $minor = [int]$Matches[1]
            if ($minor -ge 10) {
                $pyCmd = $candidate
                Write-OK "$ver gasit: $candidate"
                break
            }
        }
    } catch { }
}

if (-not $pyCmd) {
    Write-Warn "Python 3.10+ nu a fost gasit. Se instaleaza..."
    winget install --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path","User")
    $pyCmd = "python"
    try {
        $ver = & $pyCmd --version 2>&1
        Write-OK "Instalat: $ver"
    } catch {
        Write-Fail "Instalarea Python a esuat. Instalati manual de la https://www.python.org/ si reluati."
        Read-Host "Apasati Enter pentru a inchide"
        exit 1
    }
}

# ── 2. Tesseract ───────────────────────────────────────────────────────────────
Write-Step "Verificare Tesseract OCR..."

$tessExe = $null
$candidates = @(
    "tesseract",
    "C:\Program Files\Tesseract-OCR\tesseract.exe",
    "C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"
)
foreach ($c in $candidates) {
    try {
        $ver = & $c --version 2>&1
        if ($ver -match "tesseract") { $tessExe = $c; break }
    } catch { }
}

if (-not $tessExe) {
    Write-Warn "Tesseract nu a fost gasit. Se instaleaza..."
    winget install --id UB-Mannheim.TesseractOCR --silent --accept-package-agreements --accept-source-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path","User")
    $tessExe = "C:\Program Files\Tesseract-OCR\tesseract.exe"
    if (-not (Test-Path $tessExe)) {
        Write-Fail "Instalarea Tesseract a esuat. Instalati manual de la https://github.com/UB-Mannheim/tesseract/wiki"
        Read-Host "Apasati Enter pentru a inchide"
        exit 1
    }
    Write-OK "Tesseract instalat."
} else {
    Write-OK "Tesseract gasit: $tessExe"
}

# ── 3. Tessdata romana (model best) ───────────────────────────────────────────
Write-Step "Verificare tessdata romana (model best)..."

$tessdata = Join-Path $env:USERPROFILE ".tessdata"
if (-not (Test-Path $tessdata)) { New-Item -ItemType Directory -Path $tessdata | Out-Null }

$ronFile = Join-Path $tessdata "ron.traineddata"
if (Test-Path $ronFile) {
    Write-OK "ron.traineddata deja prezent."
} else {
    Write-Warn "Se descarca ron.traineddata (model best, ~10 MB)..."
    $url = "https://github.com/tesseract-ocr/tessdata_best/raw/main/ron.traineddata"
    try {
        Invoke-WebRequest -Uri $url -OutFile $ronFile -UseBasicParsing
        Write-OK "ron.traineddata descarcat."
    } catch {
        Write-Warn "Descarcarea a esuat. OCR-ul va folosi modelul standard (diacritice reduse)."
        Remove-Item -ErrorAction SilentlyContinue $ronFile
    }
}

# ── 4. pip install ─────────────────────────────────────────────────────────────
Write-Step "Instalare dependente Python..."

$req = Join-Path $AppDir "requirements.txt"
& $pyCmd -m pip install --upgrade pip --quiet --disable-pip-version-check --no-warn-script-location
& $pyCmd -m pip install -r $req --quiet --disable-pip-version-check --no-warn-script-location

if ($LASTEXITCODE -ne 0) {
    Write-Fail "pip install a esuat."
    Read-Host "Apasati Enter pentru a inchide"
    exit 1
}
Write-OK "Dependente instalate."

# ── 5. Creare .env ─────────────────────────────────────────────────────────────
Write-Step "Configurare fisier .env..."

$envFile = Join-Path $AppDir ".env"
if (Test-Path $envFile) {
    Write-OK ".env exista deja (nu va fi suprascris)."
} else {
    Write-Host ""
    Write-Host "  Setati parola de administrator pentru panoul de administrare." -ForegroundColor White
    $pw = Read-Host "  Parola admin (Enter pentru 'admin123')"
    if (-not $pw) { $pw = "admin123" }

    $envContent = "ADMIN_PASSWORD=$pw`r`nTESSERACT_PATH=$tessExe`r`n"
    [System.IO.File]::WriteAllText($envFile, $envContent, [System.Text.Encoding]::UTF8)
    Write-OK ".env creat."
}

# ── 6. Creare start.bat ────────────────────────────────────────────────────────
Write-Step "Creare start.bat..."

$startBat = Join-Path $AppDir "start.bat"
@"
@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Pornire Calendar Stiinta...
echo Deschide http://localhost:8000 in browser.
echo Apasa Ctrl+C pentru a opri serverul.
echo.
"$pyCmd" -m uvicorn main:app --host 0.0.0.0 --port 8000
pause
"@ | Set-Content -Path $startBat -Encoding ASCII
Write-OK "start.bat creat."

# ── 7. Creare uploads dir ──────────────────────────────────────────────────────
$uploadsDir = Join-Path $AppDir "uploads"
if (-not (Test-Path $uploadsDir)) {
    New-Item -ItemType Directory -Path $uploadsDir | Out-Null
}

# ── Done ───────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  +==========================================+" -ForegroundColor Green
Write-Host "  |   Instalare finalizata cu succes!        |" -ForegroundColor Green
Write-Host "  +==========================================+" -ForegroundColor Green
Write-Host ""
Write-Host "  Porniti aplicatia cu: start.bat" -ForegroundColor White
Write-Host "  Apoi deschideti in browser: http://localhost:8000" -ForegroundColor White
Write-Host ""
Read-Host "  Apasati Enter pentru a inchide"
