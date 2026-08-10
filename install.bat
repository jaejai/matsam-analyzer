@echo off
setlocal
cd /d "%~dp0"

echo.
echo  ============================================================
echo    MatSAM Analyzer - installing components
echo    first run only; needs an internet connection
echo  ============================================================
echo.

set "PIXI=%~dp0.pixi-bin\pixi.exe"

if not exist "%PIXI%" (
  echo  Downloading the environment manager pixi ...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0get_pixi.ps1"
)

if not exist "%PIXI%" (
  echo.
  echo  ERROR: could not download the environment manager.
  echo  Please check your internet connection and run this again.
  echo.
  pause
  exit /b 1
)

REM ---- detect an NVIDIA GPU: if nvidia-smi runs, use the GPU environment ----
set "MATSAM_ENV=cpu"
where nvidia-smi >nul 2>&1
if %errorlevel%==0 (
  nvidia-smi >nul 2>&1
  if %errorlevel%==0 set "MATSAM_ENV=default"
)

if "%MATSAM_ENV%"=="default" (
  echo  NVIDIA GPU detected  -^>  installing the GPU build ^(CUDA + cuDNN bundled^).
) else (
  echo  No NVIDIA GPU detected  -^>  installing the CPU build ^(slower, but works everywhere^).
)
REM remember the choice so launch.bat runs the same environment
> "%~dp0.matsam-env" echo %MATSAM_ENV%

echo.
echo  Building the analysis environment from conda-forge ...
echo  this downloads a few GB the first time - please wait
echo.
"%PIXI%" install --environment %MATSAM_ENV%
if errorlevel 1 (
  echo.
  echo  ERROR: environment setup did not complete.
  echo  This is almost always a network issue or a corporate proxy/firewall
  echo  blocking conda-forge. Check your connection and run this again.
  echo.
  pause
  exit /b 1
)

echo.
echo  ============================================================
echo    Setup complete.  Launch the app with  launch.bat
echo.
echo    On first launch the app downloads the SAM2 model
echo    ^(~0.9 GB, Apache-2.0^) into the  models\sam2  folder.
echo    If you already have that folder, it is used as-is and
echo    nothing is downloaded.
echo  ============================================================
echo.
pause
endlocal
