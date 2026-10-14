@echo off
cd /d "%~dp0"
echo Apagando el servidor (el mundo se guarda)...
docker compose stop
pause
