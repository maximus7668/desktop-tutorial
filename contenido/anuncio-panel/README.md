# Anuncio con voz del panel DEIKA (Reel 9:16, ~27 s)

Estado (20/10/2026): **terminado, pendiente de aprobación del dueño**. No publicado ni programado.

- Vídeo: `deika-anuncio-panel.mp4` (25 s, 1080×1920, con voz y música, −14,5 LUFS, pico −1,3 dB).
- Locución: ElevenLabs eleven_v4, voz «Cristina - Premium Spanish Advertising Voice» (1CeqBeXMOqCleeQjfYfO),
  una sola toma con `[confident]` y `[warmly]` en el cierre (`audio/locucion-toma1.mp3` y sus tiempos por letra).
  Comprobada con el transcriptor de ElevenLabs: dice el guion palabra por palabra. Montada con 0,5 s de entrada y
  0,2 s más en cada pausa entre frases (`public/voz.mp3`).
- Música: ElevenLabs Music con plan de secciones (`audio/musica-plan.json`), instrumental (el transcriptor no
  encuentra palabras). Se quitan los primeros 0,8 s, la subida final se baja 4,8 dB para que el volumen sea
  constante, y va unos 13 dB por debajo de la voz. Mezcla final: `public/mezcla.wav`.
- Créditos de ElevenLabs gastados en esta pieza: 1.162 (voz, 3 tomas de música y comprobaciones).
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

## Volver a renderizar

`npm ci` y `bash render.sh out/deika-anuncio-panel.mp4 mezcla.wav`. Si cambia la locución, las duraciones de
`src/guion.ts` se recalculan con los tiempos de cada frase (cada escena empieza en mitad de la pausa anterior).
