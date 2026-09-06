# GrandmasterAI — one-command start for Windows.
#
# Checks what is installed, installs the project's own dependencies, prepares the
# database, then opens the backend and the site in their own windows.
#
# Run it by double-clicking start.bat, or from PowerShell:
#     powershell -ExecutionPolicy Bypass -File .\start.ps1

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

function Say($text)  { Write-Host $text }
function Good($text) { Write-Host "  OK    $text" -ForegroundColor Green }
function Bad($text)  { Write-Host "  ---   $text" -ForegroundColor Red }
function Note($text) { Write-Host "        $text" -ForegroundColor DarkGray }

Say ''
Say 'GrandmasterAI'
Say '============='
Say ''
Say 'Checking what you have installed...'

# ---------------------------------------------------------------- Python
# `py` is the Windows launcher and is more reliable than `python`, which can open
# the Microsoft Store instead of running anything.
$python = $null
foreach ($candidate in @('py', 'python', 'python3')) {
    try {
        $version = & $candidate --version 2>&1
        if ($LASTEXITCODE -eq 0 -and "$version" -match '(\d+)\.(\d+)') {
            if ([int]$Matches[1] -ge 3 -and [int]$Matches[2] -ge 11) {
                $python = $candidate
                Good "Python: $version  (using '$candidate')"
                break
            }
            Note "Found $version at '$candidate', but 3.11 or newer is needed."
        }
    } catch { }
}
if (-not $python) {
    Bad 'Python 3.11+ not found.'
    Note 'Install it from https://www.python.org/downloads/'
    Note 'Tick "Add python.exe to PATH" on the first screen, then reopen this window.'
    Read-Host 'Press Enter to close'
    exit 1
}

# ---------------------------------------------------------------- Node
try {
    $nodeVersion = & node --version 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'missing' }
    Good "Node: $nodeVersion"
} catch {
    Bad 'Node.js not found.'
    Note 'Install the LTS version from https://nodejs.org/ then reopen this window.'
    Read-Host 'Press Enter to close'
    exit 1
}

# ---------------------------------------------------------------- Stockfish
# The engine decides every chess fact in this app, so nothing works without it.
function Find-Stockfish {
    # 1. Already recorded in .env
    $envFile = Join-Path $root '.env'
    if (Test-Path $envFile) {
        $line = Select-String -Path $envFile -Pattern '^\s*STOCKFISH_PATH\s*=\s*(.+)$' | Select-Object -First 1
        if ($line) {
            $recorded = $line.Matches[0].Groups[1].Value.Trim().Trim('"')
            if ($recorded -and (Test-Path $recorded)) { return $recorded }
        }
    }
    # 2. On PATH
    $onPath = Get-Command stockfish -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    # 3. Anywhere sensible nearby
    $places = @(
        (Join-Path $root 'engines'),
        'C:\Vasan\Tools',
        (Join-Path $env:USERPROFILE 'Downloads'),
        'C:\Program Files'
    )
    foreach ($place in $places) {
        if (-not (Test-Path $place)) { continue }
        $found = Get-ChildItem -Path $place -Filter 'stockfish*.exe' -Recurse -ErrorAction SilentlyContinue |
                 Select-Object -First 1
        if ($found) { return $found.FullName }
    }
    return $null
}

$stockfish = Find-Stockfish
if (-not $stockfish) {
    Bad 'Stockfish not found.'
    Note 'Download the Windows zip from https://stockfishchess.org/download/'
    Note "Extract it into:  $(Join-Path $root 'engines')"
    Note 'Then run this script again. It will find the .exe on its own.'
    Read-Host 'Press Enter to close'
    exit 1
}
Good "Stockfish: $stockfish"

# ---------------------------------------------------------------- settings
$envFile = Join-Path $root '.env'
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $root '.env.example') $envFile
    Say ''
    Good 'Created .env from the example.'
}
# Record the engine path so the app finds it too.
$content = Get-Content $envFile
if ($content -match '^\s*STOCKFISH_PATH\s*=') {
    $content = $content -replace '^\s*STOCKFISH_PATH\s*=.*$', "STOCKFISH_PATH=$stockfish"
} else {
    $content += "STOCKFISH_PATH=$stockfish"
}
Set-Content -Path $envFile -Value $content -Encoding UTF8

# ---------------------------------------------------------------- install
Say ''
Say 'Installing dependencies (first run takes a few minutes)...'

& $python -m pip install --quiet --disable-pip-version-check -r (Join-Path $root 'backend\requirements-dev.txt')
if ($LASTEXITCODE -ne 0) {
    Bad 'Installing the Python packages failed. The error is above.'
    Read-Host 'Press Enter to close'
    exit 1
}
Good 'Python packages ready.'

$frontend = Join-Path $root 'frontend'
if (-not (Test-Path (Join-Path $frontend 'node_modules'))) {
    Push-Location $frontend
    & npm install --no-fund --no-audit
    $npmFailed = $LASTEXITCODE -ne 0
    Pop-Location
    if ($npmFailed) {
        Bad 'Installing the site packages failed. The error is above.'
        Read-Host 'Press Enter to close'
        exit 1
    }
}
Good 'Site packages ready.'

# ---------------------------------------------------------------- database
Say ''
Say 'Preparing the database and puzzle bank...'
$backend = Join-Path $root 'backend'
Push-Location $backend
& $python -m app.bootstrap --seed
$bootstrapFailed = $LASTEXITCODE -ne 0
Pop-Location
if ($bootstrapFailed) {
    Bad 'Could not prepare the database. The error is above.'
    Read-Host 'Press Enter to close'
    exit 1
}
Good 'Database ready.'

# ---------------------------------------------------------------- run
Say ''
Say 'Starting the app in two new windows...'

Start-Process powershell -ArgumentList @(
    '-NoExit', '-Command',
    "Set-Location '$backend'; Write-Host 'BACKEND — leave this window open' -ForegroundColor Cyan; & $python -m uvicorn app.main:app --reload --port 8000"
)

Start-Process powershell -ArgumentList @(
    '-NoExit', '-Command',
    "Set-Location '$frontend'; Write-Host 'SITE — leave this window open' -ForegroundColor Cyan; npm run dev"
)

Say ''
Say 'Waiting for the backend to come up...'
$ready = $false
foreach ($attempt in 1..45) {
    Start-Sleep -Seconds 2
    try {
        $health = Invoke-RestMethod -Uri 'http://localhost:8000/api/health' -TimeoutSec 3
        $ready = $true
        break
    } catch { }
}

Say ''
if ($ready) {
    Good "Backend is up. Status: $($health.status)"
    foreach ($part in $health.components.PSObject.Properties) {
        Note "$($part.Name): $($part.Value)"
    }
    if ($health.components.coaching_brain -eq 'template-fallback') {
        Say ''
        Note 'No ANTHROPIC_API_KEY set, so coaching uses plain templates (English only).'
        Note 'The chess is identical either way. Add a key to .env for real coaching.'
    }
    Say ''
    Say 'Opening http://localhost:5173'
    Start-Process 'http://localhost:5173'
    Say ''
    Say 'To stop the app, close the two windows that opened.'
} else {
    Bad 'The backend did not start within 90 seconds.'
    Note 'Check the BACKEND window for the error.'
}

Say ''
Read-Host 'Press Enter to close this window'
