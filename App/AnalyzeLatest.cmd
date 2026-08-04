@echo off
setlocal
cd /d "%~dp0"
if exist "ShopAds.exe" (
  "ShopAds.exe" analyze
) else if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m shopads analyze
) else (
  python -m shopads analyze
)
set "SHOPADS_EXIT=%ERRORLEVEL%"
echo.
if not "%SHOPADS_EXIT%"=="0" echo AI analysis failed. See the error and Logs folder above.
pause
exit /b %SHOPADS_EXIT%
