@echo off
rem Arranca el servidor de Minecraft (Fabric) y lo reinicia si se cae.
rem Uso: doble clic en start.bat  (Ctrl+C durante la cuenta atras para salir del todo)

cd /d "%~dp0"

set MC_VERSION=1.21.11
set LOADER_VERSION=0.19.5
set INSTALLER_VERSION=1.1.2
set INSTALLER_SHA1=74685b5a0178c4dabd4be741a276d35c59b5ec96
set INSTALLER=fabric-installer-%INSTALLER_VERSION%.jar

rem Primera vez: si faltan los archivos del servidor, instala Fabric.
set NEEDS_INSTALL=0
if not exist fabric-server-launch.jar set NEEDS_INSTALL=1
if not exist server.jar set NEEDS_INSTALL=1
if not exist libraries\ set NEEDS_INSTALL=1
if "%NEEDS_INSTALL%"=="0" goto loop

echo Instalando Fabric %LOADER_VERSION% para Minecraft %MC_VERSION%...
curl -fSL -o "%INSTALLER%" "https://maven.fabricmc.net/net/fabricmc/fabric-installer/%INSTALLER_VERSION%/%INSTALLER%"
if errorlevel 1 goto error
certutil -hashfile "%INSTALLER%" SHA1 | findstr /i "%INSTALLER_SHA1%" >nul
if errorlevel 1 (
    echo ERROR: el instalador descargado no es el esperado.
    del "%INSTALLER%"
    goto error
)
java -jar "%INSTALLER%" server -mcversion %MC_VERSION% -loader %LOADER_VERSION% -downloadMinecraft -dir .
if errorlevel 1 goto error
del "%INSTALLER%"

:loop
java -Xmx4G -Xms2G -jar fabric-server-launch.jar nogui
echo El servidor se ha detenido. Se reinicia en 10 segundos (Ctrl+C para salir).
timeout /t 10
goto loop

:error
echo No se pudo instalar Fabric. Revisa el mensaje de arriba.
pause
exit /b 1
