# Fábrica de recursos

Programa que junta todo lo que hace falta para terminar un juego (arte conceptual, modelos 3D,
esqueletos, animaciones, voces, efectos de sonido y música) y lo reparte entre agentes de IA.
Un **director** lee el documento de diseño, decide qué se puede hacer ya, se lo encarga al
agente que toca, guarda el resultado y para cuando algo necesita tu visto bueno.

```
juego.toml ──► director ──► agente de concepto ──► agente 3D ──► limpieza ──► rig ──► animaciones
                  │
                  ├──► agente de voces
                  ├──► agente de efectos de sonido
                  └──► agente de música
                                    todo queda en recursos/ y en registro.json
```

## Estado actual

| Parte | Agentes disponibles |
|---|---|
| Director, plan, registro, aprobaciones, montaje en Godot | Hecho |
| Arte conceptual | **Meshy** (texto a imagen) o simulado |
| Modelo 3D | **Meshy** (imagen a 3D) o simulado |
| Limpieza del modelo | **Blender** (en tu PC), `copiar` (lo pasa tal cual) o simulado |
| Esqueleto (rig) | **Meshy** o simulado |
| Animaciones | **Meshy** (biblioteca de acciones) o simulado |
| Voces, efectos de sonido, música | **ElevenLabs** o simulado |

El agente **simulado** crea archivos válidos pero falsos (una hoja SVG, una caja glTF del tamaño
de un personaje, pitidos WAV...). Sirve para probar el flujo entero gratis y sin claves.

## Empezar

Necesitas Python 3.11 o superior. No hay que instalar nada más.

```
cd fabrica
python -m fabrica nuevo mi_juego        # crea mi_juego/juego.toml con dos personajes de ejemplo
python -m fabrica plan -p mi_juego       # lista todas las tareas y de qué dependen
python -m fabrica ejecutar -p mi_juego   # genera todo lo que se pueda hacer ya
python -m fabrica estado -p mi_juego     # cómo va cada tarea
```

En Linux o macOS puede que tengas que escribir `python3` en lugar de `python`.

## El ciclo de trabajo

1. **`ejecutar`**: el director genera, en orden, todo lo que tiene sus dependencias aprobadas.
2. **Revisas** lo que ha dejado en `mi_juego/recursos/`.
3. **`aprobar <id>`** si te gusta (o un grupo entero: `aprobar ren`, `aprobar ren/voz`, `aprobar --todo`).
   **`rechazar <id> --motivo "..."`** si no: el agente recibe tu motivo y lo rehace, y todo lo
   que dependía de ese recurso se vuelve a hacer.
4. Vuelves a **`ejecutar`** y sigue por donde se quedó.
5. Cuando todo está aprobado, **`exportar`** escribe `indice_recursos.json`, la lista de archivos
   que importará el motor del juego.

Los tipos que esperan tu visto bueno se eligen en `juego.toml` (`[fabrica] aprobar`). Por defecto:
concepto, modelo 3D, animaciones y voces.

## Llevar los recursos al motor

```
python -m fabrica montar -p mi_juego --juego ruta/al/proyecto_godot
```

Copia todo lo aprobado a `recursos_fabrica/` dentro del proyecto de Godot, con un
`indice.json` que dice qué archivo es cada cosa (rutas `res://`). La carpeta es de la
fábrica: se rehace entera cada vez y, si ya existe una que no creó la fábrica, no la toca.
Lo hecho por el agente simulado no se copia salvo con `--incluir-simulados`.

## Cambiar el diseño

Edita `juego.toml` y vuelve a ejecutar. Cada tarea guarda una huella de lo que se pidió: si
cambias la descripción de un personaje, se rehace su concepto, su modelo y sus animaciones, pero
no sus voces ni los efectos de sonido. Si añades una animación, solo se hace esa.

## Activar voces, efectos y música reales (ElevenLabs)

1. Crea una cuenta en elevenlabs.io y copia tu clave de API.
2. Define la clave en la terminal antes de ejecutar:
   - Windows (PowerShell): `$env:ELEVENLABS_API_KEY = "tu_clave"`
     (para que se quede guardada: `setx ELEVENLABS_API_KEY "tu_clave"` y abre otra terminal)
   - Linux o macOS: `export ELEVENLABS_API_KEY="tu_clave"`
3. En `juego.toml`, cambia `voz`, `sonido` y `musica` a `"elevenlabs"` en `[fabrica.proveedores]`.
4. Para las voces, pon en cada personaje el `voz_id` de una voz de tu biblioteca de ElevenLabs.

Los sonidos con `bucle = true` (aura, rayo...) se piden a ElevenLabs para que se repitan sin corte.

La clave nunca se guarda en el proyecto. Los efectos tienen que durar de 0,5 a 30 segundos y la
música de 3 segundos a 10 minutos (límites de la API). Si no hay clave, esas tareas quedan como
"sin agente" y el resto sigue. Ojo: cada generación gasta créditos de tu plan de ElevenLabs.

## Activar arte, modelos 3D, esqueleto y animaciones reales (Meshy)

1. Crea una cuenta en meshy.ai (las APIs necesitan un plan de pago) y copia tu clave de API.
2. Defínela como `MESHY_API_KEY` (igual que la de ElevenLabs, más arriba).
3. En `[fabrica.proveedores]` pon `concepto`, `modelo3d`, `rig` y `animacion` a `"meshy"`,
   y `limpieza` a `"copiar"`.

Cómo encadena el trabajo:

- **Concepto:** imagen del personaje de frente y en pose A (la que mejor pasa a 3D).
- **Modelo 3D:** usa esa imagen directamente en Meshy, sin volver a subirla.
- **Esqueleto:** sube el modelo y usa la `altura` del personaje (1,75 m si no la pones).
  Además entrega gratis andar y correr.
- **Animaciones:** cada nombre del diseño se traduce a una acción de la biblioteca de Meshy
  (`patada` → Roundhouse_Kick, `golpe_debil` → Right_Jab_from_Guard...). Para elegir otra,
  recházala poniendo como motivo el número de la acción
  (`rechazar ren/animacion/patada --motivo 215`), o fíjala en `[personajes.acciones]`.

Si Meshy tarda más de 15 minutos, la tarea queda apuntada: en la siguiente ejecución se
recoge sin pedirla (ni pagarla) otra vez. Si Meshy la rechaza, se pide de nuevo.

## Limpiar los modelos con Blender (gratis)

1. Instala Blender desde blender.org (probado con Blender 5.2 LTS).
2. Pon `limpieza = "blender"` en `[fabrica.proveedores]`.

La fábrica lo encuentra sola en las rutas de instalación habituales; si no, define la variable
`BLENDER` con la ruta a `blender.exe`. Blender se abre sin ventana y:

- pone el modelo a la `altura` del personaje, centrado y con los pies en el suelo;
- lo deja en una sola malla y con las normales coherentes;
- lo reduce a 60 000 caras como mucho si viene más pesado;
- guarda `modelo_limpio.glb` y una vista previa `vista.png` para revisarlo.

Si el modelo ya trae esqueleto, no toca sus transformaciones (rompería el rig): solo lo
exporta y hace la vista previa.

## Qué hay en la carpeta de un proyecto

```
mi_juego/
  juego.toml             el diseño: lo editas tú
  registro.json          el estado de cada tarea (lo escribe la fábrica)
  recursos/              lo generado, una carpeta por tarea
    ren/concepto/
    ren/modelo3d/
    ren/animacion/golpe_fuerte/
    sonido/explosion/
    ...
  indice_recursos.json   lo aprobado, listo para el motor (sale con "exportar")
```

## Añadir un agente nuevo

Cada agente es una clase con:

- `nombre`: cómo se escribe en `[fabrica.proveedores]`.
- `tipos`: qué sabe hacer, por ejemplo `frozenset({"modelo3d"})`.
- `disponible()`: devuelve `None` si puede trabajar, o el motivo si no (por ejemplo, que falta la clave).
- `generar(ctx)`: deja sus archivos en `ctx.carpeta` y devuelve `Resultado([archivos], nota)`.
  En `ctx.entradas` recibe los archivos de las tareas de las que depende (por ejemplo, el modelo
  3D recibe la hoja del concepto) y en `ctx.motivo_rechazo` lo que pediste cambiar.

Después se añade en `proveedores()` de `fabrica/agentes/__init__.py`. El agente trabaja en una
carpeta aparte: si falla, lo que ya había no se pierde, y el resto de tareas sigue adelante.

## Próximos agentes

1. **Arte conceptual con ComfyUI** en tu PC, con un LoRA entrenado con tu estilo.
2. **Revisión con Claude**: mira cada recurso y rechaza lo que salga mal antes de que llegue a ti.
3. **Director con Claude**: de una idea escrita al `juego.toml` completo.

## Pruebas

```
cd fabrica
python -m unittest discover -s tests -t .
```

La prueba con Blender de verdad solo se ejecuta si Blender está instalado.
