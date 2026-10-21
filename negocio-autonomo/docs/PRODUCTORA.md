# Productora de TikTok con IA: decisión de herramientas y arquitectura

Investigado el 2026-10-21. Cada precio lleva su fuente. Cuando las fuentes no coinciden, se indica y el dato queda **por verificar** antes de pagar.

## 1. Comparativa por tarea

### Orquestación
| Opción | Coste | Ventajas | Pegas | Decisión |
|---|---|---|---|---|
| **n8n autoalojado (npm, en este PC)** | 0 € | Sin suscripción; credenciales cifradas en local; reintentos y workflow de errores | El PC tiene que estar encendido y conectado. Requiere Node 20.19–24 ([docs n8n](https://docs.n8n.io/deploy/host-n8n/install-options/install-with-npm)); tu Node 26 no vale, por eso se usa un Node 24 portátil en `D:\IA\n8n` | **Elegido** |
| n8n Cloud | De pago | Siempre encendido | Suscripción obligatoria | No |

### Noticias e investigación
| Opción | Coste | Calidad para contrastar | Decisión |
|---|---|---|---|
| RSS de medios fiables (EFE, Europa Press, Xataka, The Verge, Ars Technica, blogs oficiales de OpenAI, Google, Anthropic, Meta…) | 0 € | Fuente primaria, con fecha y URL | **Elegido** como entrada |
| Gemini 2.5 Flash, nivel gratuito, con Google Search | 0 € (límites diarios por modelo; [facturación](https://ai.google.dev/gemini-api/docs/billing)) | Bueno para agrupar, quitar duplicados y puntuar. Google puede usar las peticiones gratuitas | **Elegido** para el filtrado |
| Claude (API de Anthropic) con búsqueda web | ≈ 0,01 $ por búsqueda más tokens | El mejor para contrastar afirmaciones y escribir en español de España; ya está integrado y con control de gasto | **Elegido** para contraste y guion |
| Perplexity Sonar | 1 $/M tokens más 5–12 $ por 1.000 peticiones ([guía 2026](https://www.cloudzero.com/blog/perplexity-api-pricing/)); Chat Completions se retira el 27-09-2026 | Bueno, pero duplica lo que ya hace Claude | Descartado |

### Presentador virtual (parte inferior)
| Opción | Coste para 30 vídeos de unos 70 s | Realismo y control | Decisión |
|---|---|---|---|
| **InfiniteTalk en local** (ComfyUI con la RTX 4070 Ti SUPER, ya instalado) | 0 € más electricidad | Personaje propio y siempre igual, sin marca de agua. Calidad **pendiente de la prueba que se está generando** | **Elegido** si pasa la prueba |
| HeyGen API (Avatar IV) | Por verificar: las fuentes dan 6 o 31 créditos/min; sin créditos API gratis desde 02-2026 ([arcade](https://www.arcade.software/post/heygen-pricing)) | El más realista; API madura | **Plan B** de pago |
| Synthesia API | Unos 75 créditos/min según una fuente secundaria ([creatify](https://creatify.ai/blog/heygen-vs-synthesia-(2026)-pricing-avatars-and-which-one-fits-your-team)) | Más corporativo, menos natural en vídeo corto | Descartado |
| Runway, Veo y otros generadores de vídeo | De pago por segundo | Generan escenas, no un presentador hablando con sincronía labial | No se usan para el presentador |

### Imágenes y gráficos (parte superior)
**Regla:** nada de imágenes sintéticas que parezcan reales de un acontecimiento.

| Recurso | Licencia | Uso |
|---|---|---|
| Gráficos animados propios: titulares, cifras, líneas de tiempo y citas con su fuente (Pillow/FFmpeg, ya existe el motor) | Propios | Base de cada escena |
| Capturas de las webs oficiales del producto o anuncio, con su crédito | Cita (art. 32 LPI), breve y con fuente | Cuando la noticia es un producto |
| Pexels API (vídeo e imagen de archivo) | Licencia Pexels, gratis | Recursos genéricos, nunca como prueba de un hecho |
| Wikimedia Commons | CC, con atribución | Personas y lugares públicos |
| Flux local | Propio, etiquetado como IA | Solo ilustraciones claramente no fotográficas |

### Voz
| Opción | Coste | Calidad en español de España | Licencia | Decisión |
|---|---|---|---|---|
| **ElevenLabs** (eleven_v3; la documentación ya menciona v4) | Creator ≈ 22 $/mes; las fuentes no coinciden en los créditos ([eesel](https://eesel.ai/blog/elevenlabs-pricing)) | La más natural; da la marca de tiempo de cada carácter para los subtítulos | Comercial desde Starter | **Elegido** |
| Fish Audio s2.1-pro-free | 0 € hasta como pronto el 30-11-2026 ([blog](https://fish.audio/blog/s2-1-pro-free-api/)) | Muy buena | Puede haber restricciones comerciales | Respaldo gratuito |
| Piper (local) | 0 € | Correcta, pero robótica | CC0 | Último recurso |

### Publicación, web y analítica
| Necesidad | Herramienta | Limitación real |
|---|---|---|
| Publicar en TikTok | Content Posting API oficial ([docs](https://developers.tiktok.com/doc/content-posting-api-reference-direct-post)) | **Sin auditoría de TikTok, los vídeos solo pueden publicarse como privados.** Mientras no esté aprobada, se sube como borrador a tu bandeja de TikTok y tú pulsas «Publicar». Límite: 6 peticiones por minuto. |
| Página web | Sección `/noticias` en deika.eu (el panel actual, sin WordPress): datos estructurados `NewsArticle`, fuentes enlazadas y el vídeo incrustado | WordPress sería otro servidor más que mantener. Si lo prefieres, se conecta por su API REST. |
| Métricas | Display API: visualizaciones, me gusta, comentarios y compartidos | Retención, tiempo medio y porcentaje de vídeo completo: las fuentes se contradicen sobre si la Business API los da ([adverity](https://docs.adverity.com/reference/connectors/connector-tiktok-business.html) frente a [zernio](https://docs.zernio.com/analytics/get-tiktok-account-insights)). **Se probará con un vídeo real.** |
| Comentarios y mensajes | Business API de TikTok | Sin verificar para cuentas orgánicas en la UE. Fase 2: primero se prueba; las respuestas automáticas solo a preguntas frecuentes y todo lo delicado pasa a revisión humana. |

## 2. Recomendación y coste mensual (30 vídeos de unos 70 s)

| Concepto | Opción recomendada | Opción 100 % gratis |
|---|---|---|
| n8n, Cloudflare, dominio | 0 € (dominio ya pagado) | 0 € |
| Filtrado de noticias (Gemini, nivel gratuito) | 0 € | 0 € |
| Contraste y guion (Claude con búsqueda, ≈ 0,45 $ por vídeo) | ≈ 13 € | Gemini: 0 €, pero contrasta peor |
| Voz | ElevenLabs Creator ≈ 20 € | Fish Audio (gratis mientras dure), luego Piper |
| Presentador | InfiniteTalk local: 0 € | 0 € |
| Música (biblioteca CC0) y Pexels | 0 € | 0 € |
| Electricidad (PC encendido, unos 100 W más los renderizados) | ≈ 10–15 € | ≈ 10–15 € |
| **Total** | **≈ 45 €/mes** | **≈ 12 €/mes** (solo luz) |
| Si InfiniteTalk no da la calidad: HeyGen API | +30–90 €/mes (por verificar) | — |

## 3. Arquitectura

```
n8n (local, http://127.0.0.1:5678)                     Servicio local de producción (FastAPI, negocio-autonomo)
 WF-01 Diario 07:00 ──► WF-02 Noticias ──► WF-03 Guion ──► POST /prod/render ──► voz (ElevenLabs/Fish/Piper)
   │                     RSS + dedupe       Claude +          │                   presentador (ComfyUI InfiniteTalk)
   │                     Gemini puntúa      fuentes ≥2         │                   gráficos y subtítulos (FFmpeg)
   │                                                           ▼
   │                                       WF-04 Control de calidad (ffprobe, −14 LUFS, Whisper frente al guion,
   │                                       re-contraste de hechos, etiqueta de IA, manifiesto de derechos)
   │                                         ├─ falla → reintento (máx. 2) → borrador + aprobación en el panel
   │                                         └─ pasa  → WF-05 Publicar (TikTok y /noticias en deika.eu)
   ├──► WF-06 Métricas (diario) → tabla → WF-07 Aprendizajes (semanal) → reglas para el próximo guion
   ├──► WF-08 Copias (diario: ~/.n8n, BD y vídeos de 30 días)
   └──► WF-99 Errores: cualquier fallo → registro + alerta en el panel (y por Telegram si lo activas)
```

- **Reparto del trabajo.** n8n orquesta y el trabajo pesado lo hace el servicio en Python: el nodo «Execute Command» viene desactivado en n8n 2.x por seguridad.
- **Control del gasto.** Cada llamada de pago pasa por `guarded_complete` (presupuesto y límite diario). ElevenLabs tiene tope por plan.
- **Credenciales.** Las claves de API se guardan en el `.env` (fuera de git) o en el almacén cifrado de n8n. Nunca van dentro de los workflows exportados.
- **Almacenamiento.** `data/productora/AAAA-MM-DD/`, con `guion.json`, `fuentes.json`, `voz.wav`, `presentador.mp4`, `final.mp4`, `qc.json` y `derechos.json`.

## 4. Lo que solo puedes hacer tú

| Paso | Por qué |
|---|---|
| Aprobar el gasto (≈ 33 €/mes más luz) o elegir la opción gratis | El dinero lo decides tú |
| Clave de la API de Anthropic con límite de gasto | Cuenta y pago a tu nombre |
| ElevenLabs Creator: suscribirte y crear la clave | Pago |
| Crear la app en developers.tiktok.com (Login Kit, Content Posting API y Display API) y pedir la auditoría | Cuenta de desarrollador a tu nombre. La auditoría la revisa TikTok. |
| Primer inicio de sesión en TikTok para autorizar la app (OAuth) | Solo tú puedes dar ese permiso |
| Clave de Gemini en aistudio.google.com | Cuenta de Google |
| Decidir el tema del canal (propuesta: novedades de IA y tecnología) | Línea editorial |
