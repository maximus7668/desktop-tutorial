@echo off
REM Descarga de GitHub las investigaciones nuevas (y mejoras del sistema).
REM El trabajador las importa solo en menos de una hora; o ejecuta: .venv\Scripts\python -m app.cli import-inbox
cd /d "%~dp0"
git pull --ff-only
if errorlevel 1 (
  echo No se pudo actualizar. Si cambiaste archivos del codigo, avisa antes de forzar nada.
  pause
  exit /b 1
)
echo Actualizado. Si hubo cambios de codigo, cierra las ventanas Panel y Trabajador y vuelve a abrir iniciar-windows.bat
pause
