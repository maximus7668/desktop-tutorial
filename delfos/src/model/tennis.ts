// Tenis: probabilidad a partir de los puntos del ranking (modelo tipo
// Bradley-Terry) y reparto de marcadores en sets.

/** Puntos aproximados para un ranking cuando no tenemos la cifra exacta. */
export function pointsFromRank(rank?: number): number {
  const r = rank && rank > 0 ? rank : 300;
  return 11000 * Math.pow(r, -0.78);
}

export function tennisWinProb(pointsA: number, pointsB: number): number {
  const k = 0.92;
  const a = Math.pow(Math.max(pointsA, 1), k);
  const b = Math.pow(Math.max(pointsB, 1), k);
  // Se limita a [8 %, 92 %]: en tenis hay sorpresas todas las semanas.
  return Math.min(0.92, Math.max(0.08, a / (a + b)));
}

const GRAND_SLAMS = /australian open|roland|french open|wimbledon|us open/i;

export const bestOf = (league: string, tournament?: string) =>
  league === 'atp' && tournament && GRAND_SLAMS.test(tournament) ? 5 : 3;

function matchProbFromSet(ps: number, sets: number): number {
  const need = Math.ceil(sets / 2);
  // Probabilidad de ganar `need` sets antes que el rival
  let p = 0;
  for (let lost = 0; lost < need; lost++) {
    p += binom(need - 1 + lost, lost) * Math.pow(ps, need) * Math.pow(1 - ps, lost);
  }
  return p;
}

function binom(n: number, k: number): number {
  let r = 1;
  for (let i = 1; i <= k; i++) r = (r * (n - k + i)) / i;
  return r;
}

export function setProbFromMatch(pm: number, sets: number): number {
  let lo = 0, hi = 1;
  for (let i = 0; i < 50; i++) {
    const mid = (lo + hi) / 2;
    if (matchProbFromSet(mid, sets) < pm) lo = mid;
    else hi = mid;
  }
  return (lo + hi) / 2;
}

/** Probabilidad de cada marcador en sets, de mayor a menor. */
export function setScores(pm: number, sets: number): { a: number; b: number; p: number }[] {
  const ps = setProbFromMatch(pm, sets);
  const need = Math.ceil(sets / 2);
  const out: { a: number; b: number; p: number }[] = [];
  for (let lost = 0; lost < need; lost++) {
    const pa = binom(need - 1 + lost, lost) * Math.pow(ps, need) * Math.pow(1 - ps, lost);
    const pb = binom(need - 1 + lost, lost) * Math.pow(1 - ps, need) * Math.pow(ps, lost);
    out.push({ a: need, b: lost, p: pa }, { a: lost, b: need, p: pb });
  }
  return out.sort((x, y) => y.p - x.p);
}
