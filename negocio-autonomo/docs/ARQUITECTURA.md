# Arquitectura, plan y decisiones

## 1. Inspección inicial (20/10/2026)

- El repositorio `desktop-tutorial` contenía solo skills de Claude Code del negocio DEIKA y un plugin;
  no había código de aplicación. El sistema se crea en la carpeta independiente `negocio-autonomo/`
  para no mezclarlo con DEIKA.
- Entorno disponible: Python 3.13, FastAPI, Uvicorn, Jinja2, Pydantic, SDK de Anthropic 1.15, SQLite,
  cliente `psql` (sin servidor PostgreSQL), Chromium para capturas. **Docker instalado pero sin demonio.**
- Credenciales presentes: ninguna (no hay `ANTHROPIC_API_KEY`, Stripe ni SMTP). Por eso todo el sistema
  funciona sin modelo de IA y las integraciones de pago y email quedan como adaptadores probados con
  datos de prueba.

## 2. Arquitectura mínima elegida

```
                 ┌──────────────── Panel web (FastAPI + Jinja2, sesión + CSRF) ───────────────┐
 propietario ───►│ aprobaciones · ajustes · permisos · checklist legal · parada · exportación │
                 └──────────────┬─────────────────────────────────────────────────────────────┘
                                │ decisiones humanas (approvals.decide → efectos)
 visitantes ──► /p/<slug> ──────┤  visitas, registros, consultas (analítica propia sin cookies)
 Stripe ──────► /webhooks/stripe┤  firma HMAC → pedidos idempotentes
                                ▼
                      SQLite (WAL) ── audit_log encadenado · settings · permissions · spend_requests
                                ▲     ledger · opportunities · evidence · experiments · products
                                │     events · orders · tasks · schedules · memory · alerts
 trabajador ── cola + programación ── agentes: director → evaluador / investigador / constructor
                                                ventas · operaciones
                                       │
                         herramientas solo vía permissions.authorize() y budget.request_spend()
```

Principios aplicados:

1. **Flujos fijos, no agentes libres.** Cada agente es código con un objetivo acotado. El modelo de IA
   (si se configura) solo produce *datos* (investigación en JSON) que se validan con esquemas; nunca
   decide qué herramienta usar ni puede aprobar nada.
2. **Controles en el servidor.** Presupuesto, permisos, modo y parada se comprueban en la capa de datos
   dentro de transacciones `BEGIN IMMEDIATE`; no dependen de que el modelo "obedezca".
3. **Separar real / estimación / simulación** en cada tabla que mueve números (`data_kind`).
4. **Idempotencia en todo lo que se puede reintentar**: tareas, gastos, llamadas al modelo, pedidos.

## 3. Decisiones técnicas y por qué

| Opción evaluada | Decisión | Motivo |
|---|---|---|
| Python | **Sí** | Lógica de agentes y servicios; ya disponible. |
| OpenAI Agents SDK | **No (por ahora)** | No hay modelos de OpenAI configurados y el stack del propietario usa Anthropic. El proveedor es intercambiable (`app/integrations/llm.py`): un `OpenAIProvider` encaja implementando `complete()`. |
| SDK de Anthropic | **Opcional** | `LLM_PROVIDER=anthropic`. Uso verificado contra el SDK instalado (1.15): `client.beta.messages.create` con `fallbacks="default"`, herramienta `web_search_20260209`, bloques `web_search_result` con `url`. **No se ha llamado a la API real** (no hay clave). |
| n8n | **No** | La cola persistente + programación interna cubren el MVP sin otro servicio que mantener. Si más adelante se quieren integraciones visuales, n8n puede llamar a la API interna. |
| PostgreSQL vs SQLite | **SQLite (WAL)** | Una sola instancia, cero coste, copias con la API de backup. El SQL es estándar; migrar a PostgreSQL es viable si hay varias instancias. |
| FastAPI | **Sí** | Panel, páginas públicas, webhook y salud. Sin documentación OpenAPI pública. |
| Interfaz | **HTML renderizado en servidor, sin JavaScript** | Menos superficie de ataque; CSP `script-src 'none'`. |
| Docker Compose | **Sí (no probado aquí)** | `web` + `worker` sobre un volumen. |
| Pagos | **Stripe Payment Links + webhook firmado** | El sistema no maneja tarjetas ni la clave secreta de la API de Stripe; solo verifica webhooks. |
| Búsqueda web | **Herramienta de búsqueda del servidor de Anthropic** o importación manual de JSON | Sin scraping propio: se evita incumplir condiciones de sitios. Las URLs citadas por el modelo se aceptan solo si aparecen en los resultados reales de búsqueda. |
| Analítica | **Propia, sin cookies** | Hash diario de IP+UA (no se guarda la IP). Menos obligaciones de consentimiento de cookies. |

## 4. Fases y estado

| Fase | Contenido | Estado |
|---|---|---|
| 1. Inspección y plan | Este documento | Hecho |
| 2. MVP | Investigador, evaluador, director, memoria, presupuesto, panel | Hecho y probado |
| 3. Productos | Generación de landing, comprobaciones técnicas, publicación con aprobación | Hecho y probado |
| 4. Comercial | Analítica, pedidos, webhook Stripe, seguimiento financiero, activación de cobros con checklist | Hecho; Stripe real **no probado** (sin cuenta) |
| 5. Automatización | Cola, reintentos, programación, recuperación, agentes de ventas y operaciones | Hecho y probado |
| 6. Producción | Pruebas, instalación, `.env.example`, despliegue, copias, monitorización, limitaciones | Hecho (Docker sin probar) |

## 5. Criterios de aceptación (y cómo se verifican)

| Criterio | Verificación |
|---|---|
| Nunca se compromete más de capital − suelo | `test_never_exceeds_available_budget`, `test_concurrent_agents_cannot_overspend` |
| Gasto rechazado o pendiente no se ejecuta | `test_rejected_spend_is_never_executed`, `test_pending_spend_cannot_execute_and_agent_cannot_approve` |
| Agentes no cambian permisos, ajustes ni aprueban | `test_agents_cannot_change_permissions_or_settings` |
| Ninguna acción con dinero es automática | `test_financial_actions_never_auto_allowed` |
| Las claves no aparecen en logs ni auditoría | `test_secrets_never_reach_logs_or_audit` |
| Fallos de API = fallo, nunca éxito | `test_api_error_is_failure_not_success`, `test_unconfigured_integration_is_not_presented_as_success` |
| Simulación ≠ ingresos; solo compras reales validan | `test_simulated_sales_are_not_real_revenue`, `test_only_real_purchases_validate`, `test_simulated_traffic_never_validates` |
| Sin pedidos duplicados al reintentar | `test_orders_are_not_duplicated_on_retry`, `test_webhook_in_test_env_is_simulation_and_retry_safe` |
| Recuperación tras reinicio | `test_recovers_running_task_after_crash`, `test_budget_survives_restart` |
| Aprobaciones humanas funcionan | `test_full_cycle` (por HTTP con CSRF) |
| Parada detiene todo lo externo | `test_kill_switch_stops_all_external_actions`, paso 8 de `test_full_cycle` |

## 6. Esquema de datos

Migración única `app/migrations/001_init.sql` (se aplica sola en `bootstrap`; las siguientes serán
`002_*.sql`, etc., registradas en `schema_migrations`). Importes siempre en **céntimos** (enteros).
Restricciones relevantes en la propia BD:

- `audit_log`: triggers que impiden `UPDATE` y `DELETE`.
- `experiments`: trigger que impide cambiar métrica, umbral, mínimo de visitas o presupuesto una vez fijados.
- `spend_requests.idempotency_key`, `tasks.idempotency_key`, `orders(provider, external_id)`: únicos.
- `CHECK` en todos los estados y en `data_kind`.

## 7. Defensa frente a inyección de instrucciones

- Todo texto externo pasa por `untrusted.clean()` (normaliza, quita caracteres de control/bidireccionales, acota longitud).
- Patrones típicos de inyección rebajan la evidencia a fiabilidad baja y la marcan.
- El texto externo nunca selecciona herramientas: las acciones las decide código fijo y las autoriza `permissions`.
- Las respuestas del modelo se validan con Pydantic; las URLs se contrastan con los resultados reales de búsqueda.
- Las páginas se renderizan con autoescape; el análisis interno de una oportunidad no se publica (solo `benefits`).
- El agente de ventas solo usa respuestas aprobadas; lo demás o lo sospechoso se escala a una persona.
