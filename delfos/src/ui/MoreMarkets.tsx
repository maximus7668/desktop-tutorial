import { useEffect, useMemo, useState } from 'react';
import { DOMESTIC_SOCCER } from '../data/leagues';
import { loadSoccerStats, STATS_WINDOW_DAYS } from '../data/source';
import type { LeagueAgg } from '../data/teamStats';
import type { LeagueTable, Match } from '../data/types';
import { fairDecimal } from '../model/odds';
import type { Prediction } from '../model/predict';
import { expectedPossession, goalExtras, propMarkets, type PropLine, type PropMarket, type SideInput } from '../model/props';
import { phi } from '../model/us';
import { useIsDark, useSlip } from '../state';
import { railColors } from './colors';
import { TeamLogo } from './common';
import { dec, odds2, pct } from './format';
import { Icon } from './icons';
import { slipPickForProp } from './slipPick';

const fmt = (x: number) => x.toLocaleString('es-ES');

/** Liga nacional de un equipo (para Champions, Europa League…). */
function leagueOf(teamId: string, m: Match, tables: Record<string, LeagueTable>): string | undefined {
  if (DOMESTIC_SOCCER.includes(m.leagueId)) return m.leagueId;
  return DOMESTIC_SOCCER.find((id) => tables[id]?.current.some((r) => r.teamId === teamId));
}

function useSoccerSides(m: Match, tables: Record<string, LeagueTable>) {
  const [state, setState] = useState<{ home: SideInput; away: SideInput; loading: boolean }>({ home: {}, away: {}, loading: true });
  useEffect(() => {
    let alive = true;
    const lh = leagueOf(m.home.team.id, m, tables);
    const la = leagueOf(m.away.team.id, m, tables);
    Promise.all([lh ? loadSoccerStats(lh) : null, la ? loadSoccerStats(la) : null]).then(([ah, aa]) => {
      if (!alive) return;
      const side = (agg: LeagueAgg | null, id: string): SideInput => (agg ? { league: agg, agg: agg.teams[id] } : {});
      setState({ home: side(ah, m.home.team.id), away: side(aa, m.away.team.id), loading: false });
    });
    return () => {
      alive = false;
    };
  }, [m, tables]);
  return state;
}

type Tab = 'corners' | 'cards' | 'sot' | 'shots' | 'fouls' | 'goals' | 'half';

export function SoccerMoreMarkets({ m, p, tables }: { m: Match; p: Prediction; tables: Record<string, LeagueTable> }) {
  const sides = useSoccerSides(m, tables);
  const share = p.soccer ? p.soccer.lh / (p.soccer.lh + p.soccer.la) : undefined;
  const markets = useMemo(() => propMarkets(m, sides.home, sides.away, share), [m, sides, share]);
  const extras = useMemo(() => (p.soccer ? goalExtras(p.soccer.matrix, p.soccer.lh, p.soccer.la) : undefined), [p]);
  const possession = expectedPossession(sides.home, sides.away);
  const [tab, setTab] = useState<Tab>('corners');
  const tabs: { id: Tab; name: string }[] = [
    ...markets.map((x) => ({ id: x.stat as Tab, name: x.name })),
    { id: 'goals', name: 'Goles' },
    { id: 'half', name: 'Descanso' },
  ];
  const active = tabs.some((t) => t.id === tab) ? tab : 'goals';
  const market = markets.find((x) => x.stat === active);

  return (
    <section className="panel more" aria-labelledby="more-title">
      <h3 className="panel-title" id="more-title">Más mercados</h3>
      {possession !== undefined && <PossessionBar m={m} home={possession} />}
      <nav className="seg" aria-label="Mercado">
        {tabs.map((t) => (
          <button key={t.id} type="button" className={`seg-btn ${active === t.id ? 'is-on' : ''}`} onClick={() => setTab(t.id)} aria-pressed={active === t.id}>
            {t.name}
          </button>
        ))}
      </nav>
      {sides.loading && markets.length === 0 && <p className="muted small">Sumando córners, tarjetas y tiros de la temporada…</p>}
      {!sides.loading && markets.length === 0 && active !== 'goals' && active !== 'half' && (
        <p className="muted small">No hay estadísticas de temporada para estos equipos.</p>
      )}
      {market && <StatMarket m={m} mk={market} />}
      {active === 'goals' && extras && <GoalsTab m={m} p={p} x={extras} />}
      {active === 'half' && extras && <HalfTab m={m} x={extras} />}
      {market && (
        <p className="muted tiny">
          Basado en los partidos de cada equipo en su liga en los últimos {STATS_WINDOW_DAYS} días ({market.games} como mínimo) y en la media de la liga.
          Sin cuotas de referencia: compara con la cuota justa.
        </p>
      )}
    </section>
  );
}

function PossessionBar({ m, home }: { m: Match; home: number }) {
  const dark = useIsDark();
  const c = railColors(m.home.team, m.away.team, dark);
  return (
    <div className="poss">
      <div className="poss-top">
        <span>{m.home.team.short} <b>{Math.round(home)} %</b></span>
        <span className="muted small">Posesión esperada</span>
        <span><b>{Math.round(100 - home)} %</b> {m.away.team.short}</span>
      </div>
      <div className="rail-bar">
        <span className="rail-seg" style={{ flexGrow: home, background: c.home }} />
        <span className="rail-seg" style={{ flexGrow: 100 - home, background: c.away }} />
      </div>
    </div>
  );
}

function AddCell({ m, k, label, prob, strong }: { m: Match; k: string; label: string; prob: number; strong?: boolean }) {
  const slip = useSlip();
  const on = slip.has(m.id, k);
  return (
    <button
      type="button"
      className={`line-cell ${strong ? 'is-strong' : ''} ${on ? 'is-on' : ''}`}
      onClick={() => slip.toggle(slipPickForProp(m, k, label, prob))}
      aria-pressed={on}
      title={on ? 'Quitar de la combinada' : `Añadir «${label}» a la combinada`}
    >
      <b>{pct(prob)}</b>
      <span>{odds2(fairDecimal(prob))}</span>
    </button>
  );
}

function LinesTable({ m, title, lines, keyBase, unit, who }: { m: Match; title: string; lines: PropLine[]; keyBase: string; unit: string; who?: string }) {
  return (
    <div className="lines">
      <div className="lines-head"><span>{title}</span><span>Más de</span><span>Menos de</span></div>
      {lines.map((l) => {
        const suffix = who ? ` de ${who}` : '';
        return (
          <div key={l.line} className="lines-row">
            <span className="lines-line">{fmt(l.line)}</span>
            <AddCell m={m} k={`${keyBase}:over:${l.line}`} label={`Más de ${fmt(l.line)} ${unit}${suffix}`} prob={l.over} strong={l.over >= 0.5} />
            <AddCell m={m} k={`${keyBase}:under:${l.line}`} label={`Menos de ${fmt(l.line)} ${unit}${suffix}`} prob={1 - l.over} strong={l.over < 0.5} />
          </div>
        );
      })}
    </div>
  );
}

function StatMarket({ m, mk }: { m: Match; mk: PropMarket }) {
  const dark = useIsDark();
  const slip = useSlip();
  const c = railColors(m.home.team, m.away.team, dark);
  const pick = mk.pick;
  const pickKey = pick ? `${mk.stat}:${pick.scope}:${pick.side}:${pick.line}` : '';
  return (
    <div className="stat-market">
      <div className="expect">
        <div className="expect-side">
          <TeamLogo team={m.home.team} size={26} />
          <b>{dec(mk.home)}</b>
          <span className="muted small">{m.home.team.short}</span>
        </div>
        <div className="expect-total">
          <span className="eyebrow">{mk.name} esperados</span>
          <b>{dec(mk.total)}</b>
          {mk.actual && <span className="actual">En el partido: {mk.actual.home} – {mk.actual.away}</span>}
        </div>
        <div className="expect-side">
          <TeamLogo team={m.away.team} size={26} />
          <b>{dec(mk.away)}</b>
          <span className="muted small">{m.away.team.short}</span>
        </div>
      </div>

      <div className="more-who">
        <span className="muted small">Quién tendrá más {mk.unit}</span>
        <div className="rail-bar">
          <span className="rail-seg" style={{ flexGrow: mk.more.home, background: c.home }} />
          <span className="rail-seg" style={{ flexGrow: mk.more.draw, background: 'var(--draw)' }} />
          <span className="rail-seg" style={{ flexGrow: mk.more.away, background: c.away }} />
        </div>
        <div className="rail-labels">
          <span className="rail-label" style={{ flexGrow: 1 }}><i className="rail-key" style={{ background: c.home }} />{m.home.team.short} {pct(mk.more.home)}</span>
          <span className="rail-label" style={{ flexGrow: 1 }}><i className="rail-key" style={{ background: 'var(--draw)' }} />Igual {pct(mk.more.draw)}</span>
          <span className="rail-label" style={{ flexGrow: 1 }}><i className="rail-key" style={{ background: c.away }} />{m.away.team.short} {pct(mk.more.away)}</span>
        </div>
      </div>

      {pick && (
        <div className="line-pick">
          <div>
            <span className="eyebrow">Línea Delfos</span>
            <b>{pick.label}</b>
            <span className="muted small">{pct(pick.prob)} · cuota justa {odds2(fairDecimal(pick.prob))} · con valor desde {odds2(1.04 / pick.prob)}</span>
          </div>
          <button type="button" className={`add-btn ${slip.has(m.id, pickKey) ? 'is-on' : ''}`} onClick={() => slip.toggle(slipPickForProp(m, pickKey, pick.label, pick.prob))} aria-pressed={slip.has(m.id, pickKey)}>
            <Icon name={slip.has(m.id, pickKey) ? 'check' : 'plus'} size={15} />
            <span>{slip.has(m.id, pickKey) ? 'En combinada' : 'Combinada'}</span>
          </button>
        </div>
      )}

      <LinesTable m={m} title="Total" lines={mk.totalLines} keyBase={`${mk.stat}:total`} unit={mk.unit} />
      <div className="two-lines">
        <LinesTable m={m} title={m.home.team.short} lines={mk.homeLines} keyBase={`${mk.stat}:home`} unit={mk.unit} who={m.home.team.short} />
        <LinesTable m={m} title={m.away.team.short} lines={mk.awayLines} keyBase={`${mk.stat}:away`} unit={mk.unit} who={m.away.team.short} />
      </div>
    </div>
  );
}

function ProbList({ m, rows }: { m: Match; rows: { k: string; label: string; p: number }[] }) {
  return (
    <div className="prob-list">
      {rows.map((r) => (
        <div key={r.k} className="prob-row">
          <span>{r.label}</span>
          <AddCell m={m} k={r.k} label={r.label} prob={r.p} strong={r.p >= 0.5} />
        </div>
      ))}
    </div>
  );
}

function GoalsTab({ m, p, x }: { m: Match; p: Prediction; x: ReturnType<typeof goalExtras> }) {
  const H = m.home.team.short, A = m.away.team.short;
  const s = p.soccer!;
  return (
    <div className="goal-tabs">
      <div className="two-lines">
        <LinesTable m={m} title={`Goles ${H}`} lines={x.teamGoals.home} keyBase="goals:home" unit="goles" who={H} />
        <LinesTable m={m} title={`Goles ${A}`} lines={x.teamGoals.away} keyBase="goals:away" unit="goles" who={A} />
      </div>
      <ProbList
        m={m}
        rows={[
          { k: 'btts:yes', label: 'Ambos marcan: sí', p: s.pBtts },
          { k: 'btts:no', label: 'Ambos marcan: no', p: 1 - s.pBtts },
          { k: 'cs:home', label: `${H} deja la portería a cero`, p: x.cleanSheet.home },
          { k: 'cs:away', label: `${A} deja la portería a cero`, p: x.cleanSheet.away },
          { k: 'wtn:home', label: `${H} gana sin encajar`, p: x.winToNil.home },
          { k: 'wtn:away', label: `${A} gana sin encajar`, p: x.winToNil.away },
          { k: 'margin:home:1', label: `${H} gana por 1 gol`, p: x.margin.home1 },
          { k: 'margin:home:2', label: `${H} gana por 2 o más`, p: x.margin.home2 },
          { k: 'margin:away:1', label: `${A} gana por 1 gol`, p: x.margin.away1 },
          { k: 'margin:away:2', label: `${A} gana por 2 o más`, p: x.margin.away2 },
        ]}
      />
    </div>
  );
}

const RES: Record<'home' | 'draw' | 'away', string> = { home: '1', draw: 'X', away: '2' };

function HalfTab({ m, x }: { m: Match; x: ReturnType<typeof goalExtras> }) {
  const H = m.home.team.short, A = m.away.team.short;
  return (
    <div className="goal-tabs">
      <ProbList
        m={m}
        rows={[
          { k: 'ht:home', label: `Descanso: gana ${H}`, p: x.half.pHome },
          { k: 'ht:draw', label: 'Descanso: empate', p: x.half.pDraw },
          { k: 'ht:away', label: `Descanso: gana ${A}`, p: x.half.pAway },
          { k: 'ht:over:0.5', label: 'Más de 0,5 goles en la 1.ª parte', p: x.half.over05 },
          { k: 'ht:over:1.5', label: 'Más de 1,5 goles en la 1.ª parte', p: x.half.over15 },
        ]}
      />
      <div className="htft">
        <span className="eyebrow">Descanso / final más probables</span>
        <ProbList
          m={m}
          rows={x.htft.slice(0, 5).map((c) => ({
            k: `htft:${c.ht}:${c.ft}`,
            label: `${RES[c.ht]} / ${RES[c.ft]} · ${c.ht === 'draw' ? 'empate' : `gana ${c.ht === 'home' ? H : A}`} al descanso, ${c.ft === 'draw' ? 'empate' : `gana ${c.ft === 'home' ? H : A}`} al final`,
            p: c.p,
          }))}
        />
      </div>
    </div>
  );
}

/* ------------------------- EE. UU.: líneas alternativas ------------------------- */

export function UsMoreMarkets({ m, p }: { m: Match; p: Prediction }) {
  if (!p.us) return null;
  const { margin, total, sigma, sigmaTotal } = p.us;
  const step = m.sport === 'basketball' ? 4 : m.sport === 'football' ? 3 : 1;
  const unit = m.sport === 'baseball' ? 'carreras' : m.sport === 'hockey' ? 'goles' : 'puntos';
  const round = (x: number) => Math.floor(x) + 0.5;
  const around = (c: number) => [-2, -1, 0, 1, 2].map((k) => round(c) + k * step).filter((l) => l > 0);
  const totalLines = around(m.odds?.total ?? total).map((line) => ({ line, over: phi((total - line) / sigmaTotal) }));
  const eh = total / 2 + margin / 2, ea = total / 2 - margin / 2;
  const sTeam = sigmaTotal * 0.72;
  const homeLines = around(eh).map((line) => ({ line, over: phi((eh - line) / sTeam) }));
  const awayLines = around(ea).map((line) => ({ line, over: phi((ea - line) / sTeam) }));
  const baseSpread = m.odds?.spread ?? -Math.round(margin * 2) / 2;
  const spreads = [-2, -1, 0, 1, 2].map((k) => Math.round((baseSpread + k * (step / 2)) * 2) / 2).filter((l) => l % 1 !== 0);
  return (
    <section className="panel more">
      <h3 className="panel-title">Más mercados</h3>
      <LinesTable m={m} title={`Total (${unit})`} lines={totalLines} keyBase="alt:total" unit={unit} />
      <div className="two-lines">
        <LinesTable m={m} title={m.home.team.short} lines={homeLines} keyBase="tt:home" unit={unit} who={m.home.team.short} />
        <LinesTable m={m} title={m.away.team.short} lines={awayLines} keyBase="tt:away" unit={unit} who={m.away.team.short} />
      </div>
      <ProbList
        m={m}
        rows={spreads.map((l) => ({
          k: `alt:spread:home:${l}`,
          label: `${m.home.team.short} ${l > 0 ? '+' : '−'}${fmt(Math.abs(l))} (hándicap)`,
          p: phi((margin + l) / sigma),
        }))}
      />
      <p className="muted tiny">Líneas alternativas calculadas con el margen y el total esperados de Delfos. Compara con la cuota justa.</p>
    </section>
  );
}
