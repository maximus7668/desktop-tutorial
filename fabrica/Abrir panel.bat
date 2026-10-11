@echo off
rem Abre el panel de la fabrica en el navegador. Doble clic para usarlo.
rem El proyecto se guarda en Documentos\Juegos\mi_juego. Para usar otra carpeta,
rem crea la variable FABRICA_PROYECTO con la ruta (setx FABRICA_PROYECTO "C:\ruta").
cd /d "%~dp0"
set PY=python
python --version >/dev/null 2>nul
if errorlevel 1 (
  set PY=py
  py --version >/dev/null 2>nul
  if errorlevel 1 (
    echo No encuentro Python. Instalalo desde python.org y marca "Add python.exe to PATH".
    pause
    exit /b 1
  )
)
if "%FABRICA_PROYECTO%"=="" set "FABRICA_PROYECTO=%USERPROFILE%\Documents\Juegos\mi_juego"
echo Proyecto: %FABRICA_PROYECTO%
%PY% -m fabrica panel -p "%FABRICA_PROYECTO%"
pause
