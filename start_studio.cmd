@echo off
cd /d "%~dp0"
title AI Music Studio
".venv\Scripts\python.exe" -m studio.launch_web %*
if errorlevel 1 pause
