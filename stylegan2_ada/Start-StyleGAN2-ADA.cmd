@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -u manage.py train --execute
pause
