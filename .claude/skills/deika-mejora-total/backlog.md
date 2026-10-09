# Mejora total: estado y backlog

Informe publicado: (todavía no hay)
Última auditoría completa: 09/10/2026 (sin acceso a producción: en esta sesión no hay credenciales de Cloudflare ni de Retell)

## Estado actual
09/10/2026:
- Panel: 111 tests en verde y tipos sin errores. deika.eu responde 200 en 0,5 s y pesa 80 KB. El panel responde 200.
- Seguridad: todas las rutas /api exigen sesión salvo 5 públicas; /api/admin solo para administradores. Los 8 hooks de n8n comprueban INGEST_TOKEN y los de Retell, la firma. No hay claves en ninguno de los dos repos (git grep).
- Web: tiene title, description, canonical y Open Graph. Faltan robots.txt, sitemap.xml, página 404 (cualquier ruta devuelve la portada con 200), datos estructurados y cabeceras de seguridad.
- Panel del cliente: ya muestra llamadas, citas y euros del mes (con el precio medio), avisos y minutos restantes. El informe semanal está hecho pero apagado (decisión del dueño).
- No hay CI: los tests solo se ejecutan a mano.
- No hay un procedimiento escrito para recuperar D1 ni los flujos de n8n (los flujos sí están exportados en automatizacion/n8n).
- Retell sin saldo: no se atiende ninguna llamada (ya está en «Pendiente del dueño»).

## En curso
(nada)

## Por hacer

## Hecho
(Formato: `M-001 · fecha · qué se hizo · commit · cómo se comprobó`.)
- M-001 · 09/10 · Web: datos estructurados (empresa, servicio con los 3 planes y FAQ), robots.txt, sitemap.xml, 404.html y _headers (seguridad y caché) · panel c199b6c · test/web.test.ts comprueba que precios y FAQ coinciden con la página y con planes.ts; captura de la 404 en móvil. **Falta desplegar la web** (no hay clave de Cloudflare en esta sesión).
- M-002 · 09/10 · CI en GitHub Actions (tipos, tests y build en cada push, sin secretos) · panel 95d0a87 · primeras ejecuciones en verde.
- M-003 · 09/10 · docs/recuperacion.md: D1 Time Travel (30 días), rollback del Worker, secretos y de dónde sale cada uno, web, n8n y Retell · panel cde2a9a · comandos comprobados en la documentación de Cloudflare.
- M-004 · 09/10 · Web: contraste AA del texto gris y región <main> · panel a6e2166 · axe-core sin fallos en móvil, ordenador y modo oscuro.
- M-005 · 09/10 · Hoja A5 para dejar en las visitas (docs/hoja-visita.html y .pdf, QR a deika.eu) · panel 9a4f042 · PDF revisado en captura.
- M-006 · 09/10 · Guion de visita con objeciones y lo que no se promete (docs/guion-visita.md) · panel 13432d6.
- M-007 · 09/10 · Prospección: resultado de la visita (interesado con fecha, permiso para llamar y nota; ya es cliente; al final no) y aviso a Telegram a las 9 el día que toca · panel d86da1e · tests + recorrido completo en local con Playwright. **Antes de desplegar: aplicar la migración 0019 en remoto.**
- M-008 · 09/10 · Revisión de código (subagente) y arreglos: tope diario real de búsquedas en Google, números de clientes tapados en errores de SMS/WhatsApp, sin SMS doble si WhatsApp tarda, aviso si fallan las claves de Twilio o ElevenLabs, cadenas con apóstrofo · panel 23bc43f · 120 tests. Falso positivo descartado: Retell create-web-call sí es v3 (comprobado en docs.retellai.com).

## Propuestas rojas (esperan al dueño)
- R-001 · Comparativa honesta con heydiga en la web (más minutos por euro, montaje incluido, local de Vitoria). Riesgo: nombrar a un competidor exige datos exactos y fechados (publicidad comparativa, Ley 3/1991 art. 10). Alternativa segura: «qué mirar al elegir una recepcionista con IA» sin nombres.
- R-002 · Atender en inglés y francés en las recepcionistas de los clientes (turistas, Vitoria Green Capital). Cambia agentes de clientes que pagan → solo con su permiso, uno a uno.
- R-003 · Escuchar el webhook de estados de WhatsApp para mandar el SMS cuando el número no tenga WhatsApp. Se hace cuando WhatsApp esté activo.

## Pendiente del dueño
- Dar acceso a Cloudflare en la sesión (variables CLOUDFLARE_API_TOKEN y CLOUDFLARE_ACCOUNT_ID en el entorno) para desplegar la web y el panel.
- Guardar CLAVE_CIFRADO en un gestor de contraseñas: si se pierde, hay que pedir de nuevo la clave de Cal.com a cada negocio.
- Recargar el saldo de Retell (09/10/2026: sin saldo, no se atienden llamadas).
- Rotar todas las claves que pasaron por el chat.
- Gestor: prefijo 400 (desde el 17/10/2026) y compra del número 400.
- Registrar «DEIKA» como remitente de SMS en Twilio.
- Cuenta de WhatsApp Business y aprobar la plantilla `confirmacion_cita`.
