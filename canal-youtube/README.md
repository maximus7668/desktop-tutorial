# Agente del canal de YouTube

Un agente de IA que produce un canal de YouTube **sin cara, en español**, sobre **historia
económica y de empresas del mundo hispano**. Busca temas con demanda, investiga y escribe guiones
con fuentes, pone la voz, monta el vídeo largo y los Shorts (archivo histórico con movimiento de
cámara, mapas y gráficos animados, rótulos y subtítulos), hace tres miniaturas, prepara título,
descripción con capítulos y etiquetas, pasa un control de calidad, lo sube **en privado** y,
cuando tú lo apruebas, lo programa. Después lee las métricas y apunta lo que aprende.

- **Cerebro**: Claude Code con la skill `canal-youtube` (`.claude/skills/canal-youtube/`).
- **Manos**: este programa en Python (`python -m canal …`).
- **Memoria**: `memoria/` (decisiones, ideas, lecciones, métricas, gastos y registro de acciones).
- **Estrategia**: [ESTRATEGIA.md](ESTRATEGIA.md) (nicho, formato, ritmo, cifras y reglas).

## Cómo se usa

Abre Claude Code en este repositorio y pídelo con tus palabras:

| Dices | El agente hace |
|---|---|
| «Propón ideas para el canal» | Busca vídeos atípicos del nicho y te trae 5 ideas con evidencia de demanda |
| «Haz el vídeo de Mercadona» | Investiga, escribe el guion, revisa las imágenes, produce y te envía el largo, los Shorts y las miniaturas |
| «Súbelo» | Lo sube en privado con su miniatura y subtítulos |
| «Prográmalo para el jueves a las 19:00» | Lo deja programado (solo con tu ok expreso) |
| «¿Cómo van los vídeos?» | Lee métricas, te dice dónde se va la gente y apunta lecciones |

Nada se publica sin tu aprobación, vídeo a vídeo. El gasto se para solo al llegar al tope mensual.

## Puesta en marcha (una vez)

### 1. El canal
1. Crea el canal como **cuenta de marca** (así puedes dar acceso a otras personas sin compartir tu
   cuenta personal). Activa la verificación en dos pasos (la pide el Programa de Partners).
2. **Verifica el teléfono** en youtube.com/verify. Sin eso no se pueden poner miniaturas
   personalizadas ni subir vídeos de más de 15 minutos, y los nuestros duran 15–25.
3. Elige el nombre (propuestas en `ESTRATEGIA.md`) y apúntalo en `canal.yaml` → `canal.nombre`.

### 2. Claves (gratis salvo la voz)
Ponlas en `canal-youtube/.env` (copia `.env.example`; no se sube al repo) o, en Claude Code en la
nube, como **secretos del entorno**. Nunca en el chat.

| Clave | Para qué | Dónde |
|---|---|---|
| `ELEVENLABS_API_KEY` | Voz final (la mejor). Pon también `voz.elevenlabs.voice_id` y `voz.proveedor: elevenlabs` en `canal.yaml` | elevenlabs.io → Profile → API keys. Plan Creator (22 $/mes) para uso comercial |
| `AZURE_SPEECH_KEY` | Voz alternativa: 500.000 caracteres al mes gratis (≈25 vídeos) | portal.azure.com → recurso «Speech» (región `westeurope`) |
| `PEXELS_API_KEY` | Vídeos e imágenes de stock | pexels.com/api |
| `PIXABAY_API_KEY` | Más stock | pixabay.com/api/docs |
| `YOUTUBE_API_KEY` | Buscar temas con demanda (`tendencias`) | Google Cloud → APIs → YouTube Data API v3 → Credenciales → Clave de API |

Wikimedia Commons y los mapas de Natural Earth no necesitan clave. Pon una web o un email de
contacto en `canal.contacto_api` para que Wikimedia no te limite las descargas.

### 3. Conectar con tu canal (subir y leer métricas)
1. En console.cloud.google.com, crea un proyecto y activa **YouTube Data API v3**, **YouTube
   Analytics API** y **YouTube Reporting API**.
2. Pantalla de consentimiento OAuth: tipo «Externo», añade tu cuenta y **publícala («En
   producción»)**. En modo «Prueba» la autorización caduca a los 7 días. Para uso propio no hace
   falta que Google la verifique: aceptas el aviso de «app no verificada».
3. Credenciales → ID de cliente OAuth → **Aplicación de escritorio** → descarga el JSON como
   `canal-youtube/secretos/client_secret.json`.
4. En **tu ordenador** (abre el navegador): `python -m canal autorizar`. Elige la cuenta del canal.
   Queda `secretos/token-youtube.json`. Para la nube, copia su contenido en el secreto `YT_TOKEN_JSON`.
5. La primera subida, compruébala en Studio. Si sale «Privado (bloqueado)», el proyecto necesita la
   auditoría de la API (formulario: support.google.com/youtube/contact/yt_api_form). Mientras tanto,
   `python -m canal paquete <id>` te deja todo listo para subirlo a mano en 2 minutos.

### 4. Música (opcional)
Deja pistas de la **Biblioteca de audio de YouTube** en `musica/` (no reciben reclamaciones de
Content ID). Si no hay, el agente genera una base ambiental original para cada vídeo.

### 5. Instalar (si usas tu ordenador)
Python 3.11+ y ffmpeg. Después: `bash preparar.sh`, que instala las dependencias y ejecuta
`python -m canal comprobar` para decirte qué falta.

## Órdenes

| Orden | Qué hace |
|---|---|
| `python -m canal comprobar` | Herramientas, claves y gasto del mes |
| `python -m canal tendencias "historia de empresas" --dias 90 --region MX` | Vídeos atípicos del tema → `memoria/tendencias/` |
| `python -m canal validar guiones/X.json` | Revisión editorial del guion (errores bloquean) |
| `python -m canal visuales guiones/X.json` | Hoja con la imagen de cada plano, para revisarla antes de montar |
| `python -m canal producir guiones/X.json [--voz piper] [--solo largo\|shorts]` | Voz, montaje, Shorts, miniaturas, metadatos y control de calidad → `salida/<id>/` |
| `python -m canal subir <id> --confirmo` | Sube en privado (🟡) |
| `python -m canal paquete <id>` | Instrucciones para subirlo a mano en Studio |
| `python -m canal programar <youtube_id> --cuando 2026-10-23T19:00 --confirmo` | Programa la publicación (🔴) |
| `python -m canal metricas [--crear-informe]` | Métricas, CTR y caídas de retención → `memoria/metricas.md` |
| `python -m canal vista <id>` | Copias ligeras de los vídeos para revisarlos en el móvil |
| `python -m canal marca` | Avatar (800×800) y banner (2560×1440) del canal → `salida/marca/` |
| `python -m canal gastos` | Gasto del mes |

## Qué sale de cada vídeo (`salida/<id>/`)

`largo.mp4` (1920×1080) · `short-N.mp4` (1080×1920) · `miniatura-1..3.jpg` · `miniaturas-en-movil.jpg`
· `metadatos.json` · `descripcion.txt` · `largo.srt` · `calidad.md` · `revision-*.jpg` (hoja de
fotogramas) · `linea-largo.json` (qué frase suena en cada segundo, para cruzarlo con la retención).

## Límites que pone el propio código

- **Tope de gasto** mensual (`presupuesto.mensual_eur`): la voz y las imágenes IA se paran al llegar.
  La voz va a caché, así que volver a montar un vídeo no vuelve a gastar.
- **Subir** exige `--confirmo` (o `autonomia.subir_privado: true`) y el control de calidad en verde.
  Siempre en privado.
- **Programar** exige `--confirmo`. No hay ninguna orden que publique directamente.
- Cada acción queda en `memoria/registro.jsonl`.

## Lo que hay que hacer en Studio (la API no lo permite)

«Probar y comparar» con las otras miniaturas y títulos, la pantalla final, el «vídeo relacionado» de
cada Short y la respuesta a los comentarios.

## Carpetas

```
canal/        el programa (voz, visuales, montaje, subtítulos, miniaturas, calidad, YouTube)
guiones/      un JSON por vídeo (formato en plantillas/guion.ejemplo.json)
investigacion/ datos y fuentes de cada vídeo, con su grado de certeza
memoria/      decisiones, ideas, lecciones, métricas, gastos, registro
fuentes/      tipografías libres (OFL) para rótulos y subtítulos
musica/       tus pistas de la Biblioteca de audio (opcional)
salida/       vídeos producidos (no se suben al repo)
cache/        voz, imágenes, clips y mapas ya descargados (no se suben al repo)
secretos/     credenciales de YouTube (no se suben al repo)
tests/        pruebas (python -m pytest)
```
