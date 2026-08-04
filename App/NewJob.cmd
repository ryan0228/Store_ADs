@echo off
setlocal
cd /d "%~dp0"
if exist "ShopAds.exe" (
  "ShopAds.exe" new-job
) else if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m shopads new-job
) else (
  python -m shopads new-job
)
set "SHOPADS_EXIT=%ERRORLEVEL%"
echo.
if not "%SHOPADS_EXIT%"=="0" echo New job failed. See the error above.
pause
exit /b %SHOPADS_EXIT%
