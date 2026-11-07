@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0runtime\python\python.exe" (
  echo The complete offline demo package is required. Private Python runtime is missing.
  pause
  exit /b 1
)
"%~dp0runtime\python\python.exe" -B -X utf8 "%~dp0scripts\portable.py" %*
set "demo_exit=%ERRORLEVEL%"
if not "%demo_exit%"=="0" pause
exit /b %demo_exit%
