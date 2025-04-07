@echo off
setlocal

:: Define Python version
set PYTHON_VERSION=3.11.5
set PYTHON_INSTALLER=python-%PYTHON_VERSION%-amd64.exe
set PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/%PYTHON_INSTALLER%

:: Download Python installer
echo Downloading Python %PYTHON_VERSION%...
powershell -Command "& {Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON_INSTALLER%'}"

:: Install Python silently
echo Installing Python...
start /wait %PYTHON_INSTALLER% /quiet InstallAllUsers=1 PrependPath=1

:: Verify installation
python --version
if %errorlevel% neq 0 (
    echo Python installation failed!
    exit /b %errorlevel%
)

echo Python installed successfully!
pause