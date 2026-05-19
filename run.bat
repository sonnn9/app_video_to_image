@echo off
cd /d "%~dp0"
if not exist "venv" (
    echo Dang tao moi truong ao...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo Dang cai dat thu vien...
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)
python main.py
pause
