@echo off
setlocal

cd /d "%~dp0backend"

set "PYTHON_EXE=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=.venv\Scripts\python.exe"

start "" cmd /c "timeout /t 2 >nul & start "" http://127.0.0.1:8765"
"%PYTHON_EXE%" -m dj_library_prep.cli serve-ui --database "..\djcuecraft.sqlite3" --port 8765
