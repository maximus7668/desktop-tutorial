@echo off
REM Arranca n8n en local (sin suscripcion). Datos en D:\IA\n8n\datos. Panel en http://127.0.0.1:5678
set N8N_USER_FOLDER=D:\IA\n8n\datos
set N8N_HOST=127.0.0.1
set N8N_LISTEN_ADDRESS=127.0.0.1
set N8N_PORT=5678
set GENERIC_TIMEZONE=Europe/Madrid
set TZ=Europe/Madrid
set N8N_DIAGNOSTICS_ENABLED=false
set N8N_PERSONALIZATION_ENABLED=false
set EXECUTIONS_DATA_PRUNE=true
set EXECUTIONS_DATA_MAX_AGE=720
"D:\IA\n8n\node\node.exe" "D:\IA\n8n\app\node_modules\n8n\bin\n8n" %*
