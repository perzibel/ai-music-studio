# One-time setup: Python environment, sound engines, free instrument libraries, and MCP registration.
#   powershell -ExecutionPolicy Bypass -File setup.ps1                 (everything except ACE-Step, ~6 GB)
#   powershell -ExecutionPolicy Bypass -File setup.ps1 -WithAceStep    (+ AI vocals & realism pass, ~20 GB, NVIDIA GPU)
#   powershell -ExecutionPolicy Bypass -File setup.ps1 -Minimal        (no big sample libraries; GM fallback)
param([switch]$WithAceStep, [switch]$Minimal)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv")) { python -m venv .venv }
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

New-Item -ItemType Directory -Force soundfonts | Out-Null
if (-not (Test-Path "soundfonts\GeneralUser-GS.sf2")) {
    Write-Host "Downloading GeneralUser GS SoundFont (~32 MB)..."
    $ProgressPreference = "SilentlyContinue"
    Invoke-WebRequest "https://github.com/mrbumpy409/GeneralUser-GS/raw/main/GeneralUser-GS.sf2" -OutFile "soundfonts\GeneralUser-GS.sf2"
}

# sfizz engine + amp models + cabinet IRs
.\.venv\Scripts\python.exe -m studio.library engines
if (-not $Minimal) {
    # piano, rhodes, drums, DI guitars & basses, orchestra (~5.6 GB)
    .\.venv\Scripts\python.exe -m studio.library salamander_piano jrhodes virtuosity_drums black_green_guitars black_blue_basses vsco2
}

if ($WithAceStep) {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { .\.venv\Scripts\python.exe -m pip install uv }
    if (-not (Test-Path "engines\ACE-Step-1.5")) { git clone --depth 1 https://github.com/ACE-Step/ACE-Step-1.5.git engines\ACE-Step-1.5 }
    Push-Location engines\ACE-Step-1.5
    uv sync
    uv run acestep-download --model acestep-v15-base   # used by the AI singer (vocals)
    Pop-Location
    Write-Host "ACE-Step installed. The remaining models download on first use."
}

$py = Join-Path $root ".venv\Scripts\python.exe"
$server = Join-Path $root "run_server.py"
if (Get-Command claude -ErrorAction SilentlyContinue) {
    claude mcp remove ai-music-studio --scope user 2>$null | Out-Null
    claude mcp add ai-music-studio --scope user -- $py $server
    Write-Host "Registered with Claude Code."
}
if (Get-Command codex -ErrorAction SilentlyContinue) {
    codex mcp remove ai-music-studio 2>$null | Out-Null
    codex mcp add ai-music-studio -- $py $server
    Write-Host "Registered with Codex."
}
Write-Host "Done. Try: .\.venv\Scripts\python.exe -m studio render examples\metal.json --play"
