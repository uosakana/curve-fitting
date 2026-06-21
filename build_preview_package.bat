@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_CMD="

py -3 --version >nul 2>nul
if not errorlevel 1 (
  set "PYTHON_CMD=py -3"
)

if not defined PYTHON_CMD (
  python --version >nul 2>nul
  if not errorlevel 1 (
    set "PYTHON_CMD=python"
  )
)

if not defined PYTHON_CMD (
  echo Python was not found on this build computer.
  echo Install Python 3.11 or newer, then run this file again.
  pause
  exit /b 9009
)

echo Using %PYTHON_CMD%
echo.

%PYTHON_CMD% -m pip install --upgrade "pyinstaller>=6.6" "setuptools<81"
if errorlevel 1 (
  echo.
  echo Could not install packaging tools.
  pause
  exit /b 1
)

%PYTHON_CMD% tools\build_windows_preview.py
set EXIT_CODE=%ERRORLEVEL%

echo.
if "%EXIT_CODE%"=="0" (
  echo Preview package is ready under dist\
) else (
  echo Preview package build failed with code %EXIT_CODE%.
)
pause
exit /b %EXIT_CODE%
