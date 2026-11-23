@echo off
setlocal
cd /d "%~dp0"
set PYTHONHOME=
set PYTHONPATH=
if not exist "%~dp0python\python.exe" (
  echo Portable Python is missing. Run prepare_portable_python.bat first.
  pause
  exit /b 1
)
"%~dp0python\python.exe" -s app.py
if errorlevel 1 pause
