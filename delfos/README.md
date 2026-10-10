# Delfos · Pronósticos deportivos con datos

Delfos es una app web de pronósticos para los deportes más seguidos: fútbol (LaLiga, Premier, Champions, Serie A, Bundesliga, Ligue 1, Europa y Conference League, LaLiga Hypermotion, Portugal, Eredivisie, Liga MX, Argentina, Brasileirão, Libertadores, MLS y Nations League), NBA y WNBA, NFL, MLB, NHL, tenis ATP y WTA, y Fórmula 1.

Cada partido muestra la probabilidad de cada resultado, el marcador más probable, la confianza, la comparación con el mercado y, en fútbol, la matriz completa de marcadores, más/menos goles y ambos marcan.

## Qué incluye

- **Pronósticos del día** con selector de fecha (resultados de días pasados y calendario de la semana), filtros por deporte y competición, «Confianza alta» y «Con valor».
- **El Oráculo del día**: los tres pronósticos más sólidos de competiciones distintas, combinables con un toque.
- **Apuesta recomendada**: en cada partido con cuotas, la selección (ganador, hándicap o total) cuya cuota paga más de lo que vale según Delfos, con valor esperado, cuota mínima y stake prudente (¼ de Kelly, máximo 2 % de la banca). Si ninguna cuota tiene valor, lo dice. Las mejores del día aparecen en «Apuestas recomendadas» y en la «Combinada de valor».
- **Más mercados**: córners, tarjetas, tiros a puerta, tiros y faltas (esperados por equipo, quién tendrá más, líneas de más/menos con cuota justa y una «línea Delfos»), posesión esperada, goles por equipo, portería a cero, margen de victoria, primera parte y descanso/final. En EE. UU., totales por equipo y líneas alternativas.
- **Ficha de partido**: probabilidades 1X2, marcador, cuotas justas frente a cuotas del mercado, mapa de marcadores, mercados de goles, hándicap y totales (EE. UU.), sets (tenis), racha, lanzadores o porteros probables y una explicación de por qué.
- **Mi combinada**: probabilidad conjunta, cuota justa, cuota de mercado y valor esperado. Se guarda en el navegador.
- **Clasificaciones** de todas las ligas, rankings ATP/WTA y mundial de F1 (pilotos y constructores).
- **Rendimiento**: acierto del modelo con los partidos ya jugados, por deporte y por nivel de confianza, puntuación de Brier y gráfico de calibración.
- **F1**: probabilidades de victoria, podio y puntos a partir de 12.000 carreras simuladas.
- **Método**: cómo se calcula todo y aviso de juego responsable.
- Modo claro y oscuro, diseño adaptado a móvil, instalable como app (manifest e iconos).

## Marca

- **Nombre**: Delfos, por el oráculo de Delfos.
- **Logo**: la Δ con la que empieza Δελφοί dentro de un anillo de probabilidad dorado (`public/favicon.svg`, `src/ui/icons.tsx`).
- **Colores**: azul Egeo (`#2340C8`, marca), oro laurel (`#F2B630`, el pronóstico), neutros de mármol frío y los colores reales de cada equipo en las barras de probabilidad.
- **Tipografía**: Big Shoulders Display (titulares y cifras de marcador) y Onest (texto).
- Los logos de equipos, ligas y banderas vienen del CDN de ESPN y pertenecen a sus propietarios.

## Datos

Todo sale de los servicios públicos de ESPN (`site.api.espn.com`): calendario, resultados en directo, clasificaciones (temporada actual y anterior), rankings de tenis, cuotas de DraftKings cuando las hay y logos. No hace falta clave. La versión web pide los datos en directo y refresca el día actual cada minuto.

## Modelos

| Deporte | Modelo |
|---|---|
| Fútbol | Poisson bivariante con corrección de Dixon-Coles. Ataque y defensa por equipo desde la clasificación, encogidos hacia la temporada anterior. En competiciones europeas cada equipo usa su liga nacional corregida por el nivel de la liga. |
| NBA, WNBA, NFL, MLB, NHL | Diferencia de puntos por partido encogida hacia la temporada anterior, ventaja de campo y distribución normal del margen. |
| Tenis | Puntos del ranking (Bradley-Terry) y reparto en sets. |
| F1 | Plackett-Luce simulado: puntos por carrera, forma reciente, sesiones del fin de semana y abandonos. |
| Córners, tarjetas, tiros, faltas | Tendencia a favor y en contra de cada equipo en su liga (últimos 75 días) frente a la media, factor campo de la liga y binomial negativa. El reparto entre equipos de córners y tiros se corrige con el dominio que anticipan los goles esperados. |

Con cuotas, el pronóstico final mezcla mercado (65 %) y modelo (35 %); en fútbol los goles esperados se reajustan para que la matriz cuadre con ese resultado. La apuesta recomendada (`src/model/bets.ts`) exige un valor esperado de al menos +4 %, una probabilidad mínima del 33 % y una cuota máxima de 4,5. Detalle completo en la pantalla «Método» y en `src/model/`.

## Uso

```bash
cd delfos
npm install
npm run dev          # http://localhost:5173, datos en directo
npm test             # pruebas de los modelos
npm run build        # web estática en dist/ (sirve en cualquier hosting estático)
```

La carpeta `dist/` se puede publicar tal cual en Cloudflare Pages, Netlify, Vercel o cualquier servidor estático; ESPN permite las peticiones desde el navegador (CORS abierto).

### Versión Artifact (instantánea)

```bash
npm run build:artifact   # .cache/snapshot.ts + dist-artifact/delfos.html
```

Genera un único HTML con los partidos de los últimos 8 días y los 7 siguientes, las clasificaciones y los logos incrustados (WebP), y React desde cdnjs. Es la versión que se comparte como Artifact de Claude, donde no se pueden pedir datos externos. En ese visor aparece además el botón «Análisis del Oráculo», que redacta una previa con Claude a partir de los números de la ficha.

Prueba de integración contra ESPN real:

```bash
LIVE=1 npx vitest run src/data/live.test.ts
```

## Estructura

```
src/
  data/      leagues.ts (catálogo), espn.ts (normalizador), source.ts (directo o instantánea), teamStats.ts (córners, tarjetas…), types.ts
  model/     soccer.ts, us.ts, tennis.ts, f1.ts, odds.ts, predict.ts, props.ts (más mercados), bets.ts (apuesta recomendada) (+ pruebas)
  ui/        pantallas y componentes (Forecasts, MatchDetail, Slip, Standings, Performance, F1View, Method…)
  styles/    app.css (tokens de color y tema claro/oscuro)
scripts/     snapshot.ts (instantánea), artifact.ts (empaquetado para Artifact)
```

## Juego responsable

Delfos es una herramienta de análisis: no acepta apuestas, no enlaza con casas de apuestas y no garantiza resultados. +18.
