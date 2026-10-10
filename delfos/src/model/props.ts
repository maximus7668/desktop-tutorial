// Mercados de estadísticas (fútbol): córners, tarjetas, tiros a puerta, tiros
// y faltas. Cada equipo tiene una tendencia a favor y otra en contra respecto a
// la media de su liga; el valor esperado del partido combina la tendencia de
// uno con la permisividad del rival y el factor campo. Los conteos siguen una
// binomial negativa (más dispersa que una Poisson, como en la realidad).
import type { LeagueAgg, PropStat, TeamAgg } from '../data/teamStats';
import type { Match, MatchStats } from '../data/types';
import { scoreMatrix } from './soccer';

export const PROP_INFO: Record<PropStat, { name: string; unit: string; kTotal: number; kTeam: number }> = {
  corners: { name: 'Córners', unit: 'córners', kTotal: 40, kTeam: 15 },
  cards: { name: 'Tarjetas', unit: 'tarjetas', kTotal: 12, kTeam: 6 },
  sot: { name: 'Tiros a puerta', unit: 'tiros a puerta', kTotal: 35, kTeam: 15 },
  shots: { name: 'Tiros', unit: 'tiros', kTotal: 60, kTeam: 25 },
  fouls: { name: 'Faltas', unit: 'faltas', kTotal: 80, kTeam: 40 },
};

/** Partidos de "media de liga" que se suman a cada equipo para estabilizar. */
const PRIOR_GAMES = 5;

/**
 * Cuánto del reparto entre equipos se toma del dominio esperado en goles del
 * partido (el resto, de las estadísticas propias). Quien va a dominar suele
 * sacar más córners y tirar más; en faltas y tarjetas no se aplica.
 */
const DOMINANCE_WEIGHT: Record<PropStat, number> = { corners: 0.3, cards: 0, sot: 0.5, shots: 0.4, fouls: 0 };

/** Distribución binomial negativa de media mu y forma k (Poisson si k es muy grande). */
export function nbPmf(mu: number, k: number, max = Math.ceil(mu + 10 * Math.sqrt(mu + 1) + 10)): number[] {
  const out: number[] = [];
  if (k >= 500) {
    let p = Math.exp(-mu);
    for (let x = 0; x <= max; x++) {
      out.push(p);
      p *= mu / (x + 1);
    }
    return out;
  }
  const q = mu / (k + mu);
  let p = Math.pow(k / (k + mu), k);
  for (let x = 0; x <= max; x++) {
    out.push(p);
    p *= ((x + k) / (x + 1)) * q;
  }
  return out;
}

/** P(X > line) para líneas de medio punto. */
export const overProb = (pmf: number[], line: number) => pmf.reduce((s, p, x) => (x > line ? s + p : s), 0);

export interface PropLine {
  line: number;
  over: number;
}

export interface PropPick {
  label: string;
  short: string;
  prob: number;
  scope: 'total' | 'home' | 'away';
  side: 'over' | 'under';
  line: number;
}

export interface PropMarket {
  stat: PropStat;
  name: string;
  unit: string;
  home: number;
  away: number;
  total: number;
  totalLines: PropLine[];
  homeLines: PropLine[];
  awayLines: PropLine[];
  /** Quién tendrá más (local, igualdad, visitante) */
  more: { home: number; draw: number; away: number };
  pick?: PropPick;
  /** Partidos con datos del equipo con menos historial */
  games: number;
  actual?: { home: number; away: number };
}

export interface SideInput {
  agg?: TeamAgg;
  league?: LeagueAgg;
}

function rel(t: TeamAgg | undefined, stat: PropStat, kind: 'for' | 'against', avg: number): number {
  if (!t || t.gp === 0 || avg <= 0) return 1;
  return (t[kind][stat] + PRIOR_GAMES * avg) / (t.gp + PRIOR_GAMES) / avg;
}

export function expectedCounts(stat: PropStat, home: SideInput, away: SideInput, neutral: boolean): { home: number; away: number } {
  const ah = home.league?.avg[stat] ?? away.league?.avg[stat] ?? 0;
  const aa = away.league?.avg[stat] ?? ah;
  const ref = (ah + aa) / 2;
  const hr = neutral ? 1 : Math.sqrt((home.league ?? away.league)?.homeRatio[stat] ?? 1.1);
  return {
    home: ref * rel(home.agg, stat, 'for', ah) * rel(away.agg, stat, 'against', aa) * hr,
    away: ref * rel(away.agg, stat, 'for', aa) * rel(home.agg, stat, 'against', ah) / hr,
  };
}

function linesAround(mu: number, spread: number): number[] {
  const c = Math.round(mu);
  const out: number[] = [];
  for (let l = c - spread - 0.5; l <= c + spread + 0.5; l++) if (l >= 0.5) out.push(l);
  return out;
}

const fmt = (x: number) => x.toLocaleString('es-ES');

function choosePick(stat: PropStat, m: Match, lines: { scope: PropPick['scope']; list: PropLine[] }[]): PropPick | undefined {
  const unit = PROP_INFO[stat].unit;
  let best: PropPick | undefined;
  for (const { scope, list } of lines) {
    for (const l of list) {
      for (const side of ['over', 'under'] as const) {
        const prob = side === 'over' ? l.over : 1 - l.over;
        // La línea más útil: probable (>= 62 %) pero con la cuota más alta posible.
        if (prob < 0.62 || prob > 0.9) continue;
        if (best && prob >= best.prob) continue;
        const who = scope === 'total' ? '' : ` de ${scope === 'home' ? m.home.team.short : m.away.team.short}`;
        const label = `${side === 'over' ? 'Más' : 'Menos'} de ${fmt(l.line)} ${unit}${who}`;
        best = { label, short: `${side === 'over' ? '+' : '−'}${fmt(l.line)}`, prob, scope, side, line: l.line };
      }
    }
  }
  return best;
}

function actualOf(s: MatchStats | undefined, stat: PropStat): number | undefined {
  if (!s) return undefined;
  if (stat === 'cards') return s.yellow === undefined ? undefined : s.yellow + (s.red ?? 0);
  return s[stat];
}

/**
 * @param goalShare parte de los goles esperados que corresponde al local
 *   (lambda local / suma), para corregir el reparto por dominio.
 */
export function propMarkets(m: Match, home: SideInput, away: SideInput, goalShare?: number): PropMarket[] {
  if (!home.league && !away.league) return [];
  const out: PropMarket[] = [];
  for (const stat of Object.keys(PROP_INFO) as PropStat[]) {
    const info = PROP_INFO[stat];
    const raw = expectedCounts(stat, home, away, m.neutral);
    if (!(raw.home > 0 && raw.away > 0)) continue;
    const total = raw.home + raw.away;
    const w = goalShare === undefined ? 0 : DOMINANCE_WEIGHT[stat];
    const share = (1 - w) * (raw.home / total) + w * (goalShare ?? 0.5);
    const e = { home: total * share, away: total * (1 - share) };
    const pT = nbPmf(total, info.kTotal);
    const pH = nbPmf(e.home, info.kTeam);
    const pA = nbPmf(e.away, info.kTeam);
    let mh = 0, md = 0;
    for (let i = 0; i < pH.length; i++) {
      for (let j = 0; j < pA.length; j++) {
        const p = pH[i] * pA[j];
        if (i > j) mh += p;
        else if (i === j) md += p;
      }
    }
    const totalLines = linesAround(total, 3).map((line) => ({ line, over: overProb(pT, line) }));
    const homeLines = linesAround(e.home, 2).map((line) => ({ line, over: overProb(pH, line) }));
    const awayLines = linesAround(e.away, 2).map((line) => ({ line, over: overProb(pA, line) }));
    const ah = actualOf(m.home.stats, stat), aa = actualOf(m.away.stats, stat);
    out.push({
      stat, name: info.name, unit: info.unit,
      home: e.home, away: e.away, total,
      totalLines, homeLines, awayLines,
      more: { home: mh, draw: md, away: Math.max(0, 1 - mh - md) },
      pick: choosePick(stat, m, [{ scope: 'total', list: totalLines }]),
      games: Math.min(home.agg?.gp ?? 0, away.agg?.gp ?? 0),
      actual: ah !== undefined && aa !== undefined && m.status !== 'pre' ? { home: ah, away: aa } : undefined,
    });
  }
  return out;
}

export function expectedPossession(home: SideInput, away: SideInput): number | undefined {
  const h = home.agg && home.agg.gp ? home.agg.possession / home.agg.gp : undefined;
  const a = away.agg && away.agg.gp ? away.agg.possession / away.agg.gp : undefined;
  if (h === undefined && a === undefined) return undefined;
  return Math.min(80, Math.max(20, ((h ?? 50) + (100 - (a ?? 50))) / 2));
}

/* --------------------------- Goles: mercados extra --------------------------- */

export interface GoalExtras {
  teamGoals: { home: PropLine[]; away: PropLine[] };
  cleanSheet: { home: number; away: number };
  winToNil: { home: number; away: number };
  margin: { home1: number; home2: number; away1: number; away2: number };
  half: { pHome: number; pDraw: number; pAway: number; over05: number; over15: number };
  htft: { ht: 'home' | 'draw' | 'away'; ft: 'home' | 'draw' | 'away'; p: number }[];
}

/** Proporción de goles que se marcan en la primera parte. */
const FIRST_HALF_SHARE = 0.45;

function pois(l: number, n: number): number[] {
  const out: number[] = [];
  let p = Math.exp(-l);
  for (let x = 0; x <= n; x++) {
    out.push(p);
    p *= l / (x + 1);
  }
  return out;
}

const res = (h: number, a: number) => (h > a ? 'home' : h < a ? 'away' : 'draw') as 'home' | 'draw' | 'away';

export function goalExtras(matrix: number[][], lh: number, la: number): GoalExtras {
  const n = matrix.length;
  const ph = new Array(n).fill(0), pa = new Array(n).fill(0);
  let home1 = 0, home2 = 0, away1 = 0, away2 = 0, wtnH = 0, wtnA = 0;
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      const p = matrix[i][j];
      ph[i] += p;
      pa[j] += p;
      if (i - j === 1) home1 += p;
      if (i - j >= 2) home2 += p;
      if (j - i === 1) away1 += p;
      if (j - i >= 2) away2 += p;
      if (i > 0 && j === 0) wtnH += p;
      if (j > 0 && i === 0) wtnA += p;
    }
  }
  const tl = (dist: number[]) => [0.5, 1.5, 2.5].map((line) => ({ line, over: overProb(dist, line) }));
  const ht = scoreMatrix(lh * FIRST_HALF_SHARE, la * FIRST_HALF_SHARE);
  let hH = 0, hD = 0, hA = 0, o05 = 0, o15 = 0;
  for (let i = 0; i < ht.length; i++) {
    for (let j = 0; j < ht.length; j++) {
      const p = ht[i][j];
      if (i > j) hH += p;
      else if (i === j) hD += p;
      else hA += p;
      if (i + j > 0.5) o05 += p;
      if (i + j > 1.5) o15 += p;
    }
  }
  // Descanso/final: dos mitades independientes.
  const N = 6;
  const h1 = pois(lh * FIRST_HALF_SHARE, N), a1 = pois(la * FIRST_HALF_SHARE, N);
  const h2 = pois(lh * (1 - FIRST_HALF_SHARE), N), a2 = pois(la * (1 - FIRST_HALF_SHARE), N);
  const combos = new Map<string, number>();
  for (let i = 0; i <= N; i++) for (let j = 0; j <= N; j++) {
    const p1 = h1[i] * a1[j];
    if (p1 < 1e-6) continue;
    for (let k = 0; k <= N; k++) for (let l = 0; l <= N; l++) {
      const p = p1 * h2[k] * a2[l];
      const key = `${res(i, j)}|${res(i + k, j + l)}`;
      combos.set(key, (combos.get(key) ?? 0) + p);
    }
  }
  const sum = [...combos.values()].reduce((a, b) => a + b, 0);
  const htft = [...combos.entries()]
    .map(([k, p]) => {
      const [a, b] = k.split('|') as ['home' | 'draw' | 'away', 'home' | 'draw' | 'away'];
      return { ht: a, ft: b, p: p / sum };
    })
    .sort((x, y) => y.p - x.p);
  return {
    teamGoals: { home: tl(ph), away: tl(pa) },
    cleanSheet: { home: pa[0], away: ph[0] },
    winToNil: { home: wtnH, away: wtnA },
    margin: { home1, home2, away1, away2 },
    half: { pHome: hH, pDraw: hD, pAway: hA, over05: o05, over15: o15 },
    htft,
  };
}
