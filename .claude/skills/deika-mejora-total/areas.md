# Áreas y comprobaciones

Para cada área: qué mirar, con qué datos y qué suele salir. Añade comprobaciones nuevas cuando aparezcan.

## 1. Servicio a clientes (lo primero)
- ¿Contestan todas las recepcionistas? Llamadas fallidas o «no atendidas» del último mes, motivos de corte de
  Retell, saldo de Retell y Twilio, revisión diaria funcionando.
- Calidad: lee 10–20 transcripciones recientes por negocio (sin copiar datos personales al informe). Busca
  citas mal dadas, datos inventados, clientes que piden persona y no se les pasa, llamadas largas sin cita.
- Prompts de cada agente: aviso de IA y grabación al empezar, no inventa, transferencia, urgencias.
- Agenda: reservas que fallan en Cal.com, horarios y días cerrados al día.

## 2. Captación
- Web deika.eu: mensaje, prueba social, demo (audio, «Llámala tú»), formulario, velocidad, móvil, SEO básico
  (título, descripción, datos estructurados, sitemap), accesibilidad. Compara con `deika-competencia`.
- Leads: de dónde vienen, cuánto tardan en recibir respuesta, cuántos llegan a demo y a cliente.
- Prospección: cartera por estado, criterios de encaje, calidad de las fichas, ruta, demo de visita.
- Canales legales sin explotar: anuncios con formulario, cartas, recomendaciones de clientes, alianzas.

## 3. Conversión y seguimiento
- Demo saliente y entrante: guion, cierre, qué pasa después de la demo, recordatorios.
- Plantillas aprobadas: ¿se usan?, ¿faltan casos?
- Alta (onboarding): pasos pendientes por negocio, tiempo hasta estar funcionando.

## 4. Retención
- Panel del cliente: qué ve, qué le falta (euros recuperados, llamadas, avisos), informe semanal.
- Señales de baja: negocios con pocas llamadas, quejas, cambios de plan.

## 5. Producto y panel
- Fallos y deudas en el código (usa la skill `code-review` sobre los cambios recientes y una revisión de
  seguridad con `security-review`).
- Funciones que la competencia tiene y DEIKA no, por impacto (confirmaciones, recordatorios, integraciones).

## 6. Fiabilidad y costes
- Tareas programadas: ¿se ejecutan?, ¿fallan en silencio?
- Coste por minuto real frente a precio de cada plan; topes de gasto puestos en cada proveedor.
- Copias de seguridad de D1 y de los flujos de n8n.

## 7. Legal y seguridad
- Privacidad y aviso legal al día con lo que realmente se hace; aviso de IA; prefijo 400; LSSI.
- Claves: rotadas, sin claves en el repo (`git grep` de patrones de claves), permisos mínimos.
- Accesos al panel y rutas protegidas.

## 8. Marca y contenido
- Coherencia de mensaje entre web, agentes de voz y redes (`deika-redes`).
- Ideas de contenido a partir de llamadas reales anonimizadas (con permiso del cliente).
