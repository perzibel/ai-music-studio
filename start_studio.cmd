@echo off
REM Opens ACE-Step's own web app (no Claude/Codex needed). Browser page: http://127.0.0.1:7860
REM The first time it asks your name and titles the app "<your name> Music Studio".
REM Offload: the 8 GB GPU is shared with other apps; without it generation can freeze.
REM No update check: an auto-update could break the install the music studio relies on.
cd /d "%~dp0"
".venv\Scripts\python.exe" -m studio.set_name
set OFFLOAD_TO_CPU=--offload_to_cpu true
set CHECK_UPDATE=false
cd /d "%~dp0engines\ACE-Step-1.5"
call "%~dp0engines\ACE-Step-1.5\start_gradio_ui.bat"
