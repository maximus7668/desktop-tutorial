// Normalizador de las respuestas públicas de ESPN (site.api.espn.com).
// Lo usan tanto la app en directo como el script que genera la instantánea.
import type {
  Constructor, Driver, F1Data, League, LeagueTable, Match, MatchStats, Odds, Race, RaceSession, RankEntry, Side, Status, TeamStats,
} from './types';
import { esName } from './names';

/* eslint-disable @typescript-eslint/no-explicit-any */
type Json = any;

export const ESPN_SITE = 'https://site.api.espn.com/apis/site/v2/sports';
export const ESPN_V2 = 'https://site.api.espn.com/apis/v2/sports';

export const scoreboardUrl = (slug: string, espnDay?: string) =>
  `${ESPN_SITE}/${slug}/scoreboard${espnDay ? `?dates=${espnDay}&limit=200` : ''}`;
export const standingsUrl = (slug: string, season?: number) =>
  `${ESPN_V2}/${slug}/standings${season ? `?season=${season}` : ''}`;
export const rankingsUrl = (slug: string) => `${ESPN_SITE}/${slug}/rankings`;

const num = (v: unknown): number | undefined => {
  if (v === null || v === undefined || v === '') return undefined;
  const n = typeof v === 'number' ? v : parseFloat(String(v));
  return Number.isFinite(n) ? n : undefined;
};

/** "+190" | "-395" | "EVEN" -> cuota americana */
export function parseAmerican(v: unknown): number | undefined {
  if (v === null || v === undefined) return undefined;
  const s = String(v).trim().toUpperCase();
  if (s === 'EVEN' || s === 'EV') return 100;
  const n = num(s.replace('+', ''));
  if (n === undefined || Math.abs(n) < 100) return undefined;
  return n;
}

const color = (c?: string) => (c && /^[0-9a-f]{6}$/i.test(c) ? `#${c}` : undefined);

export function parseOdds(c: Json): Odds | undefined {
  const o = (c.odds || [])[0];
  if (!o) return undefined;
  const ml = o.moneyline || {};
  const pick = (side: Json) => parseAmerican(side?.close?.odds ?? side?.open?.odds);
  const odds: Odds = {
    provider: o.provider?.name || 'Mercado',
    home: pick(ml.home) ?? parseAmerican(o.homeTeamOdds?.moneyLine),
    away: pick(ml.away) ?? parseAmerican(o.awayTeamOdds?.moneyLine),
    draw: pick(ml.draw) ?? parseAmerican(o.drawOdds?.moneyLine),
    spread: num(o.spread),
    total: num(o.overUnder),
    over: parseAmerican(o.total?.over?.close?.odds ?? o.overOdds),
    under: parseAmerican(o.total?.under?.close?.odds ?? o.underOdds),
    spreadHomeLine: num(o.pointSpread?.home?.close?.line ?? o.pointSpread?.home?.open?.line),
    spreadHomeOdds: parseAmerican(o.pointSpread?.home?.close?.odds ?? o.pointSpread?.home?.open?.odds),
    spreadAwayLine: num(o.pointSpread?.away?.close?.line ?? o.pointSpread?.away?.open?.line),
    spreadAwayOdds: parseAmerican(o.pointSpread?.away?.close?.odds ?? o.pointSpread?.away?.open?.odds),
  };
  if (odds.home === undefined && odds.away === undefined && odds.total === undefined) return undefined;
  return odds;
}

function parseStatus(st: Json): { status: Status; detail: string; completed: boolean; clock?: string; period?: number } {
  const t = st?.type || {};
  const state: Status = t.state === 'in' ? 'in' : t.state === 'post' ? 'post' : 'pre';
  return {
    status: state,
    detail: t.shortDetail || t.detail || '',
    completed: !!t.completed,
    clock: st?.displayClock,
    period: num(st?.period),
  };
}

const SOCCER_STATS: Record<string, keyof MatchStats> = {
  wonCorners: 'corners', shotsOnTarget: 'sot', totalShots: 'shots', foulsCommitted: 'fouls', possessionPct: 'possession',
};

function parseMatchStats(t: Json, details: Json[] | undefined): MatchStats | undefined {
  const st: MatchStats = {};
  let any = false;
  for (const s of t.statistics || []) {
    const k = SOCCER_STATS[s.name];
    const v = num(s.value ?? s.displayValue);
    if (k && v !== undefined) {
      st[k] = v;
      any = true;
    }
  }
  if (!any) return undefined;
  if (Array.isArray(details)) {
    const id = String(t.team?.id ?? t.id);
    st.yellow = details.filter((d: Json) => d.yellowCard && String(d.team?.id) === id).length;
    st.red = details.filter((d: Json) => d.redCard && String(d.team?.id) === id).length;
  }
  return st;
}

function parseSide(t: Json, sport: string): Side {
  const team = t.team || {};
  const records: Json[] = t.records || [];
  const total = records.find((r) => r.type === 'total' || r.name === 'overall' || r.name === 'All Splits');
  const probable = (t.probables || [])[0]?.athlete?.displayName;
  return {
    team: {
      id: String(team.id ?? t.id),
      name: esName(team.displayName || team.name || 'Por definir'),
      short: esName(team.shortDisplayName || team.name || team.displayName || ''),
      abbr: team.abbreviation || (team.shortDisplayName || '').slice(0, 3).toUpperCase(),
      logo: team.logo || team.logos?.[0]?.href,
      color: color(team.color),
      alt: color(team.alternateColor),
    },
    score: num(t.score),
    winner: t.winner === true ? true : undefined,
    form: typeof t.form === 'string' && t.form ? t.form : undefined,
    record: sport === 'soccer' ? undefined : total?.summary,
    probable,
    linescores: Array.isArray(t.linescores) ? t.linescores.map((l: Json) => num(l.value) ?? 0) : undefined,
  };
}

function withStats(side: Side, t: Json, c: Json, sport: string): Side {
  if (sport !== 'soccer') return side;
  const stats = parseMatchStats(t, c.details);
  return stats ? { ...side, stats } : side;
}

export function parseScoreboard(league: League, json: Json): Match[] {
  const out: Match[] = [];
  for (const e of json?.events || []) {
    const c = e.competitions?.[0];
    if (!c) continue;
    const comps: Json[] = c.competitors || [];
    const h = comps.find((x) => x.homeAway === 'home') || comps[0];
    const a = comps.find((x) => x.homeAway === 'away') || comps[1];
    if (!h || !a) continue;
    const st = parseStatus(c.status || e.status);
    const note = (c.notes || []).map((n: Json) => n.headline || n.text).filter(Boolean)[0];
    out.push({
      id: String(e.id),
      leagueId: league.id,
      sport: league.sport,
      start: c.date || e.date,
      timeTbd: c.timeValid === false ? true : undefined,
      status: st.status,
      statusDetail: st.detail,
      completed: st.completed,
      clock: st.clock,
      period: st.period,
      home: withStats(parseSide(h, league.sport), h, c, league.sport),
      away: withStats(parseSide(a, league.sport), a, c, league.sport),
      neutral: !!c.neutralSite,
      venue: c.venue?.fullName,
      city: c.venue?.address?.city,
      note,
      series: c.series?.summary,
      broadcast: (c.broadcasts || []).flatMap((b: Json) => b.names || [])[0],
      odds: parseOdds(c),
      seasonType: num(e.season?.type),
    });
  }
  return out;
}

const ROUNDS: Record<string, string> = {
  'Round 1': '1.ª ronda',
  'Round 2': '2.ª ronda',
  'Round 3': '3.ª ronda',
  'Round 4': 'Octavos de final',
  'Round of 16': 'Octavos de final',
  Quarterfinal: 'Cuartos de final',
  Semifinal: 'Semifinal',
  Final: 'Final',
};

export function parseTennis(league: League, json: Json, ranks: RankEntry[]): Match[] {
  const byId = new Map(ranks.map((r) => [r.id, r]));
  const out: Match[] = [];
  for (const e of json?.events || []) {
    for (const g of e.groupings || []) {
      // El marcador de la ATP incluye también los cuadros femeninos de torneos mixtos (y al revés).
      const label = g.grouping?.displayName || '';
      if (label !== (league.id === 'wta' ? "Women's Singles" : "Men's Singles")) continue;
      for (const c of g.competitions || []) {
        const round = c.round?.displayName || '';
        if (/Qualif/i.test(round)) continue;
        const comps: Json[] = c.competitors || [];
        if (comps.length !== 2) continue;
        const sides = comps
          .slice()
          .sort((x, y) => (x.order ?? 0) - (y.order ?? 0))
          .map((t): Side => {
            const ath = t.athlete || {};
            const r = byId.get(String(t.id));
            return {
              team: {
                id: String(t.id),
                name: ath.displayName || 'Por definir',
                short: ath.shortName || ath.displayName || '',
                abbr: (ath.shortName || ath.displayName || '').replace(/^.*\.\s*/, '').slice(0, 3).toUpperCase(),
                logo: ath.flag?.href,
              },
              winner: t.winner === true ? true : undefined,
              rank: r?.rank ?? num(t.curatedRank?.current),
              rankPoints: r?.points,
              linescores: Array.isArray(t.linescores) ? t.linescores.map((l: Json) => num(l.value) ?? 0) : undefined,
              score: Array.isArray(t.linescores) ? t.linescores.filter((l: Json) => l.winner).length : undefined,
            };
          });
        if (sides.some((s) => !s.team.name || s.team.name === 'TBD' || s.team.name === 'Por definir')) continue;
        const st = parseStatus(c.status);
        out.push({
          id: `${league.id}-${c.id}`,
          leagueId: league.id,
          sport: 'tennis',
          start: c.date,
          timeTbd: c.timeValid === false ? true : undefined,
          status: st.status,
          statusDetail: st.detail,
          completed: st.completed,
          home: sides[0],
          away: sides[1],
          neutral: true,
          venue: c.venue?.court,
          city: c.venue?.fullName,
          note: e.name,
          round: ROUNDS[round] || round,
        });
      }
    }
  }
  return out;
}

function statMap(stats: Json[]): Record<string, { v?: number; d?: string }> {
  const m: Record<string, { v?: number; d?: string }> = {};
  for (const s of stats || []) m[s.name || s.type] = { v: num(s.value), d: s.displayValue };
  return m;
}

export function parseStandings(json: Json): TeamStats[] {
  const out: TeamStats[] = [];
  const walk = (node: Json) => {
    const entries = node?.standings?.entries;
    if (Array.isArray(entries)) {
      for (const e of entries) {
        if (!e.team) continue;
        const s = statMap(e.stats);
        const w = s.wins?.v ?? 0;
        const l = s.losses?.v ?? 0;
        const d = s.ties?.v ?? 0;
        const otl = s.otLosses?.v ?? 0;
        out.push({
          teamId: String(e.team.id),
          name: esName(e.team.displayName || e.team.name),
          abbr: e.team.abbreviation || '',
          logo: e.team.logos?.[0]?.href,
          gp: s.gamesPlayed?.v ?? w + l + d + otl,
          w, d, l, otl,
          gf: s.pointsFor?.v ?? 0,
          ga: s.pointsAgainst?.v ?? 0,
          pts: s.points?.v,
          rank: s.rank?.v ?? s.playoffSeed?.v,
          group: node.name,
          streak: s.streak?.d,
          homeRecord: s.Home?.d ?? s.home?.d,
          awayRecord: s.Road?.d ?? s.road?.d ?? s.Away?.d,
        });
      }
    }
    for (const c of node?.children || []) walk(c);
  };
  walk(json);
  return out;
}

export function emptyTable(leagueId: string): LeagueTable {
  return { leagueId, season: '', current: [], previous: [] };
}

export function seasonName(json: Json): string {
  let name = '';
  const walk = (n: Json) => {
    if (name) return;
    if (n?.standings?.seasonDisplayName) name = n.standings.seasonDisplayName;
    for (const c of n?.children || []) walk(c);
  };
  walk(json);
  return name;
}

/** Días de partido ya pasados según el calendario de la liga (AAAAMMDD), los más recientes primero. */
export function pastCalendarDays(json: Json, now: Date, maxDays: number): string[] {
  const lg = json?.leagues?.[0];
  const raw: Json[] = lg?.calendar || [];
  const dates: string[] = [];
  for (const c of raw) {
    if (typeof c === 'string') dates.push(c);
    else if (c?.entries) for (const e of c.entries) if (e?.startDate) dates.push(e.startDate);
  }
  const lo = new Date(now.getTime() - maxDays * 86400_000).toISOString();
  const hi = now.toISOString();
  const days = new Set<string>();
  for (const d of dates) {
    if (d >= lo && d <= hi) days.add(d.slice(0, 10).replace(/-/g, ''));
  }
  return [...days].sort().reverse();
}

export function scoreboardSeasonYear(json: Json): number | undefined {
  return num(json?.leagues?.[0]?.season?.year);
}

export function parseRankings(json: Json): RankEntry[] {
  const rk = json?.rankings?.[0];
  return (rk?.ranks || []).map((r: Json) => ({
    id: String(r.athlete?.id),
    name: r.athlete?.displayName,
    rank: num(r.current) ?? 999,
    points: num(r.points) ?? 0,
  }));
}

export function parseF1(scoreboard: Json, standings: Json): F1Data {
  const ev = (scoreboard?.events || [])[0];
  let race: Race | undefined;
  if (ev) {
    const sessions: RaceSession[] = (ev.competitions || []).map((c: Json) => ({
      type: c.type?.abbreviation || '',
      date: c.date,
      status: parseStatus(c.status).status,
      order: (c.competitors || [])
        .slice()
        .sort((x: Json, y: Json) => (x.order ?? 99) - (y.order ?? 99))
        .map((x: Json) => String(x.id)),
    }));
    race = {
      id: String(ev.id),
      name: ev.name,
      short: ev.shortName,
      start: ev.date,
      end: ev.endDate || ev.date,
      venue: ev.circuit?.fullName || ev.venues?.[0]?.fullName,
      city: ev.circuit?.address?.city,
      sessions,
    };
  }
  const drivers: Driver[] = [];
  const constructors: Constructor[] = [];
  for (const ch of standings?.children || []) {
    for (const e of ch.standings?.entries || []) {
      const s = statMap(e.stats);
      if (e.athlete) {
        const perRace = (e.stats || [])
          .filter((x: Json) => x.played === true)
          .map((x: Json) => num(x.value) ?? 0);
        drivers.push({
          id: String(e.athlete.id),
          name: e.athlete.displayName,
          short: e.athlete.shortName || e.athlete.displayName,
          abbr: e.athlete.abbreviation || '',
          flag: e.athlete.flag?.href,
          rank: s.rank?.v ?? 99,
          points: s.championshipPts?.v ?? s.points?.v ?? 0,
          perRace,
        });
      } else if (e.team) {
        constructors.push({
          id: String(e.team.id),
          name: e.team.displayName || e.team.name,
          color: color(e.team.color),
          rank: s.rank?.v ?? 99,
          points: s.championshipPts?.v ?? s.points?.v ?? 0,
        });
      }
    }
  }
  return { race, drivers, constructors };
}

/** Logo de ESPN redimensionado por su propio servicio de imágenes. */
export function resizedLogo(url: string, size: number): string {
  try {
    const u = new URL(url.replace(/^http:/, 'https:'));
    if (u.pathname.startsWith('/combiner/')) {
      const img = u.searchParams.get('img');
      if (!img) return u.toString();
      return `https://a.espncdn.com/combiner/i?img=${img}&w=${size}&h=${size}&transparent=true`;
    }
    if (u.hostname.endsWith('espncdn.com')) {
      return `https://a.espncdn.com/combiner/i?img=${u.pathname}&w=${size}&h=${size}&transparent=true`;
    }
    return u.toString();
  } catch {
    return url;
  }
}
