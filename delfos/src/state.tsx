import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { loadDay, loadTables, MODE } from './data/source';
import { LEAGUE_BY_ID } from './data/leagues';
import type { LeagueTable, Match, Outcome, SportId } from './data/types';

/* ------------------------------ Almacén local ------------------------------ */

export function readLocal<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(`delfos:${key}`);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function writeLocal(key: string, value: unknown) {
  try {
    window.localStorage.setItem(`delfos:${key}`, JSON.stringify(value));
  } catch {
    /* almacenamiento bloqueado: se mantiene en memoria */
  }
}

/* --------------------------------- Tema --------------------------------- */

export type ThemePref = 'system' | 'light' | 'dark';

export function useThemePref(): [ThemePref, (t: ThemePref) => void] {
  const [pref, setPref] = useState<ThemePref>(() => (MODE === 'live' ? readLocal<ThemePref>('theme', 'system') : 'system'));
  useEffect(() => {
    if (MODE !== 'live') return;
    const root = document.documentElement;
    if (pref === 'system') root.removeAttribute('data-theme');
    else root.setAttribute('data-theme', pref);
    writeLocal('theme', pref);
  }, [pref]);
  return [pref, setPref];
}

/** ¿Se está viendo en oscuro? (preferencia del sistema o data-theme del visor) */
export function useIsDark(): boolean {
  const compute = () => {
    const t = document.documentElement.getAttribute('data-theme');
    if (t === 'dark') return true;
    if (t === 'light') return false;
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false;
  };
  const [dark, setDark] = useState(compute);
  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-color-scheme: dark)');
    const on = () => setDark(compute());
    mq?.addEventListener?.('change', on);
    const mo = new MutationObserver(on);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => {
      mq?.removeEventListener?.('change', on);
      mo.disconnect();
    };
  }, []);
  return dark;
}

/* ------------------------------ Datos del día ------------------------------ */

export interface DayState {
  matches: Match[];
  tables: Record<string, LeagueTable>;
  loading: boolean;
  error?: string;
  failed: string[];
}

const SOCCER_DOMESTIC = ['esp.1', 'eng.1', 'ita.1', 'ger.1', 'fra.1', 'por.1', 'ned.1', 'bra.1', 'arg.1', 'mex.1', 'usa.1', 'esp.2'];
const CROSS = ['uefa.champions', 'uefa.europa', 'uefa.europa.conf', 'conmebol.libertadores', 'uefa.nations'];

export function tablesNeeded(matches: Match[]): string[] {
  const ids = new Set<string>();
  for (const m of matches) {
    const l = LEAGUE_BY_ID[m.leagueId];
    if (!l || l.sport === 'tennis' || l.sport === 'racing') continue;
    ids.add(m.leagueId);
    if (CROSS.includes(m.leagueId)) SOCCER_DOMESTIC.forEach((x) => ids.add(x));
  }
  return [...ids];
}

export function useDay(k: string, nonce = 0): DayState {
  const [state, setState] = useState<DayState>({ matches: [], tables: {}, loading: true, failed: [] });
  useEffect(() => {
    let alive = true;
    setState((s) => ({ ...s, loading: true, error: undefined }));
    (async () => {
      try {
        const day = await loadDay(k);
        const tables = await loadTables(tablesNeeded(day.matches));
        if (alive) setState({ matches: day.matches, tables, loading: false, failed: day.failed });
      } catch (e) {
        if (alive) setState({ matches: [], tables: {}, loading: false, failed: [], error: e instanceof Error ? e.message : 'Error desconocido' });
      }
    })();
    return () => {
      alive = false;
    };
  }, [k, nonce]);
  return state;
}

/* ------------------------------- Combinada ------------------------------- */

export interface SlipPick {
  matchId: string;
  outcome: Outcome | 'over' | 'under' | 'btts';
  label: string;
  matchLabel: string;
  leagueId: string;
  sport: SportId;
  start: string;
  prob: number;
  market?: number;
}

interface SlipCtx {
  picks: SlipPick[];
  toggle: (p: SlipPick) => void;
  remove: (matchId: string) => void;
  clear: () => void;
  replace: (p: SlipPick[]) => void;
  has: (matchId: string, outcome: SlipPick['outcome']) => boolean;
}

const Ctx = createContext<SlipCtx | null>(null);

export function SlipProvider({ children }: { children: ReactNode }) {
  const [picks, setPicks] = useState<SlipPick[]>(() => readLocal<SlipPick[]>('slip', []));
  useEffect(() => writeLocal('slip', picks), [picks]);
  const toggle = useCallback((p: SlipPick) => {
    setPicks((cur) => {
      const same = cur.find((x) => x.matchId === p.matchId);
      if (same && same.outcome === p.outcome) return cur.filter((x) => x.matchId !== p.matchId);
      // Una selección por partido: la nueva sustituye a la anterior.
      return [...cur.filter((x) => x.matchId !== p.matchId), p];
    });
  }, []);
  const value = useMemo<SlipCtx>(() => ({
    picks,
    toggle,
    remove: (id) => setPicks((cur) => cur.filter((x) => x.matchId !== id)),
    clear: () => setPicks([]),
    replace: (p) => setPicks(p),
    has: (id, o) => picks.some((x) => x.matchId === id && x.outcome === o),
  }), [picks, toggle]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSlip(): SlipCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error('SlipProvider ausente');
  return c;
}
