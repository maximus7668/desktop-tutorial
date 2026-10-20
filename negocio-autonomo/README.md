# Negocio autónomo supervisado (MVP)

Sistema pequeño para **descubrir oportunidades de productos digitales, validarlas con experimentos baratos
y, solo cuando el propietario lo autorice, vender**, protegiendo el capital que aportes. **Arranca con 0 €**: sin capital no puede gastar nada
y trabaja solo con herramientas gratuitas; cuando aportes dinero (panel → Finanzas → Aportar capital, o
`python -m app.cli add-capital 300`), el 80 % queda disponible y el 20 % es suelo intocable.

No es una IA que lo hace todo sola: los agentes investigan, puntúan, proponen, construyen y miden;
**gastar, publicar, cobrar y cambiar permisos lo decide siempre una persona** (o un sobre de gasto
que la persona fijó antes). Todo queda en un registro de auditoría a prueba de manipulación.

## Qué hay dentro

| Pieza | Dónde | Qué hace |
|---|---|---|
| Presupuesto | `app/budget.py` | Reserva atómica de gasto, suelo intocable (20 % del capital), límites por gasto/día/experimento, aprobación humana, aportaciones de capital registradas |
| Permisos | `app/permissions.py` | Agente × herramienta × acción; techo por modo (1/2/3); el dinero nunca pasa de «aprobación» |
| Auditoría | `app/audit.py` | Solo inserción (triggers) y cadena de hashes SHA-256 verificable |
| Aprobaciones | `app/approvals.py` | Cola de decisiones humanas; nadie aprueba lo suyo |
| Parada de emergencia | `app/settings_store.py` | Cualquiera la activa; solo una persona la quita; bloquea toda acción externa |
| Cola de tareas | `app/tasks.py`, `app/worker.py` | Persistente, idempotente, reintentos limitados, recuperación tras caída, pausa/reanudar |
| Memoria | `app/memory.py` | Investigaciones, decisiones, lecciones; evita repetir experimentos fallidos |
| Validación | `app/validation.py` | Hipótesis + presupuesto + criterio fijados antes; solo compras reales validan |
| Agentes | `app/agents/` | investigador, evaluador, director, constructor, ventas, operaciones |
| Integraciones | `app/integrations/` | Modelo (Anthropic), búsqueda web, Stripe (webhooks), SMTP, analítica propia |
| Cumplimiento | `app/compliance.py` | Checklist legal/fiscal que bloquea publicar y cobrar hasta que lo confirmes |
| Panel | `app/web/` | Resumen, aprobaciones, finanzas, auditoría, ajustes, exportación CSV/JSON |

Arquitectura y decisiones: [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md).

## Puesta en marcha (local, 5 minutos)

Requisitos: Python 3.11+ (probado con 3.13).

```bash
cd negocio-autonomo
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # edita .env: al menos OWNER_* si vas a publicar algo
python -m app.cli init          # crea data/test.db con migraciones y datos base
python -m app.cli create-admin tu_usuario   # pide la contraseña (mín. 12 caracteres)
python -m app.cli serve         # panel en http://127.0.0.1:8000
```

En otra terminal, el trabajador (ejecuta la cola y las tareas programadas):

```bash
python -m app.cli worker
```

### Comprobar que funciona

```bash
python -m pytest -q                                   # 45 pruebas, ~3 s
python examples/demo_validacion.py                    # ciclo completo en data/demo.db → docs/ejemplo-validacion.md
python -m app.cli import-research examples/investigacion_2026-10-20.json
python -m app.cli evaluate                            # puntuaciones
python -m app.cli status                              # saldo, tareas, finanzas
python -m app.cli verify-audit                        # integridad del registro
curl http://127.0.0.1:8000/healthz
```

En el panel: **Tareas → director.cycle → Encolar**. Con el trabajador en marcha verás en **Aprobaciones**
el experimento propuesto. Al aprobarlo se construye la página y se pide aprobar su publicación (antes
tendrás que confirmar el checklist de **Ajustes → Cumplimiento**).

## Docker

```bash
cp .env.example .env    # APP_ENV=production, SECRET_KEY largo, OWNER_*, etc.
docker compose up -d --build
docker compose exec web python -m app.cli create-admin tu_usuario
```

Levanta `web` (panel + páginas públicas + webhook) y `worker` sobre el mismo volumen SQLite.
El puerto solo escucha en 127.0.0.1: publícalo detrás de un proxy con HTTPS (Caddy, Nginx, Cloudflare Tunnel).
**Nota:** el Dockerfile y el compose no se han podido probar en el entorno donde se desarrolló (no había
demonio de Docker); sí se ha probado todo lo demás directamente con Python.

## Qué hace con 0 € y qué cambia al aportar dinero

| | Con 0 € | Con capital aportado |
|---|---|---|
| Investigación | Importando investigaciones en JSON (hechas a mano o en una sesión como esta) | También automática con el modelo, si configuras la clave y el sobre de API |
| Evaluación, experimentos, páginas, métricas | Sí (gratis) | Sí |
| Publicar páginas | Sí, si lo sirves gratis (tu ordenador + Cloudflare Tunnel gratuito) | Igual, o en un VPS (~5 €/mes) |
| Anuncios, servicios, API de pago | Rechazado automáticamente («sin capital») | Con tu aprobación, dentro de los límites |
| Cobrar | Posible sin coste fijo (Stripe solo cobra comisión), tras el checklist legal/fiscal | Igual |

Los ingresos por ventas **no** se convierten solos en presupuesto: reinvertirlos es una aportación que decides tú.

## Modos de operación

| Modo | Para qué | Publicar | Gastar | Cobrar |
|---|---|---|---|---|
| 1 | Solo investigación | No | Solo API dentro del sobre | No |
| 2 (por defecto) | Validación controlada | Con aprobación | Con aprobación (API: sobre) | Con aprobación + checklist |
| 3 | Operación supervisada | Según tabla de permisos | Siempre con aprobación | Siempre con aprobación + checklist |

Se cambia en **Ajustes** (`mode`). Ningún modo desactiva los controles financieros ni la parada de emergencia.

## Datos reales, estimaciones y simulaciones

- **real**: solo en `APP_ENV=production` (visitas y registros que entran por HTTP) y pedidos de Stripe en
  modo *live* con `commerce_authorized=on`.
- **estimate**: puntuaciones, coste de API calculado por tokens.
- **simulation**: todo lo del entorno de pruebas y los eventos *test* de Stripe. Nunca suma a ingresos
  ni valida un experimento.

## Documentación

- [`docs/WINDOWS.md`](docs/WINDOWS.md): puesta en marcha en Windows paso a paso (0 €).
- [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md): plan, decisiones técnicas, criterios de aceptación, esquema de datos.
- [`docs/OPERACION.md`](docs/OPERACION.md): despliegue, copias de seguridad, monitorización, parada de emergencia, limitaciones conocidas.
- [`docs/CREDENCIALES.md`](docs/CREDENCIALES.md): qué tienes que configurar tú y cómo.
- [`docs/APROBACIONES.md`](docs/APROBACIONES.md): todo lo que sigue requiriendo una decisión humana.
- [`docs/COSTES.md`](docs/COSTES.md): costes fijos y variables estimados.
- [`docs/PRUEBAS.md`](docs/PRUEBAS.md): pruebas ejecutadas y resultados observados.
- [`docs/INVESTIGACION-EJEMPLO.md`](docs/INVESTIGACION-EJEMPLO.md): investigación de mercado real con fuentes.
- [`docs/ejemplo-validacion.md`](docs/ejemplo-validacion.md): creación y validación de un producto (salida del script de demo).
