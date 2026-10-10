// Deportes de EE. UU. (NBA, WNBA, NFL, MLB, NHL): rating por diferencia de
// puntos por partido, encogido hacia la temporada anterior, más ventaja de
// campo. La probabilidad sale de una normal sobre el margen esperado.
import type { SportId, TeamStats } from '../data/types';

export interface UsParams {
  /** Ventaja de campo en puntos/carreras/goles */
  hfa: number;
  /** Desviación típica del margen final */
  sigma: number;
  /** Partidos equivalentes que pesa el histórico */
  priorGames: number;
  /** Cuánto del rating anterior se conserva (el resto regresa a 0) */
  carry: number;
  /** Media de puntos por equipo y partido si no hay datos */
  avgPoints: number;
}

export const US_PARAMS: Partial<Record<SportId | 'wnba', UsParams>> = {
  basketball: { hfa: 2.4, sigma: 12.5, priorGames: 12, carry: 0.6, avgPoints: 114 },
  wnba: { hfa: 2.2, sigma: 11.5, priorGames: 8, carry: 0.6, avgPoints: 82 },
  football: { hfa: 1.6, sigma: 13.5, priorGames: 5, carry: 0.5, avgPoints: 22.5 },
  baseball: { hfa: 0.16, sigma: 4.3, priorGames: 30, carry: 0.5, avgPoints: 4.4 },
  hockey: { hfa: 0.17, sigma: 2.35, priorGames: 14, carry: 0.55, avgPoints: 3.05 },
};

export interface UsRating {
  /** Margen por partido frente a un rival medio */
  margin: number;
  /** Puntos a favor y en contra por partido (para el marcador) */
  off: number;
  def: number;
  games: number;
  source: 'temporada' | 'temporada+anterior' | 'anterior' | 'media';
}

export function leagueAvgPoints(rows: TeamStats[], fallback: number): number {
  const gp = rows.reduce((s, r) => s + r.gp, 0);
  const pf = rows.reduce((s, r) => s + r.gf, 0);
  return gp >= 20 ? pf / gp : fallback;
}

export function ratingOf(
  cur: TeamStats | undefined,
  prev: TeamStats | undefined,
  p: UsParams,
  avg: number,
  useCurrent = true,
): UsRating {
  let pm = 0, po = avg, pd = avg;
  let source: UsRating['source'] = 'media';
  if (prev && prev.gp >= 10) {
    const m = (prev.gf - prev.ga) / prev.gp;
    pm = m * p.carry;
    po = avg + ((prev.gf / prev.gp) - avg) * p.carry;
    pd = avg + ((prev.ga / prev.gp) - avg) * p.carry;
    source = 'anterior';
  }
  if (!useCurrent || !cur || cur.gp === 0) return { margin: pm, off: po, def: pd, games: 0, source };
  const k = p.priorGames;
  const n = cur.gp;
  return {
    margin: ((cur.gf - cur.ga) + k * pm) / (n + k),
    off: (cur.gf + k * po) / (n + k),
    def: (cur.ga + k * pd) / (n + k),
    games: n,
    source: source === 'anterior' ? 'temporada+anterior' : 'temporada',
  };
}

/** Función de distribución normal estándar (aprox. de Abramowitz-Stegun). */
export function phi(x: number): number {
  const t = 1 / (1 + 0.2316419 * Math.abs(x));
  const d = 0.3989423 * Math.exp((-x * x) / 2);
  const p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))));
  return x > 0 ? 1 - p : p;
}

/** Margen que corresponde a una probabilidad (inversa de phi por bisección). */
export function marginFor(prob: number, sigma: number): number {
  let lo = -6, hi = 6;
  for (let i = 0; i < 50; i++) {
    const mid = (lo + hi) / 2;
    if (phi(mid) < prob) lo = mid;
    else hi = mid;
  }
  return ((lo + hi) / 2) * sigma;
}
