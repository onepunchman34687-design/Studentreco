@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Prepare USB Portable Attendance App

set "PYVER=3.11.9"
set "PYDIR=%CD%\python"
set "PYINSTALLER=%TEMP%\python-%PYVER%-amd64.exe"
set "IF_WHEEL=%CD%\insightface-0.7.3-cp311-cp311-win_amd64.whl"
set "IF_URL=https://github.com/Gourieff/Assets/raw/main/Insightface/insightface-0.7.3-cp311-cp311-win_amd64.whl"

echo ============================================================
echo   USB PORTABLE ATTENDANCE - PRIVATE PYTHON RUNTIME
echo ============================================================
echo Python, packages, and model files will be stored in this folder.
echo InsightFace will be installed from a prebuilt community wheel,
echo avoiding the local C++ compilation that failed previously.
echo This wheel is unofficial (not published by the InsightFace project).
echo Requirements: Windows 10/11 64-bit, internet, several GB free.
echo.

if not exist "%PYDIR%\python.exe" (
  echo [1/5] Downloading the official Python %PYVER% Windows installer...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-amd64.exe' -OutFile '%PYINSTALLER%'"
  if errorlevel 1 goto failed
  echo Installing Python into this project folder on the USB drive...
  "%PYINSTALLER%" /quiet InstallAllUsers=0 TargetDir="%PYDIR%" Include_launcher=0 Include_pip=1 Include_tcltk=1 Include_test=0 PrependPath=0 AssociateFiles=0 Shortcuts=0 Include_doc=0
  if errorlevel 1 goto failed
) else (
  echo [1/5] Portable Python already exists; reusing it.
)

if not exist "%PYDIR%\python.exe" (
  echo ERROR: python.exe was not found after installation.
  goto failed
)

echo [2/5] Checking the Python runtime stored on this drive...
"%PYDIR%\python.exe" --version
if errorlevel 1 goto failed

echo [3/5] Checking pip...
"%PYDIR%\python.exe" -m pip --version
if errorlevel 1 goto failed

 echo [4/5] Installing base packages using the pendrive Python...
"%PYDIR%\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed
"%PYDIR%\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed

echo Downloading the prebuilt InsightFace wheel for Python 3.11...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '%IF_URL%' -OutFile '%IF_WHEEL%'"
if errorlevel 1 goto failed
if not exist "%IF_WHEEL%" (
  echo ERROR: InsightFace wheel download did not create the file.
  goto failed
)
echo Installing InsightFace wheel without building C++ extensions...
"%PYDIR%\python.exe" -m pip install --no-deps "%IF_WHEEL%"
if errorlevel 1 goto failed

if exist "%IF_WHEEL%" del /q "%IF_WHEEL%"
echo [5/5] Checking packages and downloading/checking the face model...
if not exist "insightface_data" mkdir "insightface_data"
"%PYDIR%\python.exe" check_setup.py
if errorlevel 1 goto failed

(
  echo @echo off
  echo setlocal
  echo cd /d "%%~dp0"
  echo set PYTHONHOME=
  echo set PYTHONPATH=
  echo if not exist "%%~dp0python\python.exe" ^(
  echo   echo Portable Python is missing. Run prepare_portable_python.bat first.
  echo   pause
  echo   exit /b 1
  echo ^)
  echo "%%~dp0python\python.exe" -s app.py
  echo if errorlevel 1 pause
) > start_attendance.bat

(
  echo PORTABLE ATTENDANCE APP
  echo =======================
  echo Double-click start_attendance.bat to run the app.
  echo This launcher uses .\python\python.exe from this folder, not system Python.
  echo Model files are stored under .\insightface_data.
  echo Attendance database, captures, and app outputs are stored in this folder.
  echo Use only on compatible 64-bit Windows PCs. Camera access and Windows native
  echo runtime requirements can still vary by computer. Keep student biometric data secure.
) > READ_ME_FIRST.txt

echo.
echo SETUP COMPLETE.
echo Portable Python: %PYDIR%\python.exe
echo Launch file:     %CD%\start_attendance.bat
echo Test on a second Windows laptop before relying on it.
echo Do not unplug the drive while the app is running.
pause
exit /b 0

:failed
echo.
echo SETUP FAILED. The portable environment may be incomplete.
echo Read the error above. Do not assume the app is ready until setup succeeds.
pause
exit /b 1
