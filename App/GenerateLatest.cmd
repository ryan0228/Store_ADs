@echo off
setlocal
cd /d "%~dp0"
if exist "ShopAds.exe" (
  "ShopAds.exe" generate
) else if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m shopads generate
) else (
  python -m shopads generate
)
set "SHOPADS_EXIT=%ERRORLEVEL%"
echo.
if not "%SHOPADS_EXIT%"=="0" echo ShopAds failed. See the error and Logs folder above.
pause
exit /b %SHOPADS_EXIT%
