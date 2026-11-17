# Puts an "AI Music Studio" shortcut on your Desktop that starts the studio UI in your browser.
#   powershell -ExecutionPolicy Bypass -File install_shortcut.ps1
$root = $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Error "Run setup.ps1 first (no .venv found)."; exit 1 }

$desktop = [Environment]::GetFolderPath("Desktop")
$lnk = Join-Path $desktop "AI Music Studio.lnk"
$sh = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$sh.TargetPath = Join-Path $root "start_studio.cmd"
$sh.WorkingDirectory = $root
$sh.IconLocation = "$env:SystemRoot\System32\shell32.dll,168"
$sh.Description = "Start the AI Music Studio"
$sh.Save()
Write-Host "Created shortcut: $lnk"
Write-Host "Double-click it. The first time, it asks your name and becomes '<your name> Music Studio'."
