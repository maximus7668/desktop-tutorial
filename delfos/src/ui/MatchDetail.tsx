import { useEffect, useRef, useState } from 'react';
import { LEAGUE_BY_ID } from '../data/leagues';
import type { LeagueTable, Match, Outcome, TeamStats } from '../data/types';
import { americanToDecimal, fairDecimal } from '../model/odds';
import { actualOutcome, hit, type Prediction } from '../model/predict';
import { useSlip } from '../state';
import { buildPrompt, getSampler } from './ai';
import { ConfidenceBadge, FormChips, HitMark, LeagueLogo, ProbRail, StatusPill, TeamLogo } from './common';
import { dec, longDate, odds2, outcomeCode, outcomeLabel, pct, pickSentence, timeOf } from './format';
import { Icon } from './icons';
import { mlKey, slipPickFor } from './slipPick';
import { BetBox } from './BetBox';
import { SoccerMoreMarkets, UsMoreMarkets } from './MoreMarkets';
import { evaluate, qualifies } from '../model/bets';

interface Props {
  m: Match;
  p: Prediction;
  tables: Record<string, LeagueTable>;
  onClose: () => void;
}

export function MatchDetail({ m, p, tables, onClose }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    ref.current?.focus();
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  const league = LEAGUE_BY_ID[m.leagueId];
  const tennis = m.sport === 'tennis';
  const showScore = m.status !== 'pre' && m.home.score !== undefined;
  const actual = actualOutcome(m);

  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div
        className="sheet"
        role="dialog"
        aria-modal="true"
        aria-label={`${m.home.team.name} contra ${m.away.team.name}`}
        tabIndex={-1}
        ref={ref}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="sheet-head">
          <div className="sheet-league">
            {league && <LeagueLogo league={league} size={22} />}
            <span>{league?.name}{m.round ? ` · ${m.round}` : ''}{m.note && !tennis ? ` · ${m.note}` : ''}{tennis && m.note ? ` · ${m.note}` : ''}</span>
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Cerrar">
            <Icon name="close" />
          </button>
        </header>

        <section className="duel">
          <TeamBlock m={m} side="home" tables={tables} />
          <div className="duel-mid">
            {showScore ? (
              <div className="duel-score">{m.home.score}<span>–</span>{m.away.score}</div>
            ) : (
              <div className="duel-vs">{m.timeTbd ? 'Por confirmar' : timeOf(m.start)}</div>
            )}
            {m.status !== 'pre' && <StatusPill m={m} />}
            <div className="duel-date">{longDate(m.start)}</div>
            {m.series && <div className="duel-series">{m.series}</div>}
          </div>
          <TeamBlock m={m} side="away" tables={tables} />
        </section>

        <div className="duel-meta">
          {m.venue && <span><Icon name="pin" size={15} /> {m.venue}{m.city ? `, ${m.city}` : ''}</span>}
          {m.broadcast && <span><Icon name="tv" size={15} /> {m.broadcast}</span>}
        </div>

        <section className="verdict">
          <div className="verdict-main">
            <span className="eyebrow">Pronóstico Delfos</span>
            <h2 className="verdict-title">{pickSentence(m, p.pick)}</h2>
            <div className="verdict-row">
              <span className="verdict-num">{pct(p.pickProb)}</span>
              <span className="verdict-score">
                <small>Marcador</small>
                {p.score.home}–{p.score.away}
              </span>
              <ConfidenceBadge c={p.confidence} />
            </div>
            {m.status === 'post' && (
              <div className="verdict-result">
                <HitMark ok={hit(m, p)} />
                <span>Resultado: {actual ? (actual === 'draw' ? 'empate' : `ganó ${outcomeLabel(m, actual)}`) : 'sin decidir'}</span>
              </div>
            )}
          </div>
          <ProbRail m={m} p={p} size="lg" />
          {p.doubleChance && (
            <p className="verdict-note">
              Partido abierto: la doble oportunidad <b>{p.doubleChance.label}</b> cubre el {pct(p.doubleChance.p)} de los casos.
            </p>
          )}
        </section>

        {!tennis && <BetBox m={m} p={p} />}

        <PickButtons m={m} p={p} />

        <OddsTable m={m} p={p} />

        {p.soccer && <SoccerMarkets m={m} p={p} />}
        {p.soccer && <SoccerMoreMarkets m={m} p={p} tables={tables} />}
        {!p.threeWay && !tennis && <UsMarkets m={m} p={p} />}
        {!p.threeWay && !tennis && <UsMoreMarkets m={m} p={p} />}
        {p.tennis && <TennisSets m={m} p={p} />}

        <section className="panel">
          <h3 className="panel-title">Por qué</h3>
          <ul className="factors">
            {p.factors.map((f, i) => <li key={i}>{f}</li>)}
          </ul>
          <p className="muted small">Calidad de los datos: {p.quality}. Los pronósticos son probabilidades, no certezas.</p>
        </section>

        <AiPanel m={m} p={p} />

        <p className="sheet-foot">Juega con responsabilidad. Delfos no es una casa de apuestas ni da consejos de apuesta. +18.</p>
      </div>
    </div>
  );
}

function TeamBlock({ m, side, tables }: { m: Match; side: 'home' | 'away'; tables: Record<string, LeagueTable> }) {
  const s = m[side];
  const tennis = m.sport === 'tennis';
  const row: TeamStats | undefined = tables[m.leagueId]?.current.find((r) => r.teamId === s.team.id);
  return (
    <div className={`duel-team ${s.winner ? 'is-winner' : ''}`}>
      <TeamLogo team={s.team} size={64} flag={tennis} />
      <div className="duel-name">{s.team.name}</div>
      <div className="duel-sub">
        {tennis ? (s.rank ? `Ranking n.º ${s.rank}` : 'Sin ranking') : side === 'home' ? (m.neutral ? 'Campo neutral' : 'Local') : 'Visitante'}
        {!tennis && row?.rank ? ` · ${row.rank}.º` : ''}
        {!tennis && s.record ? ` · ${s.record}` : ''}
      </div>
      {s.probable && <div className="duel-sub">{m.sport === 'baseball' ? 'Lanzador' : 'Portero'}: {s.probable}</div>}
      <FormChips form={s.form} />
    </div>
  );
}

function PickButtons({ m, p }: { m: Match; p: Prediction }) {
  const slip = useSlip();
  if (m.status !== 'pre') return null;
  const opts: Outcome[] = p.threeWay ? ['home', 'draw', 'away'] : ['home', 'away'];
  return (
    <section className="pick-buttons" aria-label="Añadir a la combinada">
      {opts.map((o) => {
        const pr = o === 'home' ? p.pHome : o === 'draw' ? p.pDraw : p.pAway;
        const on = slip.has(m.id, mlKey(o));
        return (
          <button key={o} type="button" className={`pick-btn ${on ? 'is-on' : ''} ${p.pick === o ? 'is-pick' : ''}`} onClick={() => slip.toggle(slipPickFor(m, p, o))} aria-pressed={on}>
            <span className="pick-btn-top">
              <span className="pick-btn-code">{outcomeCode(o, p.threeWay)}</span>
              <Icon name={on ? 'check' : 'plus'} size={15} />
            </span>
            <span className="pick-btn-label">{outcomeLabel(m, o)}</span>
            <span className="pick-btn-odds">{pct(pr)}</span>
          </button>
        );
      })}
    </section>
  );
}

function OddsTable({ m, p }: { m: Match; p: Prediction }) {
  const cols: Outcome[] = p.threeWay ? ['home', 'draw', 'away'] : ['home', 'away'];
  const get = (src: { pHome: number; pDraw: number; pAway: number } | undefined, o: Outcome) =>
    src ? (o === 'home' ? src.pHome : o === 'draw' ? src.pDraw : src.pAway) : undefined;
  const mk = (o: Outcome) => {
    const a = m.odds ? (o === 'home' ? m.odds.home : o === 'draw' ? m.odds.draw : m.odds.away) : undefined;
    return a !== undefined ? americanToDecimal(a) : undefined;
  };
  return (
    <section className="panel">
      <h3 className="panel-title">Delfos frente al mercado</h3>
      <div className="table-wrap">
        <table className="cmp">
          <thead>
            <tr>
              <th />
              {cols.map((o) => <th key={o}>{outcomeCode(o, p.threeWay)} <span className="muted">{outcomeLabel(m, o)}</span></th>)}
            </tr>
          </thead>
          <tbody>
            <tr className="is-strong">
              <th>Delfos</th>
              {cols.map((o) => <td key={o}>{pct(get(p, o)!)}</td>)}
            </tr>
            <tr>
              <th>Modelo estadístico</th>
              {cols.map((o) => <td key={o}>{pct(get(p.model, o)!)}</td>)}
            </tr>
            <tr>
              <th>Mercado{p.market ? ` (${p.market.provider})` : ''}</th>
              {cols.map((o) => <td key={o}>{p.market ? pct(get(p.market, o)!) : '—'}</td>)}
            </tr>
            <tr>
              <th>Cuota justa</th>
              {cols.map((o) => <td key={o}>{odds2(fairDecimal(get(p, o)!))}</td>)}
            </tr>
            <tr>
              <th>Cuota mercado</th>
              {cols.map((o) => {
                const d = mk(o);
                const b = d ? evaluate({ key: `ml:${o}`, market: '', label: '', prob: get(p, o)!, push: 0, odds: d }) : undefined;
                const val = !!b && m.status === 'pre' && qualifies(b);
                return <td key={o} className={val ? 'is-value' : ''}>{d ? odds2(d) : '—'}{val && <small> +{Math.round(b!.ev * 100)} %</small>}</td>;
              })}
            </tr>
          </tbody>
        </table>
      </div>
      <p className="muted small">
        Cuota justa = 1 / probabilidad. Si la cuota del mercado es mayor, hay <b>valor</b>: el precio paga más de lo que el riesgo merece según Delfos.
      </p>
    </section>
  );
}

function SoccerMarkets({ m, p }: { m: Match; p: Prediction }) {
  const s = p.soccer!;
  const N = 6;
  const max = Math.max(...s.matrix.slice(0, N).flatMap((r) => r.slice(0, N)));
  const [hover, setHover] = useState<{ h: number; a: number } | null>(null);
  const cell = hover ? s.matrix[hover.h][hover.a] : s.best.p;
  const shown = hover ?? s.best;
  return (
    <section className="panel">
      <h3 className="panel-title">Goles</h3>
      <div className="markets">
        <Meter label="Más de 2,5 goles" p={s.pOver25} />
        <Meter label="Ambos marcan" p={s.pBtts} />
        <Meter label="Más de 1,5 goles" p={s.pOver15} />
        <Meter label="Más de 3,5 goles" p={s.pOver35} />
      </div>
      <div className="xg">
        <span>Goles esperados</span>
        <b>{dec(s.xgHome, 2)}</b>
        <i>–</i>
        <b>{dec(s.xgAway, 2)}</b>
      </div>
      <div className="heat-wrap">
        <div className="heat" role="grid" aria-label="Probabilidad de cada marcador">
          <div className="heat-corner" aria-hidden="true">
            <span>{m.away.team.abbr} →</span>
            <span>{m.home.team.abbr} ↓</span>
          </div>
          {Array.from({ length: N }, (_, a) => <div key={`c${a}`} className="heat-axis">{a}</div>)}
          {Array.from({ length: N }, (_, h) => (
            <div key={`r${h}`} className="heat-row" role="row">
              <div className="heat-axis">{h}</div>
              {Array.from({ length: N }, (_, a) => {
                const v = s.matrix[h][a];
                const t = Math.pow(v / max, 0.8);
                const best = s.best.h === h && s.best.a === a;
                return (
                  <button
                    key={a}
                    type="button"
                    role="gridcell"
                    className={`heat-cell ${t > 0.62 ? 'on-dark' : ''} ${best ? 'is-best' : ''} ${hover?.h === h && hover?.a === a ? 'is-hover' : ''}`}
                    style={{ ['--t' as string]: t.toFixed(3) }}
                    onMouseEnter={() => setHover({ h, a })}
                    onFocus={() => setHover({ h, a })}
                    onMouseLeave={() => setHover(null)}
                    onBlur={() => setHover(null)}
                    aria-label={`${h}-${a}: ${pct(v, 1)}`}
                  >
                    {v >= 0.07 ? Math.round(v * 100) : ''}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
        <div className="heat-read">
          <span className="eyebrow">{hover ? 'Marcador' : 'Más probable'}</span>
          <b>{shown.h}–{shown.a}</b>
          <span>{pct(cell, 1)}</span>
          <ol className="top-scores">
            {s.top.map((c) => (
              <li key={`${c.h}-${c.a}`}><span>{c.h}–{c.a}</span><span>{pct(c.p, 1)}</span></li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}

function UsMarkets({ m, p }: { m: Match; p: Prediction }) {
  const unit = m.sport === 'baseball' ? 'carreras' : m.sport === 'hockey' ? 'goles' : 'puntos';
  return (
    <section className="panel">
      <h3 className="panel-title">Marcador y líneas</h3>
      <div className="markets">
        {p.totals && <Meter label={`Más de ${p.totals.line.toLocaleString('es-ES')} ${unit}`} p={p.totals.pOver} />}
        {p.spread && <Meter label={`${m.home.team.abbr} cubre ${p.spread.line > 0 ? '+' : ''}${p.spread.line.toLocaleString('es-ES')}`} p={p.spread.pCover} />}
      </div>
      {p.expected && (
        <div className="xg">
          <span>{unit.charAt(0).toUpperCase() + unit.slice(1)} esperados</span>
          <b>{dec(p.expected.home)}</b>
          <i>–</i>
          <b>{dec(p.expected.away)}</b>
        </div>
      )}
    </section>
  );
}

function TennisSets({ m, p }: { m: Match; p: Prediction }) {
  const t = p.tennis!;
  const max = Math.max(...t.sets.map((s) => s.p));
  return (
    <section className="panel">
      <h3 className="panel-title">Marcador en sets</h3>
      <div className="bars">
        {t.sets.map((s) => (
          <div key={`${s.a}-${s.b}`} className="bar-row">
            <span className="bar-label">{s.a}–{s.b} <span className="muted">{s.a > s.b ? m.home.team.short : m.away.team.short}</span></span>
            <span className="bar-track"><span className="bar-fill" style={{ width: `${(s.p / max) * 100}%` }} /></span>
            <span className="bar-value">{pct(s.p)}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function Meter({ label, p }: { label: string; p: number }) {
  return (
    <div className="meter">
      <div className="meter-top">
        <span>{label}</span>
        <b>{pct(p)}</b>
      </div>
      <div className="meter-track"><span style={{ width: `${Math.round(p * 100)}%` }} /></div>
    </div>
  );
}

function AiPanel({ m, p }: { m: Match; p: Prediction }) {
  const [available, setAvailable] = useState(false);
  const [text, setText] = useState('');
  const [state, setState] = useState<'idle' | 'loading' | 'done' | 'error'>('idle');
  const [err, setErr] = useState('');
  useEffect(() => {
    let alive = true;
    getSampler().then((s) => alive && setAvailable(!!s));
    return () => {
      alive = false;
    };
  }, []);
  if (!available) return null;
  const run = async () => {
    const s = await getSampler();
    if (!s) return;
    setState('loading');
    setText('');
    try {
      const res = await s(buildPrompt(m, p), { modelTier: 'quick', cache: true, onText: (u) => setText(u.text) });
      setText(res.text);
      setState('done');
    } catch (e) {
      const code = (e as { code?: string })?.code;
      if (code === 'not_granted') {
        setAvailable(false);
        return;
      }
      setErr(code === 'rate_limited' ? 'Demasiadas consultas seguidas. Prueba de nuevo en un minuto.' : 'No se pudo generar el análisis. Inténtalo otra vez.');
      setState('error');
    }
  };
  return (
    <section className="panel ai">
      <div className="ai-head">
        <h3 className="panel-title"><Icon name="wand" size={18} /> Análisis del Oráculo</h3>
        {state !== 'loading' && (
          <button type="button" className="btn btn-ghost" onClick={run}>
            {state === 'idle' ? 'Generar análisis' : 'Volver a generar'}
          </button>
        )}
      </div>
      {state === 'idle' && <p className="muted small">Claude redacta una previa a partir de los números de esta ficha.</p>}
      {state === 'loading' && !text && <p className="muted small ai-wait">Pensando…</p>}
      {text && <div className="ai-text">{text.split(/\n{2,}/).map((t, i) => <p key={i}>{t}</p>)}</div>}
      {state === 'error' && <p className="error-text">{err}</p>}
    </section>
  );
}
