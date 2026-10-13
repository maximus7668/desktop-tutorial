# Cómo se escribe un guion del canal

El guion es un JSON en `canal-youtube/guiones/` (plantilla en
`canal-youtube/plantillas/guion.ejemplo.json`). La calidad del canal sale de aquí: si el guion
es genérico, ni la mejor voz lo salva.

## Medidas

- **Vídeo largo**: 15–25 min, es decir 2.300–3.900 palabras (la voz va a ~155 palabras por minuto).
  El validador avisa por debajo de 2.000 y por encima de 4.000.
- **Escena**: 1–3 frases (8–20 s), una sola idea, con 2–4 visuales. Ningún plano dura más de 6,5 s.
- **Capítulos**: 5–8, con título corto e intrigante. El primero empieza en la primera escena.
- **Short**: 35–55 s (90–140 palabras), 3 por cada vídeo largo.

## Estructura del vídeo largo

| Tramo | Tiempo | Qué pasa |
|---|---|---|
| Gancho | 0:00–0:30 | La paradoja o la imagen más fuerte, la pregunta del vídeo y lo que se entenderá al final. Primera frase de 15 palabras como mucho. Sin saludos. |
| Contexto | 0:30–3:00 | Cómo era el mundo, qué estaba en juego y quiénes son los protagonistas. |
| Ascenso | 3–8 min | El mecanismo: cómo se ganaba el dinero, con cifras. |
| Giro | 8–12 min | El problema que nadie vio o el dato que lo cambia todo. |
| Caída o consecuencias | 12–17 min | Qué pasó, a quién le costó y con qué cifras. |
| Lección | últimos 2–3 min | La tesis contestada: qué nos enseña hoy. Cierre con una frase que se quede y anuncio del siguiente vídeo. |

**Reenganches** cada 60–90 s: una pregunta abierta, una cifra que sorprende o un «pero». Ponlos
con naturalidad y sin repetir fórmula.

## Cómo suena bien una voz sintética

- Frases cortas: 12–18 palabras de media, 30 como mucho. Una idea por frase, en voz activa.
- Concreto antes que abstracto: nombres, fechas, lugares y cifras («160.000 personas, más que
  Sevilla») en lugar de «una ciudad enorme».
- Tuteo al espectador y castellano neutro: nada de «vosotros» ni jerga de un solo país.
- Números en cifra (1545, 3.000, 45 %): el sistema los lee bien. Sin paréntesis, sin abreviaturas
  raras y sin símbolos.
- Si un nombre extranjero suena mal en el borrador, añade su pronunciación en `voz.pronunciacion`
  de `canal.yaml`.
- Lo debatido se dice como debatido: «las estimaciones van de A a B», «según el historiador X».
- El sufrimiento humano (la mita, las crisis) se cuenta con respeto, sin morbo ni sermones.
- **Prohibido** (el validador lo marca): «en este vídeo», «hola a todos», «bienvenidos», «sin más
  dilación», «no olvides suscribirte», «dale like», «adentrémonos», «sumérgete», «fascinante
  mundo», «desde tiempos inmemoriales», «a lo largo de la historia», «cabe destacar», «en
  conclusión», «en resumen», «quédate hasta el final».
- Llamada a la acción: una sola y natural, hacia el 30–40 % del vídeo, cuando ya has dado algo de
  valor. Al final, solo el anuncio del siguiente vídeo (la pantalla final dura 20 s).

## Visuales

Cada visual es un objeto con un solo tipo:

| Tipo | Para qué | Ejemplo |
|---|---|---|
| `wikimedia` | Archivo histórico: grabados, pinturas, mapas antiguos y fotos de época. Mejor con el título exacto encontrado al investigar | `{"wikimedia": "File:Cerro rico potosi.jpg"}` o `{"wikimedia": "Potosí grabado siglo XVII"}` |
| `mapa` | Dónde y por dónde: rutas, territorios. Animado | `{"mapa": "La ruta de la plata", "puntos": [{"n": "Potosí", "lat": -19.58, "lon": -65.75}, {"n": "Sevilla", "lat": 37.39, "lon": -5.99}], "ruta": true, "resaltar": ["BOL", "ESP"]}` |
| `grafico` | Cifras que se comparan o evolucionan. Animado. `forma`: `barras`, `linea` o `cronologia` | `{"grafico": "Población hacia 1610", "forma": "barras", "datos": [["Potosí", 160000], ["Sevilla", 130000]], "destacar": ["Potosí"], "nota": "Fuente: …"}` |
| `dato` | Una cifra clave, a pantalla completa | `{"dato": "160.000", "sub": "habitantes en 1610"}` |
| `cita` | Una cita **verificada**, con su autor | `{"cita": "…", "autor": "Miguel de Cervantes"}` |
| `tarjeta` | Rótulo de sección (con moderación) | `{"tarjeta": "La mita", "sub": "1573"}` |
| `stock` / `foto` | Recursos actuales: monedas, minas, puertos o texturas. Búsqueda en inglés | `{"stock": "silver coins close up"}` |
| `ia` | Solo ilustración no realista (cuesta dinero y lleva marca de IA) | `{"ia": "ilustración estilo grabado de una mina andina"}` |
| `archivo` | Un archivo propio de `canal-youtube/` | `{"archivo": "propios/grafico.png"}` |
| `de_escena` | Reutilizar en un Short el primer visual de una escena del largo | `{"de_escena": "gancho"}` |

Modificadores:
- `encuadre: [x, y, ancho, alto]` (de 0 a 1) enseña un detalle de una imagen grande.
- `mov`: `zoom_in`, `zoom_out`, `izq`, `der`, `arriba`, `abajo` o `fijo`. Si no se pone, se va alternando.
- `peso` da más tiempo a un visual dentro de su escena.

Reglas: los rótulos (`tarjeta`, `dato`, `cita`) no pasan del 35 % de los visuales. Los mapas y los
gráficos cuentan como imagen y conviene que haya muchos. Ninguna búsqueda se repite más de 2
veces. Alterna archivo, mapa, dato y detalle.

`texto_pantalla` es el rótulo amarillo de 2 a 5 palabras con una fecha, un nombre o una cifra.
Ponlo como mucho cada 3 o 4 escenas.

## Shorts

- La **primera frase es el gancho**, de 12 palabras como mucho, con el dato más sorprendente. Nada
  de contexto antes.
- Una sola idea. El cierre remite al vídeo largo o enlaza con el principio para que se vea en bucle.
- El `texto_pantalla` de la primera escena es el titular de arriba (2 a 4 palabras).
- Los mapas y gráficos funcionan muy bien en vertical; usa `de_escena` para reutilizar visuales.
- Título propio de 60 caracteres como mucho.

## Antes de validar: lista de comprobación

- [ ] Cada fecha, cifra y nombre está en una fuente de `fuentes`, con título y URL. Mínimo 3, y
      serias.
- [ ] Las citas son literales y de quien se dice; si es atribuida o dudosa, se dice así.
- [ ] Los mitos populares se presentan como mitos (p. ej., cifras de muertos infladas).
- [ ] De personas y empresas vivas, solo hechos documentados, atribuidos; nada de acusaciones.
- [ ] La tesis se enuncia en el gancho y se contesta en la lección.
- [ ] Ninguna frase se parece a la de otro vídeo del canal (el validador compara).
- [ ] `sintetico_realista` es `true` si hay IA realista de personas o hechos reales.
