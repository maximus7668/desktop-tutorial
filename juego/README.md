# Ryūsei Clash (juego)

Juego de lucha 3D en arenas abiertas con estética anime, hecho en **Godot 4.7**.
Es la primera versión jugable: dos luchadores, una arena y todas las mecánicas base.
Los cuerpos son provisionales (hechos con piezas simples). Cuando la fábrica
(`../fabrica`) entregue modelos, voces y sonidos aprobados, el juego los usa solos.

## Abrirlo

1. Descarga Godot 4.7 (versión estándar, no la .NET) desde godotengine.org.
2. En el gestor de proyectos: **Importar** → elige el archivo `juego/project.godot`.
3. Pulsa **F5** (o el botón ▶) para jugar.

## Qué hay

- **Vuelo libre** alrededor del rival, con cámara fija en él.
- **Combo cuerpo a cuerpo** de 5 golpes; el último lanza al rival por los aires.
  Si estás lejos, el primer golpe es una **embestida** que te lleva hasta él.
- **Golpe fuerte**: mantener y soltar el botón de golpe. Rompe la guardia.
- **Ráfagas de ki**, **guardia** y **cargar ki** (5 barras).
- **Paso rápido**: si lo pulsas justo antes de un golpe y tienes media barra de ki,
  te teletransportas detrás del rival y lo dejas aturdido.
- **Súper ataque** (2 barras): un rayo de energía con plano de cámara propio.
  Si los dos lanzan el súper a la vez, hay **choque de rayos**: gana quien machaque más.
- **Arena** con mesetas que se rompen cuando alguien sale volando contra ellas.
- **Rival controlado por la CPU** en tres dificultades, que reacciona con retraso
  humano y usa las mismas acciones que tú.
- Presentación, K.O. a cámara lenta, fin por tiempo, pausa, revancha.

Los controles completos están en el menú **Controles** del juego (teclado y mando).

## Pruebas

Las pruebas simulan combates fotograma a fotograma, sin ventana:

```
godot --headless --path juego res://tests/pruebas.tscn
```

Para ver cómo queda algo sin abrir el editor (por ejemplo, el choque de rayos):

```
godot --path juego --fixed-fps 60 res://tests/captura.tscn -- choque 1.8 res://tests/capturas/choque.png
```

Escenarios de captura: `titulo`, `combate`, `cerca`, `rayo`, `choque`, `carga`.

## Estructura

```
escenas/principal.tscn        pantalla inicial
scripts/principal.gd          menús: título, selección, controles, pausa, resultado
scripts/combate/combate.gd    fases, proyectiles, rayos, choque de rayos, efectos
scripts/combate/luchador.gd   estados, movimiento y ataques de un luchador
scripts/combate/control_*.gd  quién manda: jugador, CPU o guion de pruebas
scripts/combate/cuerpo_anime.gd  cuerpo provisional y poses (o el modelo de la fábrica)
scripts/combate/arena.gd      escenario
scripts/ui/hud.gd             barras de vida y ki, avisos, medidor del choque
scripts/datos/personajes.gd   fichas de los luchadores
scripts/autoload/             controles, recursos de la fábrica y sonidos
shaders/                      cel-shading, contorno, energía y suelo
tests/                        pruebas y capturas
```

## Recursos de la fábrica

`scripts/autoload/recursos.gd` lee `res://recursos_fabrica/indice.json`. Si existe un
modelo, una voz o un sonido aprobado con el mismo id (`ren`, `yuki`, `golpe_fuerte`...),
se usa en lugar del provisional. Si no, el juego sigue con lo suyo.
