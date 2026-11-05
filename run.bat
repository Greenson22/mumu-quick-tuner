@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Membuat virtual environment...
    py -3 -m venv .venv 2>nul || python -m venv .venv
    if not exist ".venv\Scripts\python.exe" (
        echo Gagal membuat virtual environment. Pastikan Python 3.10+ terpasang.
        pause
        exit /b 1
    )
)

echo [2/3] Memasang dependensi...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
    echo Gagal memasang dependensi.
    pause
    exit /b 1
)

echo [3/3] Menjalankan MuMu Quick Tuner...
".venv\Scripts\python.exe" -m app.main
if errorlevel 1 pause
endlocal
