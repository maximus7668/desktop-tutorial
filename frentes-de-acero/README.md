# Frentes de Acero

Juego de estrategia por turnos sobre la Segunda Guerra Mundial en Europa, inspirado en *Hearts of Iron IV* pero pensado para aprenderse en cinco minutos.

**Jugar:** abre `frentes-de-acero.html` en cualquier navegador (es un único archivo, funciona sin internet salvo las fuentes). Para desarrollar, abre `index.html`, que carga los archivos de `js/` y `css/` por separado.

## Qué lo hace fácil de aprender

| En HOI4 | En Frentes de Acero |
|---|---|
| Miles de provincias | 218 regiones con nombre (mapa real de 1939) |
| Decenas de recursos, fábricas civiles y militares, plantillas de división | Producción, reclutas y aviación. Dos tipos de división: infantería y blindados |
| Tiempo real con pausa | Turnos de un mes (sept. 1939 – ago. 1945) |
| Batallas opacas | Antes de atacar ves tu **probabilidad de victoria** y cada modificador explicado |
| Árboles de foco enormes | 8–15 focos por nación, con su efecto en una línea y lo que pasó en la historia |
| Wiki obligatoria | Tutorial guiado de 8 pasos, asesor con consejos cada turno y manual en el propio juego |

## Cómo se juega

1. **Produce:** la industria de tus regiones da producción cada mes. Gástala en infantería, blindados o aviones.
2. **Mueve y ataca:** selecciona una región tuya con tropas; las vecinas verdes son movimientos y las rojas muestran tu % de victoria. Puedes sumar tropas de varias regiones a un ataque. Las tropas que no se han movido pueden ir en tren a cualquier región tuya conectada o cruzar los pasos marítimos.
3. **Elige focos nacionales:** decisiones históricas (Plan Cuatrienal, Línea Maginot, Operación Barbarroja, Día D…).
4. **Cuida el suministro:** sin conexión con tu capital o un puerto, tus tropas se debilitan. Si un defensor pierde y no puede retirarse, queda rodeado.
5. **Gana:** un país se rinde al perder su capital y parte de sus ciudades. En agosto de 1945 gana el bando con más puntos de victoria.

Naciones jugables: Alemania, Reino Unido, Francia, Unión Soviética e Italia. Tres niveles de dificultad.

### Historia real

Eventos con fecha y condiciones: Pacto Molotov-Ribbentrop, Guerra de Invierno, Weserübung, Fall Gelb, Francia de Vichy (o la Francia Libre si juegas con Francia), entrada de Italia, Pacto Tripartito, Afrika Korps, invasión de los Balcanes, Barbarroja, Pearl Harbor, Préstamo y Arriendo, Operación Antorcha, caída de Mussolini, Día D, cambios de bando de Rumanía y Bulgaria y paz de Finlandia. Cada evento cuenta lo que ocurrió en la realidad. Si la partida se desvía de la historia, los eventos dejan de dispararse.

## Estructura

```
index.html            página del juego
css/style.css         estilos
js/map.js             regiones, fronteras y adyacencias (generado)
js/data.js            naciones, despliegue inicial, focos y eventos históricos
js/game.js            reglas: combate, suministro, economía, rendiciones (sin DOM)
js/ai.js              IA de las demás naciones
js/ui.js              interfaz: mapa SVG, paneles, combate, asesor y tutorial
tools/                generador del mapa, simulador y empaquetador
frentes-de-acero.html todo junto en un archivo (generado)
```

## Herramientas

```bash
cd tools
npm install
node build-map.mjs          # regenera js/map.js desde Natural Earth con las fronteras de 1939
node simulate.mjs 1 ENG -v  # partida completa IA contra IA (semilla, nación del "jugador")
node bundle.mjs             # regenera frentes-de-acero.html
```

Los datos geográficos vienen de [Natural Earth](https://www.naturalearthdata.com/) (dominio público) a través del paquete `world-atlas`; las fronteras de 1939 se reconstruyen en `tools/build-map.mjs`.
