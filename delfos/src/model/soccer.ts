// Modelo de fútbol: Poisson bivariante con corrección de Dixon-Coles para
// marcadores bajos. Las fuerzas de ataque y defensa salen de la clasificación,
// encogidas hacia la temporada anterior (o la media de la liga) para que las
// primeras jornadas no disparen los números.
import type { TeamStats } from '../data/types';

export const MAX_GOALS = 7;
const RHO = -0.06;
/** Peso del histórico en partidos equivalentes. */
const PRIOR_GAMES = 8;

export interface SoccerStrength {
  att: number;
  def: number;
  /** Partidos reales de la temporada en curso que respaldan la estimación */
  games: number;
  source: 'temporada' | 'temporada+anterior' | 'anterior' | 'media';
}

export interface LeagueAverages {
  /** Goles por equipo y partido */
  mu: number;
}

export function leagueAverages(rows: TeamStats[]): LeagueAverages {
  const gp = rows.reduce((s, r) => s + r.gp, 0);
  const gf = rows.reduce((s, r) => s + r.gf, 0);
  const mu = gp >= 10 ? gf / gp : 1.35;
  return { mu: Math.min(Math.max(mu, 0.9), 2.0) };
}

/**
 * Fuerza de un equipo a partir de su fila actual y (opcional) la de la
 * temporada anterior. Equipos sin histórico (recién ascendidos) arrancan
 * algo por debajo de la media.
 */
export function strengthOf(
  cur: TeamStats | undefined,
  prev: TeamStats | undefined,
  avg: LeagueAverages,
  prevAvg?: LeagueAverages,
): SoccerStrength {
  const mu = avg.mu;
  let priorAtt = 0.9;
  let priorDef = 1.1;
  let source: SoccerStrength['source'] = 'media';
  if (prev && prev.gp >= 10) {
    const pmu = prevAvg?.mu ?? mu;
    // Se regresa un 30 % a la media: los planteles cambian en verano.
    priorAtt = 0.7 * (prev.gf / prev.gp / pmu) + 0.3;
    priorDef = 0.7 * (prev.ga / prev.gp / pmu) + 0.3;
    source = 'anterior';
  }
  if (!cur || cur.gp === 0) return { att: priorAtt, def: priorDef, games: 0, source };
  const att = (cur.gf / mu + PRIOR_GAMES * priorAtt) / (cur.gp + PRIOR_GAMES);
  const def = (cur.ga / mu + PRIOR_GAMES * priorDef) / (cur.gp + PRIOR_GAMES);
  return { att, def, games: cur.gp, source: source === 'anterior' ? 'temporada+anterior' : 'temporada' };
}

/** Ajuste suave por la racha reciente (W/D/L de los últimos partidos). */
export function formFactor(form?: string): number {
  if (!form) return 1;
  const chars = form.toUpperCase().replace(/[^WDL]/g, '').split('');
  if (chars.length < 3) return 1;
  const ppg = chars.reduce((s, c) => s + (c === 'W' ? 3 : c === 'D' ? 1 : 0), 0) / chars.length;
  return Math.min(1.06, Math.max(0.94, 1 + 0.03 * (ppg - 1.4)));
}

export function expectedGoals(
  home: SoccerStrength,
  away: SoccerStrength,
  avg: LeagueAverages,
  neutral: boolean,
  formHome = 1,
  formAway = 1,
): { lh: number; la: number } {
  const ha = neutral ? 1 : 1.11;
  const lh = avg.mu * ha * home.att * away.def * formHome;
  const la = (avg.mu / ha) * away.att * home.def * formAway;
  return { lh: clampL(lh), la: clampL(la) };
}

const clampL = (l: number) => Math.min(Math.max(l, 0.15), 4.5);

function poissonPmf(l: number, k: number): number {
  let p = Math.exp(-l);
  for (let i = 1; i <= k; i++) p *= l / i;
  return p;
}

/** Matriz de probabilidades de marcador [golesLocal][golesVisitante]. */
export function scoreMatrix(lh: number, la: number, rho = RHO): number[][] {
  const m: number[][] = [];
  let sum = 0;
  for (let i = 0; i <= MAX_GOALS; i++) {
    m[i] = [];
    for (let j = 0; j <= MAX_GOALS; j++) {
      let p = poissonPmf(lh, i) * poissonPmf(la, j);
      if (i === 0 && j === 0) p *= 1 - lh * la * rho;
      else if (i === 0 && j === 1) p *= 1 + lh * rho;
      else if (i === 1 && j === 0) p *= 1 + la * rho;
      else if (i === 1 && j === 1) p *= 1 - rho;
      m[i][j] = Math.max(p, 0);
      sum += m[i][j];
    }
  }
  for (const row of m) for (let j = 0; j < row.length; j++) row[j] /= sum;
  return m;
}

export interface MatrixSummary {
  pHome: number;
  pDraw: number;
  pAway: number;
  pOver25: number;
  pOver15: number;
  pOver35: number;
  pBtts: number;
  best: { h: number; a: number; p: number };
  top: { h: number; a: number; p: number }[];
  xgHome: number;
  xgAway: number;
}

export function summarize(m: number[][]): MatrixSummary {
  let pHome = 0, pDraw = 0, pAway = 0, o15 = 0, o25 = 0, o35 = 0, btts = 0, xh = 0, xa = 0;
  const cells: { h: number; a: number; p: number }[] = [];
  for (let i = 0; i < m.length; i++) {
    for (let j = 0; j < m[i].length; j++) {
      const p = m[i][j];
      if (i > j) pHome += p;
      else if (i === j) pDraw += p;
      else pAway += p;
      if (i + j > 1) o15 += p;
      if (i + j > 2) o25 += p;
      if (i + j > 3) o35 += p;
      if (i > 0 && j > 0) btts += p;
      xh += i * p;
      xa += j * p;
      cells.push({ h: i, a: j, p });
    }
  }
  cells.sort((x, y) => y.p - x.p);
  return {
    pHome, pDraw, pAway,
    pOver15: o15, pOver25: o25, pOver35: o35,
    pBtts: btts,
    best: cells[0],
    top: cells.slice(0, 5),
    xgHome: xh,
    xgAway: xa,
  };
}

/**
 * Ajusta los goles esperados para que el 1X2 (y, si hay, la probabilidad del
 * más de 2,5) coincidan con unas probabilidades objetivo. Así el marcador, la
 * matriz y los mercados de goles quedan coherentes con el pronóstico final.
 * Gauss-Newton sobre log(lambda) con derivadas numéricas.
 */
export function fitLambdas(
  start: { lh: number; la: number },
  target: { pHome: number; pAway: number; pOver25?: number },
): { lh: number; la: number } {
  let x = [Math.log(start.lh), Math.log(start.la)];
  const resid = (v: number[]) => {
    const s = summarize(scoreMatrix(Math.exp(v[0]), Math.exp(v[1])));
    const r = [s.pHome - target.pHome, s.pAway - target.pAway];
    if (target.pOver25 !== undefined) r.push(0.5 * (s.pOver25 - target.pOver25));
    return r;
  };
  for (let it = 0; it < 25; it++) {
    const r = resid(x);
    const err = r.reduce((s, v) => s + v * v, 0);
    if (err < 1e-8) break;
    const h = 1e-4;
    const J = [0, 1].map((k) => {
      const xp = x.slice();
      xp[k] += h;
      const rp = resid(xp);
      return rp.map((v, i) => (v - r[i]) / h);
    });
    // JtJ (2x2) y Jt r
    const a = J[0].reduce((s, v) => s + v * v, 0) + 1e-6;
    const b = J[0].reduce((s, v, i) => s + v * J[1][i], 0);
    const d = J[1].reduce((s, v) => s + v * v, 0) + 1e-6;
    const g0 = J[0].reduce((s, v, i) => s + v * r[i], 0);
    const g1 = J[1].reduce((s, v, i) => s + v * r[i], 0);
    const det = a * d - b * b;
    if (Math.abs(det) < 1e-12) break;
    const dx0 = (d * g0 - b * g1) / det;
    const dx1 = (a * g1 - b * g0) / det;
    const step = Math.min(1, 0.8 / Math.max(Math.abs(dx0), Math.abs(dx1), 1e-9));
    x = [x[0] - step * dx0, x[1] - step * dx1];
    x = x.map((v) => Math.min(Math.max(v, Math.log(0.1)), Math.log(5)));
  }
  return { lh: Math.exp(x[0]), la: Math.exp(x[1]) };
}
