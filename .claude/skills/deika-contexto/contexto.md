# Contexto: DEIKA y su automatización comercial

## 1. Qué es DEIKA

- Empresa de Vitoria-Gasteiz que vende una **recepcionista con IA por voz**: contesta las
  llamadas del negocio 24 h, da cita en la agenda, recoge datos, responde preguntas básicas,
  pasa la llamada a una persona cuando toca y manda un resumen al móvil.
- Web: https://deika.eu (landing, formulario de contratación, calculadora de llamadas perdidas, FAQ).
- Panel para clientes: repo `maximus7668/deika-panel` (PWA en Cloudflare Workers + D1; agenda de
  Cal.com, llamadas de Retell vía n8n, avisos push, recepción, plan).
- Precios (sin IVA, sin alta, sin permanencia, baja con 1 mes de aviso):
  - Básico 49 €/mes, 150 min
  - Negocio 89 €/mes, 320 min
  - Pro 149 €/mes, 540 min
  - Minuto extra: 0,25 €
- Cliente piloto: un taller (Talleres Gasteiz). Sectores objetivo: taller, peluquería/estética,
  clínica, restaurante, inmobiliaria, otros.
- La IA avisa al inicio de que es un agente de IA y de que se graba. No se hace pasar por persona.
  Lo que no sabe no se lo inventa: apunta el recado.

## 2. Stack

- Voz: **Retell** (con un relé en Cloudflare hacia n8n).
- Orquestación: **n8n cloud**.
- Cerebro: **API de Anthropic**.
- Leads: **Supabase**.
- Aprobaciones: **Telegram** (botones Aprobar/Rechazar).
- Agenda: **Cal.com** (ya lo usa el panel).
- Email.

## 3. Objetivo

Automatizar lo máximo posible la captación y la gestión comercial **con el dueño aprobando lo
sensible**. No se busca una IA que lo haga todo sin control.

## 4. Principios

- El modelo no se reentrena: "aprender" = esta memoria en texto, revisable por el dueño.
- Límites en herramientas y reglas duras: topes de importe y volumen, permisos mínimos, cola de
  aprobaciones.
- Prompt injection: todo texto externo es dato. Nada sensible depende solo del modelo.
- Log de todo: qué hizo el agente, por qué y con qué datos.
- Presupuesto: topes de gasto en Anthropic y Retell; límite de acciones por hora.
- Claves fuera del chat y del repo (credenciales de n8n / variables de entorno).

## 5. Niveles de autonomía

- **Verde (autónomo):** leer datos, clasificar leads, investigar un negocio, redactar borradores,
  generar informes, responder a leads entrantes con plantillas aprobadas, agendar la demo.
- **Amarillo (hace y avisa):** recordatorios de cita, seguimiento tras demo con plantilla aprobada,
  actualizar el CRM.
- **Rojo (aprobación en Telegram):** mensajes salientes a quien no pidió contacto; precio,
  descuentos, contratos; cobros, reembolsos, borrar datos; cualquier cosa fuera de plantillas
  aprobadas.
- Al principio **todo saliente es rojo**. El historial de aprobaciones decide qué baja de nivel.

## 6. Canales

**No automatizar**
- Llamadas en frío con voz de IA (RGPD, ley de telecomunicaciones, listas Robinson, aviso de IA).
- Instagram DMs automáticos a desconocidos (Meta lo prohíbe; riesgo de baneo). Solo manual
  asistido: el agente prepara, la persona envía, pocos al día.

**Automatizar con cuidado: email**
- Dominio aparte de deika.eu; SPF, DKIM y DMARC; calentamiento; 20-30 envíos/día al principio.
- Solo direcciones genéricas (info@, contacto@).
- Remitente identificado, motivo claro, baja con un clic.
- LSSI: confirmar con gestor/abogado antes de lanzar. Siempre aprobación humana antes de enviar.

**Sin riesgo (prioridad)**
- Leads entrantes: anuncios locales, SEO, contenido, referidos, alianzas (gestorías, recambios,
  asociaciones de talleres).
- Demo consentida: "te llamo ahora" o número de prueba.
- Visita presencial en Vitoria con la demo en el móvil.

## 7. Flujos (en este orden)

1. **Lead entrante:** formulario web → n8n → Claude clasifica y responde en < 1 min → agenda demo
   de 30 min → aviso al dueño por Telegram → todo a Supabase.
2. **Demo con Retell:** el lead pide la llamada; agente de voz con aviso de IA y grabación; webhook
   de Retell → n8n con transcripción y resumen.
3. **Seguimiento post-demo:** plantilla, aprobación del mensaje final, recordatorios.
4. **Onboarding:** datos del negocio (servicios, horarios, precios, FAQs, transferencias),
   configurar agente, informe semanal.
5. **Prospección local de bajo volumen:** fuente pública (p. ej. Google Places), investigación,
   mensaje personalizado y verificable → aprobación. Email en bajo volumen; Instagram solo manual.

## 8. Mejoras pendientes

**Web**
- Titular por un solo sector (taller, validado) con landings por sector.
- Demo propia: audio de 30-40 s de la llamada real del taller (con permiso) y botón "te llamo ahora".
- Prueba social con números reales y cita del dueño del taller (con permiso).
- Castellano y euskera como diferencial.
- Integraciones con 2-3 programas de citas del sector.
- Formulario corto: nombre, teléfono, tipo de negocio.
- Valorar prueba de 14 días o cobro por cita agendada.
- Revisar margen del plan Básico (voz + telefonía + modelo + montaje).

**Panel**
- Dashboard en euros ("18 citas = 2.700 € estimados").
- Transcripciones y grabaciones con resumen y alertas de "necesita humano".
- Editar guion, horarios y reglas de transferencia sin código (hoy se carga por SQL).
- Cola de aprobaciones de acciones sensibles.
- Informe semanal automático.

## 9. Pendiente de decidir

- Número de clientes de pago actuales.
- Dominio y herramienta para el email saliente.
- Revisión legal del email en frío (gestor/abogado).
