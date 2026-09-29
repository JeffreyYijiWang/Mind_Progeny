@echo off
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\stop_local_training.py"
echo.
pause
