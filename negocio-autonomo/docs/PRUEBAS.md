# Informe de pruebas (20/10/2026)

Entorno: Linux, Python 3.13, pytest 9.1.1, FastAPI 0.150.0, SQLite. Comando: `python -m pytest -v`.

**Resultado: 54 pruebas, 54 superadas, 0 fallidas (≈ 4 s).** Análisis estático `ruff check --select F,E9,B`: sin avisos.

## Qué se comprueba

| Requisito | Pruebas | Resultado |
|---|---|---|
| Nunca se supera el presupuesto autorizado | `test_never_exceeds_available_budget` (20 × 50 € pedidos → solo 400 € aprobables), `test_single_and_daily_limits` | ✔ |
| Dos agentes no gastan a la vez por encima del límite | `test_concurrent_agents_cannot_overspend` (8 hilos con conexiones propias, 800 € pedidos → exactamente 400 € aprobados) | ✔ |
| Un gasto rechazado no se ejecuta | `test_rejected_spend_is_never_executed`, `test_pending_spend_cannot_execute_and_agent_cannot_approve` | ✔ |
| Las claves no aparecen en logs | `test_secrets_never_reach_logs_or_audit` (logs y auditoría) | ✔ |
| Los agentes no cambian sus permisos | `test_agents_cannot_change_permissions_or_settings`, `test_financial_actions_never_auto_allowed`, `test_unknown_or_unassigned_permission_is_denied`, `test_mode_1_blocks_publishing` | ✔ |
| Errores de API no se presentan como éxitos | `test_api_error_is_failure_not_success`, `test_unconfigured_integration_is_not_presented_as_success`, `test_failed_execution_is_recorded_as_failure`, `test_worker_runs_and_marks_unknown_failures` | ✔ |
| Ventas simuladas ≠ ingresos reales | `test_simulated_sales_are_not_real_revenue`, `test_webhook_in_test_env_is_simulation_and_retry_safe`, `test_webhook_real_only_in_production_with_commerce_authorized` | ✔ |
| Pedidos no duplicados al reintentar | `test_orders_are_not_duplicated_on_retry`, `test_refund_recorded_once`, `test_spend_request_is_idempotent`, `test_enqueue_is_idempotent`, `test_schedules_do_not_duplicate` | ✔ |
| Recuperación tras reinicio | `test_recovers_running_task_after_crash`, `test_budget_survives_restart`, `test_limited_retries_then_failed`, `test_pause_and_resume_queue_keeps_state` | ✔ |
| Aprobaciones humanas funcionan | `test_full_cycle` (por HTTP, con login y CSRF) | ✔ |
| Se pueden detener todas las acciones externas | `test_kill_switch_stops_all_external_actions` + paso 8 de `test_full_cycle` | ✔ |
| Arranque con 0 € | `tests/test_zero_capital.py`: todo gasto rechazado (también API con sobre), el modelo no se llama, la vigilancia no activa la parada, el flujo gratuito funciona, aportar capital desbloquea y queda en el libro, reiniciar no duplica el capital; la E2E arranca con 0 € y aporta 300 € desde el panel | ✔ |
| Agente de contenido | `tests/test_content.py`: borradores al publicar con enlace por canal, sin duplicados, solo productos publicados, filtro de promesas/urgencia/estado, texto de IA solo si pasa el filtro, solo personas aprueban y publican, visitas y registros atribuidos a su canal, mayúsculas de nombres propios | ✔ |
| Auditoría inalterable / detectable | `test_audit_log_is_append_only_and_tamper_evident` | ✔ |
| Inyección de instrucciones | `test_prompt_injection_in_research_is_data_not_instruction`, `test_sales_agent_escalates_suspicious_or_unknown`, `test_discover_drops_urls_not_returned_by_real_search` | ✔ |
| Validación honesta | `test_score_penalizes_thin_evidence`, `test_criteria_locked_after_approval`, `test_simulated_traffic_never_validates`, `test_signups_give_interest_but_not_validation`, `test_low_interest_is_abandoned_and_remembered`, `test_only_real_purchases_validate` | ✔ |

**Extremo a extremo** (`tests/test_e2e.py`, datos ficticios): login fallido y correcto → importación de
investigación → ciclo del director desde el panel (y rechazo de CSRF inválido) → aprobación del experimento →
construcción y comprobaciones técnicas → publicación bloqueada por el checklist legal → checklist → publicación →
31 visitas (el bot no cuenta), registros con y sin consentimiento, registro duplicado, consulta respondida con
respuesta aprobada → checkout bloqueado sin comercio → fin de plazo y veredicto «datos_insuficientes» (la
simulación no cuenta) → todas las páginas del panel, exportación CSV y auditoría íntegra → parada de emergencia.

## ¿Las pruebas detectan fallos? (prueba de mutación manual)

| Fallo introducido a propósito | Resultado |
|---|---|
| Quitar el suelo de reserva del cálculo de presupuesto | 2 pruebas fallan (`never_exceeds`, `concurrent`) |
| Quitar la transacción `BEGIN IMMEDIATE` de `request_spend` | `test_concurrent_agents_cannot_overspend` falla en 3 de 3 ejecuciones |

Tras restaurar el código, todas vuelven a pasar.

## Errores encontrados y corregidos durante el desarrollo

1. **Encolado manual deduplicado por error**: dos tareas encoladas desde el panel en el mismo segundo compartían
   clave de idempotencia y la segunda se perdía. Lo detectó la prueba E2E; ahora la clave lleva un sufijo aleatorio.
2. **Análisis interno publicado**: la página de prueba copiaba la descripción interna de la oportunidad (p. ej.
   «hay mucha oferta barata…») como argumentos de venta. Detectado al revisar la captura de la página; ahora solo
   se publican los `benefits` y hay una prueba que lo comprueba.
3. **Contenido duplicado por idempotencia**: dos peticiones de borradores con IA en el mismo segundo compartían clave y la
   segunda se descartaba. Detectado por una prueba; ahora la clave es única por petición.
4. **Mayúsculas en los textos**: «España» e «IA» salían en minúscula. Detectado al revisar los borradores reales; corregido con prueba.
5. **Reserva de API infraestimada** para llamadas con búsqueda web (los resultados entran como tokens de entrada):
   se reservaba menos de lo que podría costar. Ahora la reserva supone ~60k tokens de entrada.

## Otras verificaciones manuales

- CLI: `init`, `create-admin`, `import-research`, `evaluate`, `verify-audit`, `backup` ejecutados con éxito en
  una BD temporal; `init` con `APP_ENV=production` sin `SECRET_KEY` se niega a arrancar.
- Panel servido con Uvicorn y revisado con Chromium (capturas de Resumen, Oportunidades y la página pública en móvil).
- `examples/demo_validacion.py` → genera `docs/ejemplo-validacion.md` y `examples/landing_ejemplo.html`.

## Lo que NO se ha probado

- Llamadas reales a la API de Anthropic (sin clave). El adaptador se escribió contra el SDK instalado (1.15).
- Webhooks reales de Stripe (sin cuenta). La verificación de firma sigue el esquema documentado por Stripe y se
  prueba con firmas generadas localmente.
- Envío SMTP real.
- `docker compose` (no había demonio de Docker).
- Carga con muchos usuarios simultáneos en el panel público.
