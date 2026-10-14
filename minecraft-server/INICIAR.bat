@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Servidor Minecraft crossplay

where docker >nul 2>nul
if errorlevel 1 (
  echo No encuentro Docker. Instala Docker Desktop y vuelve a abrir este archivo:
  echo https://www.docker.com/products/docker-desktop/
  start https://www.docker.com/products/docker-desktop/
  pause
  exit /b
)

docker info >nul 2>nul
if errorlevel 1 (
  echo Abriendo Docker Desktop, espera...
  start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
  :esperar
  timeout /t 5 >nul
  docker info >nul 2>nul
  if errorlevel 1 goto esperar
)

if not exist .env (
  copy .env.example .env >nul
  echo.
  echo Se va a abrir el archivo .env en el Bloc de notas.
  echo Pon tu nombre en OPS y los jugadores en WHITELIST
  echo ^(los de PlayStation con un punto delante, por ejemplo .GamertagAmigo^).
  echo Guarda ^(Ctrl+S^), cierra el Bloc de notas y el servidor arrancara.
  echo.
  pause
  notepad .env
)

echo Arrancando el servidor (la primera vez tarda unos minutos)...
docker compose up -d
echo.
echo Cuando veas "Done" y "Started Geyser" ya se puede entrar.
echo Puedes cerrar esta ventana: el servidor sigue encendido.
echo Para apagarlo, abre APAGAR.bat
echo.
docker compose logs -f --tail 50 mc
