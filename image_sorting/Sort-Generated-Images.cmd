@echo off
cd /d "%~dp0"
if "%~1"=="" (
  echo Drag a folder containing seed-*.png files onto this launcher.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -u sort_images.py --input "%~1"
pause
