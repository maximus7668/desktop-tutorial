import { useEffect, useMemo, useState } from 'react';
import { F1_TEAMS, LEAGUES, LEAGUE_BY_ID } from '../data/leagues';
import { loadF1, loadRankings, loadTable } from '../data/source';
import type { F1Data, LeagueTable, RankEntry, TeamStats } from '../data/types';
import { readLocal, writeLocal } from '../state';
import { Empty, LeagueLogo, TeamLogo } from './common';
import { dec } from './format';

const SELECTABLE = LEAGUES.filter((l) => l.id !== 'uefa.nations');

export function Standings() {
  const [id, setId] = useState<string>(() => readLocal('table', 'esp.1'));
  useEffect(() => writeLocal('table', id), [id]);
  const league = LEAGUE_BY_ID[id] ?? LEAGUE_BY_ID['esp.1'];
  return (
    <div className="view">
      <header className="view-head">
        <h1>Clasificaciones</h1>
        <p className="muted">Las mismas tablas que alimentan el modelo.</p>
      </header>
      <nav className="leagues wrap" aria-label="Competición">
        {SELECTABLE.map((l) => (
          <button key={l.id} type="button" className={`league-chip ${id === l.id ? 'is-on' : ''}`} onClick={() => setId(l.id)} aria-pressed={id === l.id}>
            {l.logo ? <LeagueLogo league={l} size={18} /> : <span className="tour-badge sm">{l.short}</span>}
            {l.short}
          </button>
        ))}
      </nav>
      {league.sport === 'racing' ? <F1Standings /> : league.sport === 'tennis' ? <Rankings id={league.id as 'atp' | 'wta'} /> : <TeamTable leagueId={league.id} />}
    </div>
  );
}

function TeamTable({ leagueId }: { leagueId: string }) {
  const [t, setT] = useState<LeagueTable | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    setT(null);
    setErr(false);
    loadTable(leagueId).then(setT).catch(() => setErr(true));
  }, [leagueId]);
  const league = LEAGUE_BY_ID[leagueId];
  const soccer = league.sport === 'soccer';
  const groups = useMemo(() => {
    const g = new Map<string, TeamStats[]>();
    for (const r of t?.current || []) {
      const k = r.group || '';
      if (!g.has(k)) g.set(k, []);
      g.get(k)!.push(r);
    }
    for (const rows of g.values()) {
      rows.sort((a, b) => soccer
        ? (a.rank ?? 99) - (b.rank ?? 99)
        : winPct(b) - winPct(a) || (b.gf - b.ga) - (a.gf - a.ga));
    }
    return [...g.entries()];
  }, [t, soccer]);
  if (err) return <Empty title="No se pudo cargar la clasificación" />;
  if (!t) return <div className="skeleton-list" aria-hidden="true"><div className="skeleton tall" /></div>;
  if (!t.current.length) return <Empty title="Sin clasificación disponible">Esta competición aún no tiene tabla publicada.</Empty>;
  return (
    <section className="panel">
      <h3 className="panel-title">{t.season || league.name}</h3>
      {groups.map(([g, rows]) => (
        <div key={g} className="table-block">
          {groups.length > 1 && <h4 className="table-group">{translateGroup(g)}</h4>}
          <div className="table-wrap">
            <table className="standings">
              <thead>
                {soccer ? (
                  <tr><th className="num">#</th><th>Equipo</th><th className="num">PJ</th><th className="num">G</th><th className="num">E</th><th className="num">P</th><th className="num hide-sm">GF</th><th className="num hide-sm">GC</th><th className="num">DG</th><th className="num">Pts</th></tr>
                ) : (
                  <tr><th className="num">#</th><th>Equipo</th><th className="num">G</th><th className="num">P</th>{league.sport === 'hockey' && <th className="num">PR</th>}<th className="num">%</th><th className="num hide-sm">A favor</th><th className="num hide-sm">En contra</th><th className="num">Dif.</th><th className="num hide-sm">Racha</th></tr>
                )}
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={r.teamId}>
                    <td className="num muted">{soccer ? r.rank ?? i + 1 : i + 1}</td>
                    <td><span className="team-cell"><TeamLogo team={{ logo: r.logo, abbr: r.abbr, name: r.name }} size={22} /> <span>{r.name}</span></span></td>
                    {soccer ? (
                      <>
                        <td className="num">{r.gp}</td><td className="num">{r.w}</td><td className="num">{r.d}</td><td className="num">{r.l}</td>
                        <td className="num hide-sm">{r.gf}</td><td className="num hide-sm">{r.ga}</td>
                        <td className="num">{r.gf - r.ga > 0 ? '+' : ''}{r.gf - r.ga}</td>
                        <td className="num"><b>{r.pts ?? r.w * 3 + r.d}</b></td>
                      </>
                    ) : (
                      <>
                        <td className="num">{r.w}</td><td className="num">{r.l}</td>{league.sport === 'hockey' && <td className="num">{r.otl}</td>}
                        <td className="num">{winPct(r).toFixed(3).replace(/^0/, '').replace('.', ',')}</td>
                        <td className="num hide-sm">{r.gp ? dec(r.gf / r.gp) : '—'}</td><td className="num hide-sm">{r.gp ? dec(r.ga / r.gp) : '—'}</td>
                        <td className="num">{r.gp ? `${r.gf - r.ga >= 0 ? '+' : ''}${dec((r.gf - r.ga) / r.gp)}` : '—'}</td>
                        <td className="num hide-sm">{translateStreak(r.streak)}</td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
      {!soccer && <p className="muted small">A favor, en contra y diferencia: por partido.</p>}
    </section>
  );
}

const winPct = (r: TeamStats) => (r.gp ? (r.w + 0.5 * r.d) / r.gp : 0);

const translateGroup = (g: string) =>
  g.replace('Eastern Conference', 'Conferencia Este').replace('Western Conference', 'Conferencia Oeste')
    .replace('American Football Conference', 'AFC').replace('National Football Conference', 'NFC')
    .replace('American League', 'Liga Americana').replace('National League', 'Liga Nacional');

const translateStreak = (s?: string) => (s ? s.replace(/^W/, 'G').replace(/^L/, 'P').replace(/^T/, 'E') : '—');

function Rankings({ id }: { id: 'atp' | 'wta' }) {
  const [rows, setRows] = useState<RankEntry[] | null>(null);
  useEffect(() => {
    setRows(null);
    loadRankings(id).then(setRows).catch(() => setRows([]));
  }, [id]);
  if (!rows) return <div className="skeleton-list" aria-hidden="true"><div className="skeleton tall" /></div>;
  if (!rows.length) return <Empty title="Ranking no disponible" />;
  return (
    <section className="panel">
      <h3 className="panel-title">Ranking {id.toUpperCase()}</h3>
      <div className="table-wrap">
        <table className="standings">
          <thead><tr><th className="num">#</th><th>Jugador</th><th className="num">Puntos</th></tr></thead>
          <tbody>
            {rows.slice(0, 100).map((r) => (
              <tr key={r.id}><td className="num muted">{r.rank}</td><td>{r.name}</td><td className="num">{r.points.toLocaleString('es-ES')}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function F1Standings() {
  const [d, setD] = useState<F1Data | null>(null);
  useEffect(() => {
    loadF1().then(setD).catch(() => setD({ drivers: [], constructors: [] }));
  }, []);
  if (!d) return <div className="skeleton-list" aria-hidden="true"><div className="skeleton tall" /></div>;
  return (
    <div className="two-col">
      <section className="panel">
        <h3 className="panel-title">Pilotos</h3>
        <div className="table-wrap">
          <table className="standings">
            <thead><tr><th className="num">#</th><th>Piloto</th><th className="num">Pts</th></tr></thead>
            <tbody>
              {d.drivers.map((r) => (
                <tr key={r.id}>
                  <td className="num muted">{r.rank}</td>
                  <td><span className="driver"><i className="team-stripe" style={{ background: F1_TEAMS[r.abbr]?.color ?? 'var(--line)' }} /><TeamLogo team={{ logo: r.flag, abbr: r.abbr, name: r.name }} size={18} flag /><span>{r.name}</span></span></td>
                  <td className="num"><b>{r.points}</b></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="panel">
        <h3 className="panel-title">Constructores</h3>
        <div className="table-wrap">
          <table className="standings">
            <thead><tr><th className="num">#</th><th>Equipo</th><th className="num">Pts</th></tr></thead>
            <tbody>
              {d.constructors.map((r) => {
                const c = Object.values(F1_TEAMS).find((t) => t.team === r.name)?.color ?? r.color;
                return (
                  <tr key={r.id}>
                    <td className="num muted">{r.rank}</td>
                    <td><span className="driver"><i className="team-stripe" style={{ background: c ?? 'var(--line)' }} /><span>{r.name}</span></span></td>
                    <td className="num"><b>{r.points}</b></td>
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
