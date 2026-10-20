# Operación: despliegue, copias, monitorización y límites conocidos

## Entornos

- `APP_ENV=test` (por defecto): BD `data/test.db`; todo lo que entra por HTTP es **simulación**. Permite
  `ADMIN_PASSWORD` para automatizar pruebas.
- `APP_ENV=production`: BD `data/production.db`; exige `SECRET_KEY` ≥ 32 caracteres, cookies `Secure`,
  prohíbe `LLM_PROVIDER=fake`. Solo aquí hay datos **reales**.
- Las dos BD son ficheros distintos: nunca se mezclan.

## Despliegue recomendado (coste mínimo)

1. Un VPS pequeño (o un ordenador propio siempre encendido) con Docker.
2. `cp .env.example .env` → `APP_ENV=production`, `SECRET_KEY`, `PUBLIC_BASE_URL=https://tu-dominio`, `OWNER_*`.
3. `docker compose up -d --build` y `docker compose exec web python -m app.cli create-admin tu_usuario`.
4. Proxy HTTPS delante (Caddy: `tu-dominio { reverse_proxy 127.0.0.1:8000 }`), o Cloudflare Tunnel sin abrir puertos.
5. Comprobar `https://tu-dominio/healthz` y entrar al panel.

Sin Docker: `python -m app.cli serve` y `python -m app.cli worker` como servicios systemd.

## Copias de seguridad

- Automática: tarea programada `copia-seguridad` cada 24 h → `backups/<entorno>-AAAAMMDD-HHMMSS.db`
  (API de backup de SQLite, consistente con la app en marcha). Se guardan las 14 últimas.
- Manual: `python -m app.cli backup`.
- **Fuera de la máquina:** copia `backups/` a otro sitio (rclone, Syncthing, almacenamiento del proveedor).
  Esto no está automatizado: es tarea tuya.
- Restaurar: detén web y worker, `python -m app.cli restore backups/production-XXXX.db` (guarda la BD
  anterior como `.antes-de-restaurar` y verifica la auditoría), vuelve a arrancar.

## Monitorización

- `GET /healthz` → `{"ok": true, "kill_switch": "off"}` para un monitor externo (UptimeRobot, Healthchecks…).
- Tarea `vigilancia-presupuesto` (cada hora): alerta de saldo bajo, activa la parada si el gasto comprometido
  supera el presupuesto o si la cadena de auditoría está rota, avisa de aprobaciones con más de 3 días.
- Informe diario en `reports/informe-*.json` (finanzas, tareas, oportunidades, experimentos, aprobaciones, alertas).
- Panel → Resumen: alertas abiertas, tareas fallidas, estado de cada agente con su último error.
- Logs del proceso por salida estándar (`docker compose logs -f`), con secretos redactados.
- No hay avisos push/Telegram todavía: revisa el panel o conecta un monitor a `/healthz`.

## Parada de emergencia

- Panel → botón rojo **Parada de emergencia**, o `python -m app.cli stop "motivo"`.
- Efecto inmediato: ninguna herramienta externa (modelo, búsqueda, publicación, email, anuncios, pagos)
  pasa los permisos; no se aceptan nuevos gastos; el trabajador no toma tareas; el botón de compra
  redirige a la página. Las páginas ya publicadas siguen visibles (para retirarlas, para el servicio web).
- Solo una persona autenticada puede reanudar.

## Limitaciones conocidas

1. **Sin pruebas contra servicios reales**: API de Anthropic (no hay clave), Stripe (no hay cuenta), SMTP. Los
   adaptadores siguen la documentación y el SDK instalado, pero la primera ejecución real debe hacerse
   vigilando el panel y con importes mínimos.
2. **Docker no probado** en el entorno de desarrollo (sin demonio).
3. **Una sola instancia**: SQLite y el limitador de peticiones en memoria no sirven para varias réplicas.
4. **Agentes en el mismo proceso** que la lógica de control: la separación de permisos es lógica (tipo de actor
   comprobado en el servidor), no de proceso. Para aislamiento fuerte, ejecutar agentes con un usuario del SO
   sin acceso de escritura al fichero de la BD y exponerles solo una API.
5. **La cadena de auditoría detecta manipulaciones**, no las impide si alguien tiene acceso de escritura al fichero.
   Copia periódica fuera de la máquina = prueba independiente.
6. **Puntuación de oportunidades simple** (pesos fijos sobre estimaciones). Sirve para ordenar, no para predecir.
7. **Constructor sin modelo**: la página usa el título, la idea y los beneficios que aporta la investigación.
   No genera el producto digital en sí (plantillas, guía…): eso lo prepara el propietario si el experimento lo justifica.
8. **Anuncios, plataformas de venta (Gumroad, Etsy…), seguimiento externo de tareas**: solo adaptadores pendientes,
   marcados como «no configurado» en Ajustes → Integraciones.
9. **Textos legales** (aviso legal y privacidad) son plantillas: deben revisarse antes de publicar.
10. **Email**: el adaptador SMTP no está conectado a ningún flujo; las respuestas quedan en borrador y las
    consultas escaladas se resuelven fuera del sistema (aprobarlas solo deja constancia).
11. Los gastos que no son de API (anuncios, servicios) se registran y controlan, pero su **ejecución** es manual:
    el sistema no tiene acceso a ninguna cuenta bancaria ni de anuncios.
