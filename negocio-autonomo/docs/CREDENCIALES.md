# Credenciales y servicios que tienes que configurar tú

Ninguna clave se escribe en el código ni en el repositorio. Todas van en `.env` (o en el gestor de
secretos de tu servidor). El sistema funciona sin ninguna; cada una desbloquea algo concreto.

| # | Qué | Para qué | Cómo | Obligatorio |
|---|---|---|---|---|
| 1 | `SECRET_KEY` | Firmar sesiones del panel | `python -c "import secrets;print(secrets.token_urlsafe(48))"` | Sí en producción |
| 2 | Usuario administrador | Entrar al panel | `python -m app.cli create-admin tu_usuario` | Sí |
| 3 | `OWNER_LEGAL_NAME`, `OWNER_TAX_ID`, `OWNER_ADDRESS`, `OWNER_CONTACT_EMAIL` | Aviso legal (LSSI) y consentimiento | Tus datos reales de titular | Sí para publicar |
| 4 | Dominio + HTTPS y `PUBLIC_BASE_URL` | Que las páginas sean accesibles y los datos cuenten como reales | Registrador de dominios + Caddy/Cloudflare | Para validar con tráfico real |
| 5 | `ANTHROPIC_API_KEY` + `LLM_PROVIDER=anthropic` | Investigación automática con búsqueda web | console.anthropic.com → API keys. **Pon un límite de gasto mensual en la consola** además del sobre interno | No |
| 6 | `API_MONTHLY_ENVELOPE_EUR` | Gasto de API que autorizas por adelantado | Recomendado 5-10 € cuando aportes capital (con 0 € no se usa) | Si usas el modelo |
| 7 | Cuenta Stripe verificada + Payment Link por producto | Cobrar | dashboard.stripe.com → Payment Links; pega el enlace en Ajustes → Enlaces de pago | Para vender |
| 8 | `STRIPE_WEBHOOK_SECRET` | Registrar pedidos y reembolsos | Stripe → Developers → Webhooks → endpoint `https://tu-dominio/webhooks/stripe`, eventos `checkout.session.completed` y `charge.refunded` | Para vender |
| 9 | `SMTP_*` | Enviar emails (respuestas, avisos a la lista de espera) | Tu proveedor de email transaccional | No |
| 10 | Copia externa de `backups/` | Recuperación ante pérdida del servidor | rclone/Syncthing/almacenamiento del proveedor | Muy recomendable |

Antes de poner `commerce_authorized=on` el panel exige completar el checklist de **Ajustes → Cumplimiento**
(alta censal, Seguridad Social, IVA/OSS, facturación/Verifactu, condiciones de venta, Stripe verificado,
revisión profesional). Estas cuestiones dependen de tu situación fiscal concreta: consúltalas con un asesor.

## Prueba de cada integración tras configurarla

- Modelo: Tareas → `research.discover` con `{"topic": "plantillas para autónomos", "run_id": "prueba-1"}`.
  Revisa Finanzas → Uso del modelo y el coste estimado.
- Stripe: en modo test de Stripe, «Send test webhook». Debe aparecer un pedido marcado **simulation**.
- SMTP: el adaptador (`app/integrations/email.py`) existe y exige el permiso `email.send`, pero **todavía no está
  conectado a ningún flujo**: las respuestas a consultas quedan como borrador en Consultas y las envías tú.
