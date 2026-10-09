# Registro de decisiones

Una entrada por decisión, la más reciente arriba. No se borran entradas: si algo cambia, se
añade otra que la sustituye.

Formato: **fecha · decisión** · motivo · qué cambia.

---

**2026-10-09 · Flujos 2 y 3 construidos (misma rama)** · Demo: el webhook firmado de Retell deja el lead en
demo_hecha / no_contesta / no_contactar; reintento máx. 1 vez; «no me llaméis» bloquea para siempre ese
lead. Seguimiento: botones Es cliente / Perdido y recordatorio a las 48 h · **Ningún mensaje al lead sale
solo**: las tarjetas llevan enlace wa.me y el dueño escribe a mano (LSSI; WhatsApp API exige plantillas de
Meta). Borradores en `automatizacion/plantillas/whatsapp-seguimiento.md`, pendientes de aprobación.

**Pendiente del dueño** · Aprobar o cambiar las 3 plantillas de WhatsApp · Decidir el texto de aviso bajo el
formulario («Te llamará nuestra recepcionista con IA… la llamada se graba») y revisarlo con el gestor ·
Número importado en Retell para la demo.

**2026-10-09 · Flujo 1 construido (rama `claude/leads-entrantes` de Deika-panel)** · El formulario de la
web ya enviaba al Worker del panel · Leads en D1 (`leads`, `lead_acciones`); n8n clasifica con
`claude-haiku-5-5` y manda tarjeta a Telegram con botones Le llamo yo / Demo DEIKA / Descartar. La demo
con Retell es ROJO: solo sale si un aprobador pulsa el botón. Topes en el Worker: 10 demos/día, solo
teléfonos +34, una decisión por lead. Pendiente desplegar y configurar (ver `automatizacion/README.md`).

**2026-10-09 · Leads en D1, no en Supabase** (sustituye a la entrada de Supabase de abajo) · El panel ya
tiene D1, límites y administración en el mismo Worker · Un servicio menos que mantener.

**2026-10-09 · Respuesta al lead = llamada, no email** · El formulario de la cabecera solo pide negocio y
teléfono, y la web promete "te llamamos hoy" · Cal.com no hace falta para el flujo 1.

**2026-10-09 · Número para llamadas salientes de demo** · Según la documentación de Retell, un número
comprado en Retell solo llama a EE. UU. · Para llamar a +34 hace falta un número importado (p. ej. Twilio).

**2026-10-09 · Aprobaciones por Telegram** · Botones inline sencillos y el dueño lo tiene en el
móvil · Los flujos de n8n usan un bot de Telegram con Aprobar/Rechazar.

**2026-10-09 · Leads en Supabase** · Log y permisos reales (Postgres, RLS) · Base aparte de la
D1 del panel: los leads (prospectos) y los clientes son dominios distintos. Cuando un lead se
convierte en cliente, el alta en el panel sigue siendo manual (`npm run alta`).

**2026-10-09 · n8n cloud** · Menos mantenimiento al empezar · Se puede migrar a autoalojado
más adelante exportando los flujos.

**2026-10-09 · Agenda de demos en Cal.com** · El panel ya usa Cal.com · Aparcado: el flujo 1 responde
con una llamada.

**2026-10-09 · Todo saliente es ROJO** · Punto de partida acordado · Sin excepciones hasta que
haya historial de aprobaciones.

## Tensiones abiertas

- **Un sector o varios.** La web propone titular centrado en talleres; la skill `deika-redes`
  pide mezclar sectores en redes. Pendiente de que el dueño decida si se alinean.
