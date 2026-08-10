@echo off
REM ===================================================================
REM  MatSAM Analyzer - launch
REM  Runs the app inside its private pixi environment (the GPU or CPU
REM  environment chosen by install.bat). The user never activates
REM  anything; pixi does it internally.
REM
REM  On the very first launch the app downloads the SAM2 model into
REM  models\sam2 (only if that folder is not already present).
REM ===================================================================
setlocal
cd /d "%~dp0"

set "PIXI=%~dp0.pixi-bin\pixi.exe"
if not exist "%PIXI%" (
  echo  The app is not set up yet. Please run  install.bat  first.
  pause
  exit /b 1
)

REM use the environment install.bat selected (default = GPU, cpu = CPU-only)
set "MATSAM_ENV=default"
if exist "%~dp0.matsam-env" set /p MATSAM_ENV=<"%~dp0.matsam-env"

REM launch the GUI without a lingering console window
start "" /b "%PIXI%" run --environment %MATSAM_ENV% app
endlocal
