# Registro de decisiones

Una entrada por decisión, la más reciente arriba. No se borran entradas: si algo cambia, se
añade otra que la sustituye.

Formato: **fecha · decisión** · motivo · qué cambia.

---

**2026-10-09 · Carga de OpenStreetMap vía n8n** · Overpass rechaza las peticiones desde Cloudflare · Flujo n8n
«DEIKA · Cargar negocios de Vitoria» (lunes 9 h + webhook). El botón del panel y el cron llaman a ese webhook
(secreto `OSM_N8N_URL`); si falla, prueban Overpass directo. 390 negocios cargados.

**2026-10-09 · ESTADO AL CERRAR LA SESIÓN** (producción = rama `claude/despliegue-cloudflare` de Deika-panel, commit 885ae61+)
- Activo: leads con clasificación Claude (ANTHROPIC_API_KEY puesta y probada), avisos por el relé, decisiones en
  Administración → Leads, demo con +34945524251 y agente `agent_27903ca89b6d8f0e8ad87775b8` (bloqueo automático
  desde el 17/10 si no es +34400), recordatorios, onboarding, baja de negocios (borra agente, ocultar),
  prospección (carga OSM automática si vacía / lunes 9 h; 2 investigaciones a las 10 h laborables).
- Desactivado: informe semanal (INFORME_SEMANAL), espera ok del dueño.
- Twilio: paquete National BU2bb1ff…2b35a en revisión. Los números de España NO se compran por API (Exclusive
  Number order / formulario en la consola): lo hace el dueño. Hay una comprobación programada (send_later).
- Email en frío: NO (LSSI art. 21). Contacto = visitas en persona.
- Pendiente del dueño: gestor (400 y email), comprar 400/945 en consola, probar la demo con su móvil, tope de
  gasto en console.anthropic.com, decisiones de la web (sector, audio, cifras, euskera), rotar claves.

**2026-10-09 · Desplegado en producción** (Worker deika-panel + web deika.eu + migraciones 0010-0012) · Lo
pidió el dueño · Activo: leads guardados y avisados, decisiones en Administración, recordatorios, puesta en
marcha, prospección (OpenStreetMap los lunes). Desactivado: informe semanal (`INFORME_SEMANAL`), demo
(`RETELL_DEMO_*`, pendiente del 400) y Claude (`ANTHROPIC_API_KEY`, sin clave aún).

**2026-10-09 · Las decisiones se toman en el panel, no con botones de Telegram** · El bot lo tiene el relé
`deika-relay-demo`, que solo manda texto, y n8n no tiene credencial de Telegram · Telegram avisa con enlace;
Administración → Leads / Prospección decide (hay que estar identificado). n8n queda opcional.

**2026-10-09 · Flujo 5 (prospección) = visitas en persona** · Email en frío pendiente del gestor (LSSI),
Instagram automático prohibido, llamadas en frío con IA no · OpenStreetMap + web del negocio, 10/semana,
solo citas literales, tarjeta «Visitar / Descartar / No contactar». No se envía nada. Privacidad actualizada.

**2026-10-09 · Flujo 4 (onboarding)** · El alta ya existía en el panel · Añadido: puesta en marcha (qué le falta
a cada alta, aviso L y J) e informe semanal por correo, **desactivado** hasta `INFORME_SEMANAL=activo`.

**2026-10-09 · Twilio: paquete «Spain: National – Individual» enviado a revisión** (BU2bb1ff…2b35a), con el DNI
y el titular ya aprobados · Para comprar un +34 400 para la demo · Twilio no vende números de España por API:
la compra, cuando apruebe el paquete, desde la consola. Agente de demo en Retell creado y publicado
(`agent_27903ca89b6d8f0e8ad87775b8`).

**2026-10-09 · Número de la demo: Twilio** · Lo confirma el dueño · Se importa en Retell por SIP trunk
(Geographic Permissions con España); pasos en `automatizacion/README.md`.

**2026-10-09 · Aviso de IA y grabación bajo el formulario + privacidad actualizada** · El dueño lo delegó
(«hazlo como mejor creas») · Cambio en `web-deika-eu/` (rama `claude/leads-entrantes`), sin publicar hasta
desplegar. Recomendado que lo revise el gestor.

**ALERTA LEGAL · Prefijo 400 desde ~17/10/2026** · BOE-A-2026-8409: las empresas en el ámbito de la Ley
10/2025 solo pueden hacer llamadas comerciales desde números 400 · Pendiente de que el gestor diga si DEIKA
está dentro y si la demo pedida por el lead cuenta como comercial. Hasta entonces, demo desactivada en
producción desde el 17/10 (sin `RETELL_DEMO_*`).

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
