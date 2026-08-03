@echo off
setlocal
cd /d "%~dp0"
if exist "ShopAds.exe" (
  "ShopAds.exe" validate
) else if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m shopads validate
) else (
  python -m shopads validate
)
set "SHOPADS_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %SHOPADS_EXIT%
