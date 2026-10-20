@echo off
REM Arranca el panel y el trabajador en dos ventanas. Deja ambas abiertas.
cd /d "%~dp0"
if not exist .venv\Scripts\activate.bat (
  echo Falta el entorno .venv. Sigue docs\WINDOWS.md paso 3.
  pause
  exit /b 1
)
start "Panel (no cerrar)" cmd /k ".venv\Scripts\activate.bat && python -m app.cli serve"
start "Trabajador (no cerrar)" cmd /k ".venv\Scripts\activate.bat && python -m app.cli worker"
echo Panel en http://127.0.0.1:8000
