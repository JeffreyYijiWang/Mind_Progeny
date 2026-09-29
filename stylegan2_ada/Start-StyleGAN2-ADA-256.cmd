@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -u manage.py --profile 256 train --execute
pause
