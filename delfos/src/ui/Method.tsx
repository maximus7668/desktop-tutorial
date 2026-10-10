import { MARKET_WEIGHT } from '../model/predict';
import { LogoMark } from './icons';

export function Method() {
  const w = Math.round(MARKET_WEIGHT * 100);
  return (
    <div className="view method">
      <header className="view-head method-hero">
        <LogoMark size={56} />
        <div>
          <h1>Cómo pronostica Delfos</h1>
          <p className="muted">
            El nombre viene del oráculo de Delfos; la marca es la Δ con la que empieza Δελφοί dentro de un anillo de probabilidad.
            Aquí no hay corazonadas: cada número sale de datos públicos y de un modelo que puedes revisar.
          </p>
        </div>
      </header>

      <section className="panel prose">
        <h2>1. Los datos</h2>
        <p>
          Calendario, resultados, clasificaciones, rankings, cuotas y logos salen de los servicios públicos de ESPN.
          La versión web los pide en directo cada vez que abres un día (el día de hoy se refresca cada minuto); la versión
          compartida como Artifact lleva una instantánea con la fecha indicada arriba.
        </p>
      </section>

      <section className="panel prose">
        <h2>2. Fútbol: Poisson con corrección de Dixon-Coles</h2>
        <p>
          Cada equipo tiene una fuerza de ataque (goles a favor frente a la media de su liga) y una de defensa (goles en contra).
          Al principio de temporada esas cifras se mezclan con las de la temporada anterior, como si valieran ocho partidos, para
          que una racha de tres jornadas no dispare los números. Los recién ascendidos empiezan algo por debajo de la media.
        </p>
        <p>
          Con ataque, defensa y factor campo salen los goles esperados de cada equipo. Una distribución de Poisson, corregida para los
          marcadores bajos (0-0, 1-0, 0-1, 1-1), da la probabilidad de cada resultado exacto. De esa matriz salen el 1X2, el más/menos de 2,5,
          el ambos marcan y el marcador más probable. En Champions, Europa League y Libertadores cada equipo trae su fuerza de su liga,
          corregida por el nivel de esa liga.
        </p>
      </section>

      <section className="panel prose">
        <h2>3. NBA, NFL, MLB y NHL: diferencia de puntos</h2>
        <p>
          El rating de un equipo es su diferencia media de puntos (o carreras, o goles) por partido, encogida hacia la temporada anterior.
          El margen esperado es la diferencia de ratings más la ventaja de campo, y la probabilidad de ganar sale de una distribución normal
          con la dispersión típica de cada deporte. En pretemporada pesa casi todo el histórico y la confianza baja.
        </p>
      </section>

      <section className="panel prose">
        <h2>4. Tenis y Fórmula 1</h2>
        <p>
          En tenis se comparan los puntos del ranking ATP o WTA (modelo de Bradley-Terry) y se reparte esa probabilidad en marcadores
          por sets. En F1 se simulan 12.000 carreras: la fuerza de cada piloto mezcla sus puntos por carrera, la forma de las últimas
          cinco citas y lo que ya ha pasado en el fin de semana (libres, sprint y, sobre todo, la clasificación).
        </p>
      </section>

      <section className="panel prose">
        <h2>5. Modelo y mercado</h2>
        <p>
          Cuando hay cuotas, se les quita el margen de la casa y se combinan con el modelo: el mercado pesa un {w} % y el modelo un {100 - w} %
          (un 75 % el mercado si hay pocos datos propios). En fútbol, los goles esperados se reajustan para que la matriz de marcadores cuadre
          con ese pronóstico final.
        </p>
        <p>
          <b>Valor</b> significa que la probabilidad de Delfos multiplicada por la cuota supera 1,05, es decir, que el precio paga al menos un 5 %
          más de lo que el riesgo merece. Solo se marca en resultados con al menos un 30 % de probabilidad.
        </p>
      </section>

      <section className="panel prose">
        <h2>6. Confianza</h2>
        <p>
          En fútbol la confianza es alta desde un 60 % para el resultado elegido y media desde un 46 %. En deportes sin empate, alta desde un 70 %
          y media desde un 58 %. Si faltan datos se rebaja un escalón. La página de rendimiento muestra cuánto acierta cada nivel.
        </p>
      </section>

      <section className="panel prose responsible">
        <h2>Juego responsable</h2>
        <p>
          Delfos es una herramienta de análisis. No acepta apuestas, no enlaza con casas de apuestas y no garantiza resultados:
          un 70 % significa que tres de cada diez veces pasa lo contrario. Si apuestas, hazlo solo si eres mayor de edad, con dinero que puedas perder,
          y pide ayuda si deja de ser un entretenimiento (en España tienes información y ayuda en <b>jugarbien.es</b>).
        </p>
        <p className="muted small">Logos y marcas pertenecen a sus propietarios y se muestran solo para identificar a equipos y competiciones.</p>
      </section>
    </div>
  );
}
