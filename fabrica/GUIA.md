# Guía: montar la fábrica en tu PC, paso a paso

Al terminar tendrás en tu ordenador un programa que, a partir de tu idea, encarga cada parte
del juego a una herramienta de IA (Claude para el diseño y la revisión, ComfyUI o Meshy para el
arte, Meshy para los modelos 3D, el esqueleto y las animaciones, Blender para limpiar los
modelos y ElevenLabs para voces, efectos y música), te enseña el resultado para que lo apruebes
y lo lleva a tu proyecto de Godot.

No hace falta montarlo todo de golpe. Ve por orden: con los pasos 1 a 3 ya puedes probar todo el
recorrido **gratis y sin claves** (con un agente que hace dibujos y sonidos de relleno). Luego
vas activando cada herramienta de verdad cuando la necesites.

Los pasos están pensados para **Windows 10 u 11**. En Mac o Linux es igual cambiando el doble
clic del paso 3 por la orden que se indica allí.

---

## 1. Instala Python (gratis, 5 minutos)

1. Entra en **python.org/downloads** y descarga la versión más reciente (vale la 3.11 o
   cualquiera más nueva).
2. Abre el instalador y, **antes de pulsar «Install Now»**, marca la casilla
   **«Add python.exe to PATH»** (abajo del todo). Si no la marcas, Windows no lo encontrará.
3. Para comprobarlo: pulsa la tecla Windows, escribe `cmd` y pulsa Intro. En la ventana negra
   escribe `python --version` y pulsa Intro. Tiene que salir algo como `Python 3.13.1`.

## 2. Descarga la fábrica

1. Entra en la página del repositorio en GitHub (`maximus7668/desktop-tutorial`).
2. Arriba a la izquierda, en el selector de ramas, elige **`claude/triple-a-game-dev-6p90dg`**
   (o `main` si ya la has unido).
3. Pulsa el botón verde **Code → Download ZIP**.
4. Descomprime el ZIP en una carpeta fácil, por ejemplo `C:\Fabrica`. Dentro verás una carpeta
   llamada **`fabrica`**: es el programa.

## 3. Primera prueba (gratis, sin claves)

1. Abre la carpeta `fabrica` y haz **doble clic en `Abrir panel.bat`**.
   Se abre una ventana negra (déjala abierta: es la fábrica funcionando) y el navegador con el
   panel. Si Windows avisa de que es un archivo descargado, pulsa «Más información → Ejecutar
   de todas formas».
2. En el panel, pulsa **«Usar el ejemplo»**: crea un juego de ejemplo con dos luchadores.
3. Pulsa **«▶ Ejecutar»**. En unos segundos aparecen los primeros recursos (de relleno).
4. Lo que **espera tu visto bueno** sale en naranja: pulsa **Aprobar**, o **Rechazar…** y
   escribe qué cambiar. Vuelve a pulsar **Ejecutar** para seguir con lo que dependía de eso.
5. Los modelos 3D se ven con **«Ver en 3D»** y se giran con el ratón.

Tu proyecto se guarda en **Documentos\Juegos\mi_juego**. Para cerrar la fábrica, cierra la
ventana negra (lo que estuviera a medias se retoma la próxima vez).

> En Mac o Linux: abre la Terminal en la carpeta `fabrica` y escribe
> `python3 -m fabrica panel -p ~/Juegos/mi_juego`

---

## 4. Claude: tu director creativo y tu revisor

Claude escribe el diseño completo del juego a partir de tu idea (personajes, animaciones,
frases, efectos y música) y, si quieres, mira cada imagen antes que tú y manda rehacer lo que
salga mal.

1. Crea una cuenta en **platform.claude.com**.
2. En **Settings → Billing** añade saldo (con 5 dólares tienes para muchas pruebas).
3. En **Settings → API keys** pulsa **Create Key** y copia la clave (empieza por `sk-ant-`).
   Solo se ve una vez: guárdala en un sitio seguro.
4. Abre `cmd` y escribe (con tu clave entre las comillas):
   ```
   setx ANTHROPIC_API_KEY "sk-ant-tu-clave"
   python -m pip install anthropic
   ```
5. Cierra la ventana negra de la fábrica y vuelve a abrir `Abrir panel.bat` (las claves nuevas
   solo se ven al abrirla de nuevo).

**Para usarlo:** en un proyecto nuevo, el panel te ofrece **«Cuéntale tu idea a Claude»**.
Escribe lo que quieres con tus palabras (cuántos personajes, cómo son, el estilo...) y en unos
minutos tendrás el diseño. Los personajes siempre son originales: si mencionas una serie, la toma
solo como referencia de estilo. Después puedes cambiar cualquier cosa en el botón **Diseño**.

**Para que revise las imágenes:** en **Diseño**, busca la línea
`# revisar = ["concepto", "modelo3d", "limpieza"]`, quítale el `#` del principio y guarda.

**Cuánto cuesta:** cada revisión, unos céntimos; escribir un diseño completo, normalmente menos
de 1 €.

> Para tener varios proyectos: crea la variable `FABRICA_PROYECTO` con otra carpeta
> (`setx FABRICA_PROYECTO "C:\Juegos\otro_juego"`) y abre el panel de nuevo.

## 5. Voces, efectos y música: ElevenLabs

1. Crea una cuenta en **elevenlabs.io** y elige un plan (cada voz, efecto o canción gasta
   créditos del plan).
2. Copia tu clave en **elevenlabs.io/app/settings/api-keys** y guárdala igual que la de Claude:
   ```
   setx ELEVENLABS_API_KEY "tu-clave"
   ```
3. En el panel, **Diseño**: en `[fabrica.proveedores]` pon `voz`, `sonido` y `musica` a
   `"elevenlabs"`.
4. Para las voces: en **elevenlabs.io/app/voice-library** elige una voz para cada personaje,
   añádela a tus voces y copia su **ID**. Pégalo en el `voz_id` de ese personaje en **Diseño**.
5. Vuelve a abrir el panel y pulsa **Ejecutar**.

## 6. Arte conceptual gratis en tu PC: ComfyUI (opcional)

Necesitas una tarjeta gráfica **NVIDIA con 8 GB o más** (o un Mac con chip Apple). Si no la
tienes, salta al paso 7: Meshy también hace el arte conceptual.

1. Descarga **ComfyUI Desktop** de **comfy.org/download** e instálalo.
2. Descarga un modelo de estilo anime: en **huggingface.co/cagliostrolab/animagine-xl-4.0**,
   pestaña **Files**, el archivo **`animagine-xl-4.0.safetensors`** (unos 7 GB).
3. Ponlo en la carpeta `models\checkpoints` de ComfyUI (la eliges al instalarlo; dentro de
   ComfyUI también puedes verla en los ajustes).
4. En el panel, **Diseño**: pon `concepto = "comfyui"` en `[fabrica.proveedores]` y, debajo,
   quita los `#` de estas líneas para que queden así:
   ```
   [fabrica.comfyui]
   modelo = "animagine-xl-4.0.safetensors"
   ```
5. **Deja ComfyUI abierto** mientras la fábrica trabaja.

Antes de vender el juego, lee la licencia del modelo que uses (Animagine XL 4.0 usa la licencia
OpenRAIL++, que tiene condiciones de uso).

## 7. Modelos 3D, esqueleto y animaciones: Meshy

1. Crea una cuenta en **meshy.ai** con un **plan de pago** (sin él no se pueden crear claves
   para la API).
2. Crea la clave en **meshy.ai/developers/keys** y guárdala:
   ```
   setx MESHY_API_KEY "tu-clave"
   ```
3. En **Diseño**, en `[fabrica.proveedores]`: `modelo3d`, `rig` y `animacion` a `"meshy"`
   (y `concepto` también, si no usas ComfyUI).
4. Para `limpieza`, pon `"blender"` (paso 8) o, mientras tanto, `"copiar"`.

Cada modelo, esqueleto y animación gasta créditos de Meshy. Si cierras la fábrica mientras
Meshy trabaja, el encargo queda apuntado y se recoge después **sin pagarlo otra vez**.

## 8. Limpieza de los modelos: Blender (gratis)

1. Descarga **Blender** de **blender.org/download** (la versión LTS, por ejemplo la 5.2) e
   instálalo.
2. En **Diseño**, pon `limpieza = "blender"`.

La fábrica lo encuentra sola. Deja cada modelo a la altura del personaje, con los pies en el
suelo, sin polígonos de más, y hace una vista previa para revisarlo.

## 9. Llevarlo a Godot

1. Descarga **Godot 4** de **godotengine.org/download** (no necesita instalación).
2. Crea o abre el proyecto de tu juego.
3. En el panel, **Llevar a Godot** y escribe la carpeta del proyecto (la que tiene el archivo
   `project.godot`). Copia todo lo aprobado a `recursos_fabrica`, con un índice para el juego.

---

## Si algo falla

| Lo que ves | Qué hacer |
|---|---|
| «python no se reconoce como un comando» | Reinstala Python marcando «Add python.exe to PATH» (paso 1). |
| Una tarea dice «sin agente: falta la clave...» | Guarda la clave con `setx` (pasos 4 a 7) y vuelve a abrir el panel. |
| «Falta la librería de Claude» | En `cmd`: `python -m pip install anthropic` |
| «ComfyUI no responde» | Abre ComfyUI antes de pulsar Ejecutar. |
| «No encuentro Blender» | Instálalo (paso 8). Si lo tienes en otra carpeta: `setx BLENDER "C:\ruta\blender.exe"` |
| Windows pregunta por el cortafuegos | Puedes permitirlo: el panel solo escucha en tu propio PC. |
| El navegador no se abre solo | Copia la dirección que sale en la ventana negra (`http://127.0.0.1:8765`). |
| El diseño no se guarda | El panel te dice qué línea tiene el error; corrígela y vuelve a guardar. |

**Importante:** las claves son como contraseñas. No las pegues en el diseño ni las compartas;
la fábrica las lee de Windows y nunca las guarda en el proyecto.

## Orden recomendado para tu primer juego

1. Prueba el recorrido entero con el ejemplo (paso 3, gratis).
2. Activa Claude y pídele el diseño de tu juego (paso 4).
3. Arte conceptual con ComfyUI o Meshy, con Claude revisando (pasos 4, 6 y 7).
4. Modelos, esqueletos y animaciones con Meshy, limpieza con Blender (pasos 7 y 8).
5. Voces, efectos y música con ElevenLabs (paso 5).
6. Llévalo a Godot (paso 9).
