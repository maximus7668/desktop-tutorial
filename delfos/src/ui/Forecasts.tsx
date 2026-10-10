import { useMemo, useState } from 'react';
import { LEAGUE_BY_ID, SPORTS } from '../data/leagues';
import { addDays, dayKey, MODE, snapshotDays } from '../data/source';
import type { Match, SportId } from '../data/types';
import { predict, type Prediction } from '../model/predict';
import type { DayState } from '../state';
import { useSlip } from '../state';
import { ConfidenceBadge, Empty, LeagueLogo, ProbRail, StatusPill, TeamLogo } from './common';
import { dayLabel, outcomeLabel, pct, pickSentence, plural } from './format';
import { Icon, SportIcon } from './icons';
import { MatchCard } from './MatchCard';
import { slipPickFor } from './slipPick';
import { F1View } from './F1View';

export type SportFilter = SportId | 'all';

interface Props {
  day: string;
  setDay: (k: string) => void;
  sport: SportFilter;
  setSport: (s: SportFilter) => void;
  data: DayState;
  onOpen: (id: string) => void;
  onReload: () => void;
}

export interface Scored {
  m: Match;
  p: Prediction;
}

export function useScored(data: DayState): Scored[] {
  return useMemo(() => {
    const ctx = { tables: data.tables };
    return data.matches
      .map((m) => {
        try {
          return { m, p: predict(m, ctx) };
        } catch {
          return null;
        }
      })
      .filter((x): x is Scored => !!x)
      .sort((a, b) => a.m.start.localeCompare(b.m.start));
  }, [data.matches, data.tables]);
}

export function dayRange(): string[] {
  const today = dayKey(new Date());
  const snap = snapshotDays();
  const all = Array.from({ length: 10 }, (_, i) => addDays(today, i - 3));
  if (!snap) return all;
  const inSnap = all.filter((k) => snap.includes(k));
  return inSnap.length ? inSnap : snap.slice(-7);
}

export function DateStrip({ day, setDay }: { day: string; setDay: (k: string) => void }) {
  const days = dayRange();
  return (
    <nav className="dates" aria-label="Elegir día">
      {days.map((k) => {
        const l = dayLabel(k);
        return (
          <button key={k} type="button" className={`date ${k === day ? 'is-on' : ''}`} onClick={() => setDay(k)} aria-pressed={k === day}>
            <span className="date-top">{l.top}</span>
            <span className="date-bottom">{l.bottom}</span>
          </button>
        );
      })}
    </nav>
  );
}

export function SportBar({ sport, setSport, counts }: { sport: SportFilter; setSport: (s: SportFilter) => void; counts: Record<string, number> }) {
  const items: { id: SportFilter; name: string }[] = [{ id: 'all', name: 'Todo' }, ...SPORTS.map((s) => ({ id: s.id, name: s.short }))];
  return (
    <nav className="sports" aria-label="Deportes">
      {items.map((s) => {
        const n = s.id === 'all' ? Object.values(counts).reduce((a, b) => a + b, 0) : counts[s.id] ?? 0;
        return (
          <button key={s.id} type="button" className={`sport ${sport === s.id ? 'is-on' : ''}`} onClick={() => setSport(s.id)} aria-pressed={sport === s.id}>
            <SportIcon sport={s.id} size={18} />
            <span>{s.name}</span>
            {s.id !== 'racing' && <small>{n}</small>}
          </button>
        );
      })}
    </nav>
  );
}

type Sort = 'hora' | 'confianza';

export function Forecasts({ day, setDay, sport, setSport, data, onOpen, onReload }: Props) {
  const scored = useScored(data);
  const [league, setLeague] = useState<string>('all');
  const [onlyValue, setOnlyValue] = useState(false);
  const [onlyHigh, setOnlyHigh] = useState(false);
  const [sort, setSort] = useState<Sort>('hora');

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const s of scored) c[s.m.sport] = (c[s.m.sport] ?? 0) + 1;
    return c;
  }, [scored]);

  const bySport = scored.filter((s) => sport === 'all' || s.m.sport === sport);
  const leagues = [...new Set(bySport.map((s) => s.m.leagueId))].sort((a, b) => (LEAGUE_BY_ID[a]?.order ?? 99) - (LEAGUE_BY_ID[b]?.order ?? 99));
  const activeLeague = leagues.includes(league) ? league : 'all';
  let list = bySport.filter((s) => activeLeague === 'all' || s.m.leagueId === activeLeague);
  if (onlyValue) list = list.filter((s) => s.p.value && s.m.status === 'pre');
  if (onlyHigh) list = list.filter((s) => s.p.confidence === 'alta');

  const groups = useMemo(() => {
    const g = new Map<string, Scored[]>();
    for (const s of list) {
      const key = s.m.sport === 'tennis' ? `${s.m.leagueId}|${s.m.note ?? ''}` : s.m.leagueId;
      if (!g.has(key)) g.set(key, []);
      g.get(key)!.push(s);
    }
    const arr = [...g.entries()].sort((a, b) => (LEAGUE_BY_ID[a[0].split('|')[0]]?.order ?? 99) - (LEAGUE_BY_ID[b[0].split('|')[0]]?.order ?? 99));
    if (sort === 'confianza') for (const [, v] of arr) v.sort((a, b) => b.p.pickProb - a.p.pickProb);
    return arr;
  }, [list, sort]);

  return (
    <div className="view">
      <DateStrip day={day} setDay={setDay} />
      <SportBar sport={sport} setSport={setSport} counts={counts} />

      {sport === 'racing' ? (
        <F1View />
      ) : (
        <>
          {data.failed.length > 0 && (
            <div className="notice">
              No se pudieron cargar: {data.failed.join(', ')}.
              <button type="button" className="btn btn-ghost" onClick={onReload}><Icon name="refresh" size={15} /> Reintentar</button>
            </div>
          )}
          {data.error && (
            <div className="notice notice-error">
              No hay conexión con la fuente de datos ({data.error}).
              <button type="button" className="btn btn-ghost" onClick={onReload}><Icon name="refresh" size={15} /> Reintentar</button>
            </div>
          )}

          <Featured scored={bySport} onOpen={onOpen} />

          {leagues.length > 1 && (
            <nav className="leagues" aria-label="Competiciones">
              <button type="button" className={`league-chip ${activeLeague === 'all' ? 'is-on' : ''}`} onClick={() => setLeague('all')}>Todas</button>
              {leagues.map((id) => {
                const l = LEAGUE_BY_ID[id];
                if (!l) return null;
                return (
                  <button key={id} type="button" className={`league-chip ${activeLeague === id ? 'is-on' : ''}`} onClick={() => setLeague(id)}>
                    <LeagueLogo league={l} size={18} />
                    {l.short}
                  </button>
                );
              })}
            </nav>
          )}

          <div className="toolbar">
            <span className="toolbar-count">{data.loading ? 'Cargando…' : plural(list.length, 'partido', 'partidos')}</span>
            <div className="toolbar-actions">
              <button type="button" className={`toggle ${onlyHigh ? 'is-on' : ''}`} onClick={() => setOnlyHigh((v) => !v)} aria-pressed={onlyHigh}>Confianza alta</button>
              <button type="button" className={`toggle ${onlyValue ? 'is-on' : ''}`} onClick={() => setOnlyValue((v) => !v)} aria-pressed={onlyValue}><Icon name="spark" size={14} /> Con valor</button>
              <label className="select">
                <span className="sr-only">Ordenar</span>
                <select id="orden" value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
                  <option value="hora">Por hora</option>
                  <option value="confianza">Por confianza</option>
                </select>
              </label>
            </div>
          </div>

          {data.loading && scored.length === 0 ? (
            <div className="skeleton-list" aria-hidden="true">
              {Array.from({ length: 4 }, (_, i) => <div key={i} className="skeleton" />)}
            </div>
          ) : groups.length === 0 ? (
            <Empty title="Sin partidos con estos filtros">
              {onlyValue || onlyHigh ? 'Quita algún filtro o cambia de día.' : 'Prueba otro día u otro deporte.'}
            </Empty>
          ) : (
            groups.map(([key, items]) => {
              const [lid, tour] = key.split('|');
              const l = LEAGUE_BY_ID[lid];
              return (
                <section key={key} className="group">
                  <header className="group-head">
                    {l && (l.logo ? <LeagueLogo league={l} size={24} /> : <span className="tour-badge">{l.short}</span>)}
                    <h2>{tour || l?.name}</h2>
                    <span className="group-sub">{tour ? l?.name : l?.region}</span>
                    <span className="group-n">{items.length}</span>
                  </header>
                  <div className="group-list">
                    {items.map((s) => <MatchCard key={s.m.id} m={s.m} p={s.p} onOpen={onOpen} />)}
                  </div>
                </section>
              );
            })
          )}
          {MODE === 'snapshot' && <p className="muted small center">Datos de una instantánea. La versión web se actualiza sola cada minuto.</p>}
        </>
      )}
    </div>
  );
}

/** Los pronósticos más sólidos del día, sin repetir competición. */
export function featuredPicks(scored: Scored[], n = 3): Scored[] {
  const pre = scored.filter((s) => s.m.status === 'pre' && s.p.quality !== 'escasa' && s.m.seasonType !== 1);
  const sorted = pre.sort((a, b) => b.p.pickProb + (b.p.market ? 0.03 : 0) - (a.p.pickProb + (a.p.market ? 0.03 : 0)));
  const out: Scored[] = [];
  const used = new Set<string>();
  for (const s of sorted) {
    if (used.has(s.m.leagueId)) continue;
    out.push(s);
    used.add(s.m.leagueId);
    if (out.length === n) break;
  }
  return out;
}

function Featured({ scored, onOpen }: { scored: Scored[]; onOpen: (id: string) => void }) {
  const slip = useSlip();
  const picks = featuredPicks(scored);
  if (picks.length === 0) return null;
  const combo = picks.reduce((s, x) => s * x.p.pickProb, 1);
  const allIn = picks.every((x) => slip.has(x.m.id, x.p.pick));
  return (
    <section className="oracle" aria-labelledby="oracle-title">
      <div className="oracle-head">
        <div>
          <span className="eyebrow">El Oráculo del día</span>
          <h2 id="oracle-title">Los pronósticos más sólidos</h2>
        </div>
        <button
          type="button"
          className={`btn ${allIn ? 'btn-ghost' : 'btn-gold'}`}
          onClick={() => {
            if (allIn) picks.forEach((x) => slip.remove(x.m.id));
            else picks.forEach((x) => !slip.has(x.m.id, x.p.pick) && slip.toggle(slipPickFor(x.m, x.p, x.p.pick)));
          }}
        >
          {allIn ? 'Quitar de la combinada' : `Combinar los ${picks.length} · ${pct(combo)}`}
        </button>
      </div>
      <div className="oracle-cards">
        {picks.map(({ m, p }) => {
          const l = LEAGUE_BY_ID[m.leagueId];
          const pickSide = p.pick === 'home' ? m.home : p.pick === 'away' ? m.away : undefined;
          return (
            <button key={m.id} type="button" className="oracle-card" onClick={() => onOpen(m.id)}>
              <span className="oracle-league">
                {l && (l.logo ? <LeagueLogo league={l} size={18} /> : <span className="tour-badge sm">{l.short}</span>)}
                {l?.short}
                <StatusPill m={m} />
              </span>
              <span className="oracle-teams">
                <TeamLogo team={m.home.team} size={40} flag={m.sport === 'tennis'} />
                <span className="oracle-vs">vs</span>
                <TeamLogo team={m.away.team} size={40} flag={m.sport === 'tennis'} />
              </span>
              <span className="oracle-names">{m.home.team.short} – {m.away.team.short}</span>
              <span className="oracle-pick">
                {pickSide && <TeamLogo team={pickSide.team} size={20} flag={m.sport === 'tennis'} />}
                {pickSentence(m, p.pick)}
              </span>
              <span className="oracle-num">{pct(p.pickProb)}</span>
              <ProbRail m={m} p={p} labels={false} />
              <span className="oracle-foot">
                <ConfidenceBadge c={p.confidence} short />
                <span className="muted">{p.value ? `Valor en ${outcomeLabel(m, p.value.outcome)}` : `Marcador ${p.score.home}–${p.score.away}`}</span>
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
