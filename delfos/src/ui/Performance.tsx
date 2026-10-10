import { useEffect, useMemo, useState } from 'react';
import { LEAGUE_BY_ID, SPORT_BY_ID } from '../data/leagues';
import { addDays, dayKey, loadDay, loadTables, MODE } from '../data/source';
import type { LeagueTable, Match, Outcome } from '../data/types';
import { actualOutcome, predict, type Confidence, type Prediction } from '../model/predict';
import { tablesNeeded } from '../state';
import { Empty, HitMark, TeamLogo } from './common';
import { dateTime, dec, outcomeLabel, pct, plural } from './format';

interface Row {
  m: Match;
  p: Prediction;
  actual: Outcome;
  ok: boolean;
}

const DAYS = MODE === 'snapshot' ? 9 : 4;

function useHistory() {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const today = dayKey(new Date());
        const days = Array.from({ length: DAYS }, (_, i) => addDays(today, -i));
        const parts = await Promise.all(days.map((d) => loadDay(d).then((r) => r.matches).catch(() => [] as Match[])));
        const done = parts.flat().filter((m) => m.completed && actualOutcome(m));
        const tables: Record<string, LeagueTable> = await loadTables(tablesNeeded(done));
        const out: Row[] = [];
        for (const m of done) {
          // Sin cuotas: ESPN las retira al acabar el partido. Se evalúa el modelo puro.
          const p = predict({ ...m, odds: undefined }, { tables });
          const actual = actualOutcome(m)!;
          out.push({ m, p, actual, ok: actual === p.pick });
        }
        out.sort((a, b) => b.m.start.localeCompare(a.m.start));
        if (alive) setRows(out);
      } catch {
        if (alive) setErr(true);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);
  return { rows, err };
}

function brier(r: Row): number {
  const ps: Record<Outcome, number> = { home: r.p.pHome, draw: r.p.pDraw, away: r.p.pAway };
  const keys: Outcome[] = r.p.threeWay ? ['home', 'draw', 'away'] : ['home', 'away'];
  return keys.reduce((s, k) => s + (ps[k] - (r.actual === k ? 1 : 0)) ** 2, 0);
}

export function Performance() {
  const { rows, err } = useHistory();
  const stats = useMemo(() => {
    if (!rows || rows.length === 0) return null;
    const hits = rows.filter((r) => r.ok).length;
    const by = <K extends string>(f: (r: Row) => K) => {
      const g = new Map<K, Row[]>();
      for (const r of rows) {
        const k = f(r);
        if (!g.has(k)) g.set(k, []);
        g.get(k)!.push(r);
      }
      return [...g.entries()].map(([k, v]) => ({ k, n: v.length, acc: v.filter((x) => x.ok).length / v.length }));
    };
    const sport = by((r) => r.m.sport).sort((a, b) => b.n - a.n);
    const order: Confidence[] = ['alta', 'media', 'baja'];
    const conf = by((r) => r.p.confidence).sort((a, b) => order.indexOf(a.k) - order.indexOf(b.k));
    const edges = [0.3, 0.45, 0.55, 0.65, 0.75, 0.85, 1.01];
    const bins = edges.slice(0, -1).map((lo, i) => {
      const hi = edges[i + 1];
      const v = rows.filter((r) => r.p.pickProb >= lo && r.p.pickProb < hi);
      return {
        lo, hi, n: v.length,
        pred: v.length ? v.reduce((s, r) => s + r.p.pickProb, 0) / v.length : 0,
        act: v.length ? v.filter((r) => r.ok).length / v.length : 0,
      };
    }).filter((b) => b.n >= 5);
    const b3 = rows.filter((r) => r.p.threeWay);
    const b2 = rows.filter((r) => !r.p.threeWay);
    return {
      n: rows.length, hits, acc: hits / rows.length, sport, conf, bins,
      brier3: b3.length ? b3.reduce((s, r) => s + brier(r), 0) / b3.length : undefined,
      brier2: b2.length ? b2.reduce((s, r) => s + brier(r), 0) / b2.length : undefined,
      n3: b3.length, n2: b2.length,
    };
  }, [rows]);

  return (
    <div className="view">
      <header className="view-head">
        <h1>Rendimiento</h1>
        <p className="muted">Cómo le ha ido al modelo con los partidos ya jugados de los últimos {DAYS} días.</p>
      </header>
      {err && <Empty title="No se pudo cargar el historial" />}
      {!rows && !err && <div className="skeleton-list" aria-hidden="true"><div className="skeleton tall" /></div>}
      {rows && rows.length === 0 && <Empty title="Aún no hay partidos terminados">Vuelve cuando se hayan jugado los primeros encuentros.</Empty>}
      {stats && rows && (
        <>
          <section className="tiles">
            <div className="tile tile-hero">
              <span className="tile-label">Acierto del pronóstico</span>
              <span className="tile-value">{pct(stats.acc)}</span>
              <span className="tile-sub">{plural(stats.hits, 'acierto', 'aciertos')} de {plural(stats.n, 'partido', 'partidos')}</span>
            </div>
            {stats.brier3 !== undefined && (
              <div className="tile">
                <span className="tile-label">Brier fútbol (1X2)</span>
                <span className="tile-value">{dec(stats.brier3, 3)}</span>
                <span className="tile-sub">Azar: 0,667 · {plural(stats.n3, 'partido', 'partidos')}</span>
              </div>
            )}
            {stats.brier2 !== undefined && (
              <div className="tile">
                <span className="tile-label">Brier resto (2 vías)</span>
                <span className="tile-value">{dec(stats.brier2, 3)}</span>
                <span className="tile-sub">Azar: 0,500 · {plural(stats.n2, 'partido', 'partidos')}</span>
              </div>
            )}
          </section>

          <div className="two-col">
            <section className="panel">
              <h3 className="panel-title">Acierto por deporte</h3>
              <div className="bars">
                {stats.sport.map((s) => (
                  <div key={s.k} className="bar-row">
                    <span className="bar-label">{SPORT_BY_ID[s.k]?.name ?? s.k} <span className="muted">{s.n}</span></span>
                    <span className="bar-track"><span className="bar-fill" style={{ width: `${s.acc * 100}%` }} /></span>
                    <span className="bar-value">{pct(s.acc)}</span>
                  </div>
                ))}
              </div>
            </section>
            <section className="panel">
              <h3 className="panel-title">Acierto por confianza</h3>
              <div className="bars">
                {stats.conf.map((s) => (
                  <div key={s.k} className="bar-row">
                    <span className="bar-label">{s.k.charAt(0).toUpperCase() + s.k.slice(1)} <span className="muted">{s.n}</span></span>
                    <span className="bar-track"><span className="bar-fill" style={{ width: `${s.acc * 100}%` }} /></span>
                    <span className="bar-value">{pct(s.acc)}</span>
                  </div>
                ))}
              </div>
              <p className="muted small">Si el modelo está bien calibrado, la confianza alta acierta más que la media y la media más que la baja.</p>
            </section>
          </div>

          {stats.bins.length >= 2 && <Calibration bins={stats.bins} />}

          <section className="panel">
            <h3 className="panel-title">Últimos resultados</h3>
            <ul className="history">
              {rows.slice(0, 40).map((r) => (
                <li key={r.m.id} className="history-row">
                  <span className="muted small history-when">{dateTime(r.m.start)}</span>
                  <span className="history-match">
                    <TeamLogo team={r.m.home.team} size={18} flag={r.m.sport === 'tennis'} />
                    <span>{r.m.home.team.short} {r.m.sport !== 'tennis' ? <b>{r.m.home.score}–{r.m.away.score}</b> : <span className="muted">–</span>} {r.m.away.team.short}</span>
                    <TeamLogo team={r.m.away.team} size={18} flag={r.m.sport === 'tennis'} />
                  </span>
                  <span className="history-pick">{outcomeLabel(r.m, r.p.pick)} <span className="muted">{pct(r.p.pickProb)}</span></span>
                  <span className="history-league muted small">{LEAGUE_BY_ID[r.m.leagueId]?.short}</span>
                  <HitMark ok={r.ok} />
                </li>
              ))}
            </ul>
          </section>
          <p className="muted small">
            Método de evaluación: para cada partido terminado se recalcula el pronóstico quitando su propio resultado de la clasificación.
            Las cuotas de partidos ya jugados no están disponibles, así que aquí se mide solo el modelo estadístico; el pronóstico completo, que también usa el mercado, suele afinar más.
          </p>
        </>
      )}
    </div>
  );
}

function Calibration({ bins }: { bins: { lo: number; hi: number; n: number; pred: number; act: number }[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 520, H = 300, L = 44, R = 16, T = 16, B = 40;
  const x0 = 0.3, x1 = 1;
  const sx = (v: number) => L + ((v - x0) / (x1 - x0)) * (W - L - R);
  const sy = (v: number) => T + (1 - v) * (H - T - B);
  const ticksX = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1];
  const ticksY = [0, 0.25, 0.5, 0.75, 1];
  const path = bins.map((b, i) => `${i ? 'L' : 'M'}${sx(b.pred).toFixed(1)},${sy(b.act).toFixed(1)}`).join(' ');
  const hb = hover !== null ? bins[hover] : null;
  return (
    <section className="panel">
      <h3 className="panel-title">Calibración</h3>
      <p className="muted small">Cada punto agrupa pronósticos con una probabilidad parecida. Sobre la diagonal, el modelo dice exactamente lo que luego pasa.</p>
      <div className="chart-wrap">
        <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Probabilidad pronosticada frente a acierto real">
          {ticksY.map((t) => (
            <g key={`y${t}`}>
              <line x1={L} x2={W - R} y1={sy(t)} y2={sy(t)} className="grid" />
              <text x={L - 8} y={sy(t) + 4} className="axis-text" textAnchor="end">{Math.round(t * 100)}%</text>
            </g>
          ))}
          {ticksX.map((t) => (
            <text key={`x${t}`} x={sx(t)} y={H - B + 18} className="axis-text" textAnchor="middle">{Math.round(t * 100)}%</text>
          ))}
          <text x={(L + W - R) / 2} y={H - 4} className="axis-title" textAnchor="middle">Probabilidad pronosticada</text>
          <line x1={sx(x0)} y1={sy(x0)} x2={sx(1)} y2={sy(1)} className="diag" />
          <path d={path} className="cal-line" fill="none" />
          {bins.map((b, i) => (
            <g key={i} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(i)} onBlur={() => setHover(null)} tabIndex={0} role="button" aria-label={`${Math.round(b.pred * 100)} % pronosticado, ${Math.round(b.act * 100)} % real, ${b.n} partidos`}>
              <circle cx={sx(b.pred)} cy={sy(b.act)} r={14} fill="transparent" />
              <circle cx={sx(b.pred)} cy={sy(b.act)} r={hover === i ? 6.5 : 5} className="cal-dot" />
            </g>
          ))}
          {bins.length > 0 && (
            <text x={sx(bins[bins.length - 1].pred) - 10} y={sy(bins[bins.length - 1].act) - 12} className="axis-text strong" textAnchor="end">Delfos</text>
          )}
        </svg>
        {hb && (
          <div className="tooltip" style={{ left: `${(sx(hb.pred) / W) * 100}%`, top: `${(sy(hb.act) / H) * 100}%` }}>
            <b>{Math.round(hb.lo * 100)}–{Math.min(100, Math.round(hb.hi * 100))} %</b>
            <span>Pronosticado {pct(hb.pred)}</span>
            <span>Real {pct(hb.act)}</span>
            <span className="muted">{plural(hb.n, 'partido', 'partidos')}</span>
          </div>
        )}
      </div>
      <details className="table-twin">
        <summary>Ver como tabla</summary>
        <div className="table-wrap">
          <table className="standings">
            <thead><tr><th>Tramo</th><th className="num">Partidos</th><th className="num">Pronosticado</th><th className="num">Real</th></tr></thead>
            <tbody>
              {bins.map((b, i) => (
                <tr key={i}><td>{Math.round(b.lo * 100)}–{Math.min(100, Math.round(b.hi * 100))} %</td><td className="num">{b.n}</td><td className="num">{pct(b.pred)}</td><td className="num">{pct(b.act)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}
