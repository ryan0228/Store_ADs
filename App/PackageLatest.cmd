@echo off
setlocal
cd /d "%~dp0"
if exist "ShopAds.exe" (
  "ShopAds.exe" package
) else if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m shopads package
) else (
  python -m shopads package
)
set "SHOPADS_EXIT=%ERRORLEVEL%"
echo.
if not "%SHOPADS_EXIT%"=="0" echo Packaging failed. Confirm Result\Final first.
pause
exit /b %SHOPADS_EXIT%
