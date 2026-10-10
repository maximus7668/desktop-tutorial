// Fuente de datos: en directo desde ESPN (web) o instantánea embebida (Artifact).
import snapshot from '@snapshot';
import {
  emptyTable, parseF1, parseRankings, parseScoreboard, parseStandings, parseTennis, rankingsUrl,
  resizedLogo, scoreboardSeasonYear, scoreboardUrl, seasonName, standingsUrl,
} from './espn';
import { LEAGUES, LEAGUE_BY_ID } from './leagues';
import type { F1Data, LeagueTable, Match, RankEntry } from './types';

export interface SnapshotData {
  generatedAt: string;
  matches: Match[];
  tables: Record<string, LeagueTable>;
  f1: F1Data | null;
  rankings: Record<string, RankEntry[]>;
  logos: Record<string, string>;
}

const SNAP = snapshot as SnapshotData | null;

export const MODE: 'live' | 'snapshot' = SNAP ? 'snapshot' : 'live';
export const GENERATED_AT = SNAP?.generatedAt;

/* ------------------------------ Fechas ------------------------------ */

const pad = (n: number) => String(n).padStart(2, '0');
export const dayKey = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
export const parseDayKey = (k: string) => {
  const [y, m, d] = k.split('-').map(Number);
  return new Date(y, m - 1, d, 12);
};
export const addDays = (k: string, n: number) => {
  const d = parseDayKey(k);
  d.setDate(d.getDate() + n);
  return dayKey(d);
};
export const localDayOf = (iso: string) => dayKey(new Date(iso));
const espnDay = (k: string) => k.replace(/-/g, '');

/** Días de ESPN (hora del este de EE. UU.) que cubren un día local. */
function espnDaysFor(k: string): string[] {
  const offsetH = -new Date().getTimezoneOffset() / 60; // España en verano: +2
  const etOffset = -4;
  if (offsetH > etOffset) return [espnDay(addDays(k, -1)), espnDay(k)];
  if (offsetH < etOffset) return [espnDay(k), espnDay(addDays(k, 1))];
  return [espnDay(k)];
}

/* ------------------------------ Caché ------------------------------ */

const mem = new Map<string, { at: number; data: unknown }>();

function store(): Storage | undefined {
  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
}

async function getJson<T = unknown>(url: string, ttlMs: number, persist = false): Promise<T> {
  const now = Date.now();
  const hit = mem.get(url);
  if (hit && now - hit.at < ttlMs) return hit.data as T;
  if (persist) {
    try {
      const raw = store()?.getItem(`delfos:${url}`);
      if (raw) {
        const c = JSON.parse(raw) as { at: number; data: T };
        if (now - c.at < ttlMs) {
          mem.set(url, c);
          return c.data;
        }
      }
    } catch {
      /* caché corrupta: se ignora */
    }
  }
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 15000);
  try {
    const res = await fetch(url, { signal: ctrl.signal });
    if (!res.ok) throw new Error(`ESPN respondió ${res.status}`);
    const data = (await res.json()) as T;
    mem.set(url, { at: now, data });
    if (persist) {
      try {
        store()?.setItem(`delfos:${url}`, JSON.stringify({ at: now, data }));
      } catch {
        /* sin espacio: solo memoria */
      }
    }
    return data;
  } finally {
    clearTimeout(timer);
  }
}

async function pool<T, R>(items: T[], n: number, fn: (x: T) => Promise<R>): Promise<R[]> {
  const out: R[] = new Array(items.length);
  let i = 0;
  const workers = Array.from({ length: Math.min(n, items.length) }, async () => {
    while (i < items.length) {
      const k = i++;
      out[k] = await fn(items[k]);
    }
  });
  await Promise.all(workers);
  return out;
}

/* --------------------------- API pública --------------------------- */

const seasonYear = new Map<string, number>();
const TEAM_LEAGUES = LEAGUES.filter((l) => l.sport !== 'tennis' && l.sport !== 'racing');

export interface DayResult {
  matches: Match[];
  failed: string[];
}

export async function loadRankings(id: 'atp' | 'wta'): Promise<RankEntry[]> {
  if (SNAP) return SNAP.rankings?.[id] || [];
  const rk = await getJson(rankingsUrl(LEAGUE_BY_ID[id].slug), 12 * 3600_000, true);
  return parseRankings(rk);
}

async function tennisMatches(): Promise<Match[]> {
  const out: Match[] = [];
  for (const id of ['atp', 'wta']) {
    const l = LEAGUE_BY_ID[id];
    const [sb, rk] = await Promise.all([
      getJson(scoreboardUrl(l.slug), 5 * 60_000),
      getJson(rankingsUrl(l.slug), 12 * 3600_000, true).catch(() => null),
    ]);
    const ranks: RankEntry[] = rk ? parseRankings(rk) : [];
    out.push(...parseTennis(l, sb, ranks));
  }
  return out;
}

export async function loadDay(k: string): Promise<DayResult> {
  if (SNAP) return { matches: SNAP.matches.filter((m) => localDayOf(m.start) === k), failed: [] };
  const today = dayKey(new Date());
  const ttl = k === today ? 60_000 : k < today ? 30 * 60_000 : 10 * 60_000;
  const failed: string[] = [];
  const jobs = TEAM_LEAGUES.flatMap((l) => espnDaysFor(k).map((d) => ({ l, d })));
  const parts = await pool(jobs, 8, async ({ l, d }) => {
    try {
      const json = await getJson(scoreboardUrl(l.slug, d), ttl);
      const y = scoreboardSeasonYear(json);
      if (y) seasonYear.set(l.id, y);
      return parseScoreboard(l, json);
    } catch {
      if (!failed.includes(l.name)) failed.push(l.name);
      return [];
    }
  });
  let tennis: Match[] = [];
  try {
    tennis = await tennisMatches();
  } catch {
    failed.push('Tenis');
  }
  const seen = new Set<string>();
  const matches = [...parts.flat(), ...tennis].filter((m) => {
    if (seen.has(m.id) || localDayOf(m.start) !== k) return false;
    seen.add(m.id);
    return true;
  });
  return { matches, failed };
}

export async function loadTable(leagueId: string): Promise<LeagueTable> {
  if (SNAP) return SNAP.tables[leagueId] || emptyTable(leagueId);
  const l = LEAGUE_BY_ID[leagueId];
  if (!l || l.sport === 'tennis' || l.sport === 'racing') return emptyTable(leagueId);
  let year = seasonYear.get(leagueId);
  if (!year) {
    try {
      year = scoreboardSeasonYear(await getJson(scoreboardUrl(l.slug), 10 * 60_000));
      if (year) seasonYear.set(leagueId, year);
    } catch {
      /* sin año: no hay temporada anterior */
    }
  }
  const [cur, prev] = await Promise.all([
    getJson(standingsUrl(l.slug), 3 * 3600_000, true).catch(() => null),
    year ? getJson(standingsUrl(l.slug, year - 1), 7 * 24 * 3600_000, true).catch(() => null) : Promise.resolve(null),
  ]);
  return {
    leagueId,
    season: cur ? seasonName(cur) : '',
    current: cur ? parseStandings(cur) : [],
    previous: prev ? parseStandings(prev) : [],
  };
}

export async function loadTables(ids: string[]): Promise<Record<string, LeagueTable>> {
  const uniq = [...new Set(ids)];
  const rows = await pool(uniq, 6, (id) => loadTable(id).catch(() => emptyTable(id)));
  return Object.fromEntries(uniq.map((id, i) => [id, rows[i]]));
}

export async function loadF1(): Promise<F1Data | null> {
  if (SNAP) return SNAP.f1;
  const l = LEAGUE_BY_ID.f1;
  const [sb, st] = await Promise.all([
    getJson(scoreboardUrl(l.slug), 5 * 60_000),
    getJson(standingsUrl(l.slug), 3 * 3600_000, true),
  ]);
  return parseF1(sb, st);
}

/** Días disponibles en la instantánea (o null si hay datos en directo). */
export function snapshotDays(): string[] | null {
  if (!SNAP) return null;
  return [...new Set(SNAP.matches.map((m) => localDayOf(m.start)))].sort();
}

/** URL de imagen lista para pintar: data URI en la instantánea, ESPN redimensionado en directo. */
export function logoSrc(url: string | undefined, size = 96): string | undefined {
  if (!url) return undefined;
  if (SNAP) return SNAP.logos[url];
  return resizedLogo(url, size);
}
