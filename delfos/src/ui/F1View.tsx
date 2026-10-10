import { useEffect, useMemo, useState } from 'react';
import { F1_TEAMS } from '../data/leagues';
import { loadF1 } from '../data/source';
import type { F1Data } from '../data/types';
import { simulateRace } from '../model/f1';
import { Empty, TeamLogo } from './common';
import { dateTime, dec, pct } from './format';
import { Icon } from './icons';

const SESSION_NAMES: Record<string, string> = {
  FP1: 'Libres 1', FP2: 'Libres 2', FP3: 'Libres 3', SS: 'Clasificación sprint', SR: 'Sprint', Qual: 'Clasificación', Race: 'Carrera',
};

const GP: [RegExp, string][] = [
  [/singapore/i, 'Singapur'], [/united states|austin/i, 'Estados Unidos'], [/mexic/i, 'México'], [/s(ã|a)o paulo|brazil/i, 'São Paulo'],
  [/las vegas/i, 'Las Vegas'], [/qatar/i, 'Catar'], [/abu dhabi/i, 'Abu Dabi'], [/azerbaijan|baku/i, 'Azerbaiyán'], [/japan/i, 'Japón'],
  [/italian|italy|monza/i, 'Italia'], [/dutch|netherlands/i, 'Países Bajos'], [/spanish|spain|barcelona|madrid/i, 'España'],
  [/british/i, 'Gran Bretaña'], [/belgian/i, 'Bélgica'], [/hungarian/i, 'Hungría'], [/austrian/i, 'Austria'], [/canadian|canada/i, 'Canadá'],
  [/monaco/i, 'Mónaco'], [/miami/i, 'Miami'], [/saudi/i, 'Arabia Saudí'], [/bahrain/i, 'Baréin'], [/australian/i, 'Australia'], [/chinese|china/i, 'China'],
];
const gpName = (n: string) => {
  const hit = GP.find(([re]) => re.test(n));
  return hit ? `Gran Premio de ${hit[1]}` : n;
};

export function F1View() {
  const [data, setData] = useState<F1Data | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    loadF1().then(setData).catch(() => setError(true));
  }, []);
  const odds = useMemo(() => (data ? simulateRace(data) : []), [data]);
  if (error) return <Empty title="No se pudo cargar la Fórmula 1">Comprueba la conexión y vuelve a intentarlo.</Empty>;
  if (!data) return <div className="skeleton-list" aria-hidden="true"><div className="skeleton tall" /></div>;
  const race = data.race;
  const raceSession = race?.sessions.find((s) => s.type === 'Race');
  const finished = raceSession?.status === 'post';
  const maxWin = Math.max(...odds.map((o) => o.win), 0.01);
  const fav = odds[0];
  const names = new Map(data.drivers.map((d) => [d.id, d]));

  return (
    <div className="f1">
      {race ? (
        <section className="gp">
          <div className="gp-head">
            <span className="eyebrow">Próximo Gran Premio</span>
            <h2>{gpName(race.name)}</h2>
            {race.venue && <p className="muted"><Icon name="pin" size={15} /> {race.venue}{race.city ? `, ${race.city}` : ''}</p>}
          </div>
          <ol className="sessions">
            {race.sessions.map((s) => (
              <li key={s.type} className={`session session-${s.status}`}>
                <span className="session-name">{SESSION_NAMES[s.type] ?? s.type}</span>
                <span className="session-when">{s.status === 'post' ? 'Terminada' : dateTime(s.date)}</span>
                {s.status === 'post' && s.order[0] && <span className="session-top">1.º {names.get(s.order[0])?.short ?? ''}</span>}
              </li>
            ))}
          </ol>
          {fav && !finished && (
            <div className="gp-fav">
              <TeamLogo team={{ logo: fav.driver.flag, abbr: fav.driver.abbr, name: fav.driver.name }} size={44} flag />
              <div>
                <span className="eyebrow">Favorito de Delfos</span>
                <b className="gp-fav-name">{fav.driver.name}</b>
                <span className="muted">{F1_TEAMS[fav.driver.abbr]?.team ?? ''}</span>
              </div>
              <span className="gp-fav-num">{pct(fav.win)}</span>
            </div>
          )}
        </section>
      ) : (
        <Empty title="No hay Gran Premio a la vista" />
      )}

      <section className="panel">
        <h3 className="panel-title">Probabilidades de carrera</h3>
        <p className="muted small">12.000 carreras simuladas con la forma de la temporada, las últimas cinco citas y las sesiones ya disputadas este fin de semana.</p>
        <div className="table-wrap">
          <table className="f1-table">
            <thead>
              <tr>
                <th>Piloto</th>
                <th className="num">Victoria</th>
                <th className="num">Podio</th>
                <th className="num hide-sm">Puntos</th>
                <th className="num hide-sm">Pos. media</th>
              </tr>
            </thead>
            <tbody>
              {odds.map((o) => {
                const team = F1_TEAMS[o.driver.abbr];
                return (
                  <tr key={o.driver.id}>
                    <td>
                      <span className="driver">
                        <i className="team-stripe" style={{ background: team?.color ?? 'var(--line)' }} />
                        <TeamLogo team={{ logo: o.driver.flag, abbr: o.driver.abbr, name: o.driver.name }} size={20} flag />
                        <span>
                          <b>{o.driver.name}</b>
                          <small className="muted">{team?.team ?? '—'} · {o.driver.points} pts</small>
                        </span>
                      </span>
                    </td>
                    <td className="num">
                      <span className="win-cell">
                        <span className="win-bar"><span style={{ width: `${(o.win / maxWin) * 100}%` }} /></span>
                        {o.win < 0.005 ? '<1 %' : pct(o.win)}
                      </span>
                    </td>
                    <td className="num">{o.podium < 0.005 ? '<1 %' : pct(o.podium)}</td>
                    <td className="num hide-sm">{pct(o.points)}</td>
                    <td className="num hide-sm">{dec(o.expected)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
