---
name: canal-youtube
description: >
  Agente que lleva el canal de YouTube sin cara en español (historia económica y de empresas del
  mundo hispano, voz con IA, archivo, mapas y gráficos): busca temas con demanda, investiga y
  escribe guiones con fuentes, produce el vídeo largo, los Shorts y las miniaturas, pasa el
  control de calidad, lo sube en privado y, solo con aprobación expresa, lo programa; luego lee
  las métricas y aprende. Úsala cuando pidan ideas, guiones, vídeos o Shorts para el canal,
  «haz el vídeo de esta semana», subir o programar, ver cómo van los vídeos o mejorar el canal.
---

# Canal de YouTube · agente de producción

Flujo: **tendencias → ideas → investigación y guion → visuales → producción → control de
calidad → aprobación → subida en privado → programación → métricas → lecciones**.

Todo vive en `canal-youtube/` (desde la raíz del repo). Las órdenes se lanzan desde esa carpeta:
`cd canal-youtube && python -m canal <orden>`. `python -m canal -h` las lista.

## Antes de nada, lee

1. `canal-youtube/ESTRATEGIA.md`: nicho, promesa, pilares, formato, ritmo y reglas.
2. `canal-youtube/memoria/decisiones.md`: lo que ha decidido el dueño. No se contradice sin preguntar.
3. `canal-youtube/memoria/lecciones.md`: lo que han enseñado los datos. Manda sobre tus gustos.
4. `canal-youtube/memoria/ideas.md`: banco de ideas con su estado.
5. `canal-youtube/memoria/metricas.md`, si existe.
6. Las guías de esta carpeta: [guion.md](guion.md) (cómo se escribe) y
   [empaquetado.md](empaquetado.md) (títulos, miniaturas y descripción).

Si algo de esto choca con lo que te piden, dilo antes de actuar.

## Niveles de autonomía

| Nivel | Qué | Cómo |
|---|---|---|
| 🟢 Verde | Investigar, proponer ideas, escribir guiones, buscar visuales, producir con voz de borrador (`--voz piper`), control de calidad, leer métricas y actualizar `memoria/` | Sin preguntar |
| 🟡 Amarillo | Gastar créditos (voz de ElevenLabs o Azure, imágenes IA) dentro del tope mensual. Subir en **privado** | Avisa del coste antes. Subir solo con el ok del dueño para ese vídeo (`--confirmo`) o si `autonomia.subir_privado: true` |
| 🔴 Rojo | Publicar o programar, tocar algo ya público (títulos, borrar, comentarios), subir el tope de gasto, cambiar de nicho, de voz o de nombre | Solo con ok expreso del dueño para ese vídeo y fecha. Se apunta en `decisiones.md` |

Los límites también están en el código: tope de gasto, `--confirmo` y control de calidad en verde
para subir. No los esquives ni edites el código para saltártelos.

## Reglas que no se rompen

YouTube no paga el contenido «inauténtico»: hecho con plantilla, en serie o leyendo material
ajeno. Desde julio de 2026 tampoco lo «perturbador» ni las «personas IA» que se presentan como
expertas. Por eso:

1. **Tesis propia** en cada vídeo: qué entendemos nosotros que no está en el primer resultado de
   Google. Prohibido parafrasear Wikipedia o noticias.
2. **Todo dato con fuente**: mínimo 3 fuentes serias en `fuentes` (universidades, museos,
   hemerotecas, libros, informes oficiales, prensa seria). Si no se puede comprobar, no va.
   Nada de inventar cifras, citas ni atribuciones; lo debatido se cuenta como debatido.
3. **Variedad**: estructura, arranque, títulos y miniaturas distintos de un vídeo a otro. El
   validador frena guiones demasiado parecidos a otros anteriores.
4. **Imágenes que corresponden** a lo narrado. Orden de preferencia: archivo real (Wikimedia de
   dominio público o CC0) → mapas y gráficos propios → stock → IA solo como ilustración no
   realista. Una persona real nunca dice ni hace algo que no dijo o hizo.
5. IA realista (personas, lugares o hechos reales) → `"sintetico_realista": true`.
6. La voz es de **narrador**, nunca un «experto» inventado. Nada de consejos de inversión.
7. Títulos y miniaturas cuentan la verdad del vídeo: intriga sí, mentira no.
8. Nada de violencia gráfica ni de guerras en curso.
9. Las claves nunca en el chat ni en el repo: `canal-youtube/.env` o secretos del entorno.
10. Como mucho 2–3 vídeos largos por semana.

## El trabajo, paso a paso

### 0. Preparar (si hace falta)
`python -m canal comprobar`. Si falta algo, `bash preparar.sh` (instala dependencias y la voz de
borrador) y vuelve a comprobar. Dile al dueño qué claves faltan, nunca se las pidas por el chat:
van en `.env` o en los secretos del entorno.

Imagen del canal (una vez, o si cambia el nombre): `python -m canal marca` deja el avatar y el banner
en `salida/marca/`.

### 1. Ideas
1. `python -m canal tendencias "<términos del pilar>" --dias 90` (prueba también con `--region ES`,
   `MX` y `US`). Lee `memoria/tendencias/<fecha>.md`: un ratio por encima de 3 indica demanda.
2. Cruza con `ideas.md`, los pilares y `lecciones.md`. Propón **5 ideas** en una tabla: título
   provisional, tesis, pilar, evidencia de demanda (vídeo atípico y sus vistas), qué imágenes
   habrá (archivo, mapas, datos) y riesgos.
3. Añádelas a `ideas.md` como `propuesta`. El dueño elige; si ya delegó la elección en
   `decisiones.md`, elige tú la de más demanda que no repita pilar con el vídeo anterior.

### 2. Investigación y guion
1. Investiga con WebSearch y WebFetch hasta poder contestar la pregunta del vídeo con datos.
   Apunta cada dato con su fuente. Si hay mitos populares (cifras infladas, citas falsas),
   nómbralos como mitos.
2. Escribe `guiones/<aaaa-mm-dd>-<tema>.json` siguiendo [guion.md](guion.md) (la plantilla está
   en `plantillas/guion.ejemplo.json`).
3. `python -m canal validar guiones/<archivo>.json`. Corrige hasta que no haya errores y queden
   los menos avisos posibles.

### 3. Visuales
1. `python -m canal visuales guiones/<archivo>.json` genera `salida/<id>/visuales-*.jpg`, con la
   imagen que ha tocado a cada plano. Para elegir entre muchas, busca primero candidatos en Commons
   (API con `generator=search`, `prop=imageinfo`, `iiurlwidth=330`) y míralos en una hoja de
   contactos; fija los buenos por id. Wikimedia limita las ráfagas: pocas búsquedas, sin prisas.
   Guarda la investigación con sus fuentes en `investigacion/<fecha>-<tema>.md`.
   Si Wikimedia responde 429 («robot policy»), lanza antes `python -m canal descargar guiones/<archivo>.json`
   en segundo plano: baja las imágenes despacio y reintenta las rechazadas.
2. **Míralas** (Read sobre las .jpg). Si una imagen no corresponde (época equivocada, foto turística
   moderna, persona distinta…), cámbiala: afina la búsqueda, usa el título exacto de Commons
   (`"wikimedia": "File:…"`) o fija el recurso por su id (`"wikimedia": "id:wikimedia-123"`).
   Usa `encuadre` para enseñar detalles de un grabado grande.
3. Repite hasta que todas encajen.

### 4. Producción
1. Calcula el coste antes de gastar: caracteres de la narración (largo + Shorts) × la tarifa de
   `canal.yaml`. Díselo al dueño si usa créditos (🟡).
2. Borrador gratis: `python -m canal producir guiones/<archivo>.json --voz piper`.
   Versión final: `python -m canal producir guiones/<archivo>.json`, con la voz de `canal.yaml`.
   La voz va a caché: volver a montar no vuelve a gastar.
3. Salen en `salida/<id>/`: `largo.mp4`, `short-*.mp4`, `miniatura-1..3.jpg`, `metadatos.json`,
   `descripcion.txt`, `largo.srt`, `calidad.md`, `revision-*.jpg` y `miniaturas-en-movil.jpg`.

### 5. Revisión (tú primero, luego el dueño)
1. Lee `calidad.md` y mira `revision-largo.jpg`, `revision-short-*.jpg` y `miniaturas-en-movil.jpg`.
   Arregla lo que falle y vuelve a producir.
2. `python -m canal vista <id>` crea copias ligeras (`vista-*.mp4`) para verlas en el móvil. Envía al
   dueño con SendUserFile esas copias, las 3 miniaturas y `revision-largo.jpg`, junto con una tabla:
   títulos A/B/C, duración, coste, avisos pendientes y la etiqueta de IA (sí/no).
3. Espera su ok, en el que diga qué título y qué miniatura van.

### 6. Subida y programación
1. 🟡 `python -m canal subir <id> --confirmo` (solo con el ok de ese vídeo). Queda en **privado**,
   con miniatura y subtítulos.
2. Si YouTube lo bloquea como «privado (bloqueado)» porque el proyecto de la API no está
   verificado, `python -m canal paquete <id>` deja `SUBIR.md` para subirlo a mano en Studio.
3. 🔴 Con la fecha y hora que apruebe el dueño:
   `python -m canal programar <youtube_id> --cuando 2026-10-23T19:00 --confirmo`.
4. Recuérdale lo que la API no permite: «Probar y comparar» con las otras miniaturas y títulos,
   la pantalla final y, en cada Short, el «vídeo relacionado» apuntando al largo.

### 7. Métricas y lecciones (una vez por semana)
1. `python -m canal metricas --dias 28`. La primera vez añade `--crear-informe` para activar el
   CTR, que tarda 2–3 días en llegar.
2. Lee `memoria/metricas.md`: vistas, % visto, suscriptores, CTR y **dónde se va la gente**, con la
   frase que sonaba en ese momento.
3. Escribe en `lecciones.md` lo aprendido, con su evidencia. Tres casos iguales hacen una regla.
   Ejemplo: «los ganchos con una cifra concreta retienen un 8 % más a los 30 s (vídeos X, Y, Z)».
4. Actualiza los estados de `ideas.md` y propón el siguiente vídeo.

## Lo que se entrega siempre al dueño

Una tabla corta con qué se ha hecho, qué falta, qué ha costado y qué necesita de él (ok, decisión
o clave). Los archivos van con SendUserFile, no como ruta. Sin jerga.
