$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot

function Assert-NativeSuccess {
    param([string]$Step)
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE."
    }
}

$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    python -m venv (Join-Path $projectRoot '.venv')
    Assert-NativeSuccess 'Create virtual environment'
}
& $venvPython -m pip install --disable-pip-version-check -r requirements.txt
Assert-NativeSuccess 'Install dependencies'
& $venvPython -m unittest discover -s tests -v
Assert-NativeSuccess 'Run tests'
& $venvPython -m PyInstaller --noconfirm --clean --onefile --name ShopAds --paths $projectRoot shopads\__main__.py
Assert-NativeSuccess 'Build executable'
Copy-Item -LiteralPath (Join-Path $projectRoot 'dist\ShopAds.exe') -Destination (Join-Path $projectRoot 'ShopAds.exe') -Force
Write-Host 'Build completed: ShopAds.exe'
