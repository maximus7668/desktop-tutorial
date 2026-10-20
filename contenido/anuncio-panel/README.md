# Anuncio con voz del panel DEIKA (Reel 9:16, ~27 s)

Estado (20/10/2026): **borrador sin voz**, pendiente de aprobar el guion. Falta la locución (ElevenLabs,
voz Cristina, eleven_v4) y, si se quiere, música. En esta sesión no había clave de ElevenLabs: se añade como
variable `ELEVENLABS_API_KEY` en los ajustes del entorno y la recoge una sesión nueva.

- Borrador: `deika-anuncio-panel-borrador.mp4` (1080×1920, sin sonido).
- Panel con **datos de ejemplo** de un negocio inventado (Peluquería Marta); lo dice una etiqueta arriba.
- Pantallas reales del panel (`Deika-panel`, compilado y servido en local) con la API simulada:
  `capturar.mjs` (necesita `npx vite preview --port 4173` en Deika-panel y `LANG=es_ES.UTF-8` para la hora en 24 h).

## Guion (voz y texto en pantalla)

| Escena | Locución | Pantalla |
|---|---|---|
| intro | ¿Quién te ha llamado mientras trabajabas? | Móvil bloqueado llenándose de avisos de DEIKA |
| panel | Con el panel de DEIKA, lo ves todo desde el móvil. | Agenda: hoy 6 citas, 9 llamadas |
| llamadas | Cada llamada: quién era, qué quería, y un resumen. | Llamadas → toca Laura Pérez → resumen y cita |
| escuchar | Y si quieres, la escuchas entera. | Reproductor y conversación |
| agenda | Las citas que da van directas a tu agenda. | Cita «Reservada por DEIKA por teléfono» |
| urgente | Si algo es urgente, te avisa al momento. | Aviso «Llamada urgente» y llamada en rojo |
| recepcion | ¿Cambias el horario? Lo tocas aquí, y ella ya lo sabe. | Tu recepcionista → Editar → horario |
| cierre | DEIKA. Tu teléfono, siempre atendido. | Logo, lema y deika.eu |

## Terminarlo con la voz

1. Generar la locución (una toma por frase o todo seguido) y dejarla en `public/voz.mp3`.
2. Ajustar `dur` de cada escena en `src/guion.ts` a lo que dura cada frase (+0,3 s de aire).
3. `npm ci` y `bash render.sh out/deika-anuncio-panel.mp4 voz.mp3 [musica.mp3]`.
