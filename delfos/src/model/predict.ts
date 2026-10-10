// Punto de entrada de los pronósticos: combina el modelo estadístico de cada
// deporte con las cuotas del mercado cuando las hay.
import { CROSS_SOCCER, LEAGUE_BY_ID } from '../data/leagues';
import type { LeagueTable, Match, Outcome, TeamStats } from '../data/types';
import { devig } from './odds';
import {
  expectedGoals, fitLambdas, formFactor, leagueAverages, scoreMatrix, strengthOf, summarize,
  type MatrixSummary, type SoccerStrength,
} from './soccer';
import { US_PARAMS, leagueAvgPoints, marginFor, phi, ratingOf, type UsParams } from './us';
import { bestOf, pointsFromRank, setScores, tennisWinProb } from './tennis';

export type Confidence = 'alta' | 'media' | 'baja';

export interface Prediction {
  matchId: string;
  threeWay: boolean;
  pHome: number;
  pDraw: number;
  pAway: number;
  pick: Outcome;
  pickProb: number;
  confidence: Confidence;
  score: { home: number; away: number };
  expected?: { home: number; away: number };
  market?: { pHome: number; pDraw: number; pAway: number; provider: string };
  model: { pHome: number; pDraw: number; pAway: number };
  soccer?: MatrixSummary & { matrix: number[][]; lh: number; la: number };
  /** EE. UU.: margen y total esperados con sus dispersiones, para calcular cualquier línea */
  us?: { margin: number; total: number; sigma: number; sigmaTotal: number };
  totals?: { line: number; pOver: number; expected: number };
  spread?: { line: number; pCover: number };
  tennis?: { sets: { a: number; b: number; p: number }[]; bestOf: number };
  doubleChance?: { label: '1X' | 'X2'; p: number };
  factors: string[];
  quality: 'buena' | 'media' | 'escasa';
}

export interface PredictContext {
  tables: Record<string, LeagueTable | undefined>;
}

/** Peso del mercado en el pronóstico final cuando hay cuotas. */
export const MARKET_WEIGHT = 0.65;

const CROSS = new Set(CROSS_SOCCER);
const LEAGUE_COEF: Record<string, number> = {
  'eng.1': 1, 'esp.1': 0.97, 'ita.1': 0.93, 'ger.1': 0.93, 'fra.1': 0.88, 'por.1': 0.82, 'ned.1': 0.8,
  'bra.1': 0.84, 'arg.1': 0.78, 'mex.1': 0.74, 'usa.1': 0.72, 'esp.2': 0.72,
};

const pct = (p: number) => `${Math.round(p * 100)} %`;
const dec1 = (x: number) => x.toLocaleString('es-ES', { maximumFractionDigits: 1, minimumFractionDigits: 1 });

/** Quita el propio partido de la fila de clasificación (para evaluar partidos ya jugados sin trampas). */
export function withoutResult(row: TeamStats | undefined, m: Match, side: 'home' | 'away'): TeamStats | undefined {
  if (!row || !m.completed || m.home.score === undefined || m.away.score === undefined || row.gp < 1) return row;
  const own = side === 'home' ? m.home.score : m.away.score;
  const opp = side === 'home' ? m.away.score : m.home.score;
  const r = { ...row, gp: row.gp - 1, gf: Math.max(0, row.gf - own), ga: Math.max(0, row.ga - opp) };
  if (own > opp) r.w = Math.max(0, r.w - 1);
  else if (own < opp) r.l = Math.max(0, r.l - 1);
  else r.d = Math.max(0, r.d - 1);
  return r;
}

function findRow(rows: TeamStats[] | undefined, id: string) {
  return rows?.find((r) => r.teamId === id);
}

function confidenceOf(p: number, threeWay: boolean, quality: Prediction['quality']): Confidence {
  const hi = threeWay ? 0.6 : 0.7;
  const mid = threeWay ? 0.46 : 0.58;
  let c: Confidence = p >= hi ? 'alta' : p >= mid ? 'media' : 'baja';
  if (quality === 'escasa' && c === 'alta') c = 'media';
  else if (quality === 'escasa') c = 'baja';
  return c;
}

function argmax3(h: number, d: number, a: number): Outcome {
  if (d > h && d > a) return 'draw';
  return h >= a ? 'home' : 'away';
}

/* ------------------------------- Fútbol ------------------------------- */

/** Marcador más probable entre los que dan el resultado pronosticado. */
export function likelyScoreFor(matrix: number[][], pick: Outcome): { home: number; away: number } {
  let best = { home: 1, away: 1, p: -1 };
  for (let i = 0; i < matrix.length; i++) {
    for (let j = 0; j < matrix[i].length; j++) {
      const ok = pick === 'home' ? i > j : pick === 'away' ? i < j : i === j;
      if (ok && matrix[i][j] > best.p) best = { home: i, away: j, p: matrix[i][j] };
    }
  }
  return { home: best.home, away: best.away };
}

function soccerSide(teamId: string, leagueId: string, ctx: PredictContext, m: Match, side: 'home' | 'away') {
  const own = ctx.tables[leagueId];
  if (!CROSS.has(leagueId) && own) {
    const cur = withoutResult(findRow(own.current, teamId), m, side);
    const prev = findRow(own.previous, teamId);
    const avg = leagueAverages(own.current);
    const prevAvg = leagueAverages(own.previous);
    return { s: strengthOf(cur, prev, avg, prevAvg), avg, coef: 1, row: cur, from: leagueId };
  }
  // Competiciones internacionales: fuerza en su liga nacional, corregida por el nivel de esa liga.
  for (const [lid, t] of Object.entries(ctx.tables)) {
    if (!t || CROSS.has(lid) || LEAGUE_BY_ID[lid]?.sport !== 'soccer') continue;
    const cur = findRow(t.current, teamId);
    if (!cur) continue;
    const prev = findRow(t.previous, teamId);
    const avg = leagueAverages(t.current);
    return { s: strengthOf(cur, prev, avg, leagueAverages(t.previous)), avg, coef: LEAGUE_COEF[lid] ?? 0.75, row: cur, from: lid };
  }
  const t = own;
  const cur = withoutResult(findRow(t?.current, teamId), m, side);
  const avg = leagueAverages(t?.current || []);
  return { s: strengthOf(cur, undefined, avg), avg, coef: 0.8, row: cur, from: leagueId };
}

function predictSoccer(m: Match, ctx: PredictContext): Prediction {
  const H = soccerSide(m.home.team.id, m.leagueId, ctx, m, 'home');
  const A = soccerSide(m.away.team.id, m.leagueId, ctx, m, 'away');
  const mu = CROSS.has(m.leagueId) ? 1.42 : H.avg.mu;
  const adj = (s: SoccerStrength, c: number): SoccerStrength => ({ ...s, att: s.att * c, def: s.def / c });
  const hs = adj(H.s, H.coef / Math.max(H.coef, A.coef));
  const as = adj(A.s, A.coef / Math.max(H.coef, A.coef));
  const live = m.completed;
  const fh = live ? 1 : formFactor(m.home.form);
  const fa = live ? 1 : formFactor(m.away.form);
  const base = expectedGoals(hs, as, { mu }, m.neutral, fh, fa);
  const modelSum = summarize(scoreMatrix(base.lh, base.la));
  const model = { pHome: modelSum.pHome, pDraw: modelSum.pDraw, pAway: modelSum.pAway };

  const mk = m.odds ? devig([m.odds.home, m.odds.draw, m.odds.away]) : undefined;
  const market = mk ? { pHome: mk[0], pDraw: mk[1], pAway: mk[2], provider: m.odds!.provider } : undefined;
  const statGames = Math.min(H.s.games, A.s.games);
  const hasHistory = H.s.source !== 'media' && A.s.source !== 'media';
  // Con pocos datos propios, se fía más del mercado.
  const w = market ? (statGames >= 6 || hasHistory ? MARKET_WEIGHT : 0.75) : 0;
  const tgt = {
    pHome: w * (market?.pHome ?? 0) + (1 - w) * model.pHome,
    pAway: w * (market?.pAway ?? 0) + (1 - w) * model.pAway,
  };
  let pOver25: number | undefined;
  if (m.odds?.total === 2.5 && m.odds.over !== undefined && m.odds.under !== undefined) {
    const ou = devig([m.odds.over, m.odds.under]);
    if (ou) pOver25 = w * ou[0] + (1 - w) * modelSum.pOver25;
  }
  const fitted = w > 0 ? fitLambdas(base, { ...tgt, pOver25 }) : base;
  const matrix = scoreMatrix(fitted.lh, fitted.la);
  const sum = summarize(matrix);
  const pHome = sum.pHome, pDraw = sum.pDraw, pAway = sum.pAway;
  const pick = argmax3(pHome, pDraw, pAway);
  const pickProb = Math.max(pHome, pDraw, pAway);
  const quality: Prediction['quality'] = market && (statGames >= 5 || hasHistory) ? 'buena' : market || statGames >= 5 || hasHistory ? 'media' : 'escasa';

  const factors: string[] = [];
  const line = (name: string, r?: TeamStats) =>
    r && r.gp > 0 ? `${name}: ${r.w}G ${r.d}E ${r.l}P en ${r.gp} partidos, ${dec1(r.gf / r.gp)} goles a favor y ${dec1(r.ga / r.gp)} en contra por partido.` : undefined;
  const l1 = line(m.home.team.short, H.row);
  const l2 = line(m.away.team.short, A.row);
  if (l1) factors.push(l1);
  if (l2) factors.push(l2);
  if (CROSS.has(m.leagueId) && (H.from !== A.from)) factors.push('Equipos de ligas distintas: la fuerza de cada uno se corrige por el nivel de su liga.');
  if (market) factors.push(`Mercado (${market.provider}): ${pct(market.pHome)} local · ${pct(market.pDraw)} empate · ${pct(market.pAway)} visitante.`);
  if (!m.neutral) factors.push('Factor campo: el local suele marcar alrededor de un 11 % más.');
  else factors.push('Campo neutral: sin ventaja de local.');
  if (!live && (fh !== 1 || fa !== 1)) factors.push(`Racha reciente: ${m.home.team.short} ${m.home.form ?? '—'} · ${m.away.team.short} ${m.away.form ?? '—'}.`);
  if (!hasHistory && statGames < 4) factors.push('Pocos partidos de referencia: confianza reducida.');

  const dcHome = pHome + pDraw, dcAway = pAway + pDraw;
  const doubleChance = pickProb < 0.5 ? (dcHome >= dcAway ? { label: '1X' as const, p: dcHome } : { label: 'X2' as const, p: dcAway }) : undefined;

  return {
    matchId: m.id,
    threeWay: true,
    pHome, pDraw, pAway, pick, pickProb,
    confidence: confidenceOf(pickProb, true, quality),
    score: likelyScoreFor(matrix, pick),
    expected: { home: sum.xgHome, away: sum.xgAway },
    market,
    model,
    soccer: { ...sum, matrix, lh: fitted.lh, la: fitted.la },
    totals: { line: 2.5, pOver: sum.pOver25, expected: sum.xgHome + sum.xgAway },
    doubleChance,
    factors,
    quality,
  };
}

/* --------------------------- EE. UU. (2 vías) --------------------------- */

const TOTAL_SIGMA: Record<string, number> = { basketball: 17, wnba: 15, football: 13.5, baseball: 3.3, hockey: 1.9 };

function predictUs(m: Match, ctx: PredictContext): Prediction {
  const key = m.leagueId === 'wnba' ? 'wnba' : m.sport;
  const p = US_PARAMS[key] as UsParams;
  const t = ctx.tables[m.leagueId];
  const avg = leagueAvgPoints(t?.current?.length ? t.current : t?.previous || [], p.avgPoints);
  const preseason = m.seasonType === 1;
  const hr = withoutResult(findRow(t?.current, m.home.team.id), m, 'home');
  const ar = withoutResult(findRow(t?.current, m.away.team.id), m, 'away');
  const H = ratingOf(hr, findRow(t?.previous, m.home.team.id), p, avg, !preseason);
  const A = ratingOf(ar, findRow(t?.previous, m.away.team.id), p, avg, !preseason);
  const hfa = m.neutral ? 0 : p.hfa;
  const mModel = H.margin - A.margin + hfa;
  const tModel = (H.off + A.def) / 2 + (A.off + H.def) / 2;
  const pModel = phi(mModel / p.sigma);

  const mk = m.odds ? devig([m.odds.home, m.odds.away]) : undefined;
  const market = mk ? { pHome: mk[0], pDraw: 0, pAway: mk[1], provider: m.odds!.provider } : undefined;
  const games = Math.min(H.games, A.games);
  const hasHistory = H.source !== 'media' && A.source !== 'media';
  const w = market ? (games >= 8 || hasHistory ? MARKET_WEIGHT : 0.75) : 0;
  const pHome = w * (market?.pHome ?? 0) + (1 - w) * pModel;
  const pAway = 1 - pHome;
  const margin = marginFor(pHome, p.sigma);
  const total = m.odds?.total !== undefined ? w * m.odds.total + (1 - w) * tModel : tModel;
  const eh = total / 2 + margin / 2;
  const ea = total / 2 - margin / 2;
  let sh = Math.round(eh), sa = Math.round(ea);
  if (sh === sa) {
    if (pHome >= 0.5) sh += 1;
    else sa += 1;
  }
  const pick: Outcome = pHome >= 0.5 ? 'home' : 'away';
  const pickProb = Math.max(pHome, pAway);
  const quality: Prediction['quality'] = market && (games >= 5 || hasHistory) ? 'buena' : market || games >= 5 || hasHistory ? 'media' : 'escasa';
  const factors: string[] = [];
  const unit = m.sport === 'baseball' ? 'carreras' : m.sport === 'hockey' ? 'goles' : 'puntos';
  const rec = (name: string, r?: TeamStats, rr?: string) =>
    r && r.gp > 0 ? `${name}: ${rr || `${r.w}-${r.l}`}, ${(r.gf - r.ga) >= 0 ? '+' : ''}${dec1((r.gf - r.ga) / r.gp)} ${unit} de diferencia por partido.` : undefined;
  if (!preseason) {
    const a = rec(m.home.team.short, hr, m.home.record);
    const b = rec(m.away.team.short, ar, m.away.record);
    if (a) factors.push(a);
    if (b) factors.push(b);
  } else {
    factors.push('Pretemporada: se usa sobre todo la temporada pasada y el mercado. Las rotaciones hacen estos partidos poco fiables.');
  }
  if (m.seasonType === 3 && m.series) factors.push(`Playoffs: ${m.series}.`);
  if (m.home.probable || m.away.probable) {
    const who = m.sport === 'baseball' ? 'Lanzadores probables' : 'Porteros probables';
    factors.push(`${who}: ${m.away.probable ?? '—'} (${m.away.team.abbr}) y ${m.home.probable ?? '—'} (${m.home.team.abbr}).`);
  }
  if (market) factors.push(`Mercado (${market.provider}): ${pct(market.pHome)} ${m.home.team.abbr} · ${pct(market.pAway)} ${m.away.team.abbr}${m.odds?.spread !== undefined ? `, hándicap local ${m.odds.spread > 0 ? '+' : ''}${m.odds.spread}` : ''}.`);
  if (!m.neutral) factors.push(`Ventaja de campo estimada: ${dec1(p.hfa)} ${unit}.`);
  else factors.push('Sede neutral: sin ventaja de campo.');

  return {
    matchId: m.id,
    threeWay: false,
    pHome, pDraw: 0, pAway, pick, pickProb,
    confidence: confidenceOf(pickProb, false, preseason ? 'escasa' : quality),
    score: { home: sh, away: sa },
    expected: { home: eh, away: ea },
    market,
    model: { pHome: pModel, pDraw: 0, pAway: 1 - pModel },
    totals: m.odds?.total !== undefined
      ? { line: m.odds.total, pOver: phi((total - m.odds.total) / TOTAL_SIGMA[key]), expected: total }
      : { line: Math.round(total * 2) / 2, pOver: 0.5, expected: total },
    spread: m.odds?.spread !== undefined ? { line: m.odds.spread, pCover: phi((margin + m.odds.spread) / p.sigma) } : undefined,
    us: { margin, total, sigma: p.sigma, sigmaTotal: TOTAL_SIGMA[key] },
    factors,
    quality: preseason ? 'escasa' : quality,
  };
}

/* -------------------------------- Tenis -------------------------------- */

function predictTennis(m: Match): Prediction {
  const pa = m.home.rankPoints ?? pointsFromRank(m.home.rank);
  const pb = m.away.rankPoints ?? pointsFromRank(m.away.rank);
  const pHome = tennisWinProb(pa, pb);
  const n = bestOf(m.leagueId, m.note);
  const sets = setScores(pHome, n);
  const fav = pHome >= 0.5 ? sets.find((s) => s.a > s.b)! : sets.find((s) => s.b > s.a)!;
  const pickProb = Math.max(pHome, 1 - pHome);
  const known = (m.home.rank ? 1 : 0) + (m.away.rank ? 1 : 0);
  const quality: Prediction['quality'] = known === 2 ? 'media' : 'escasa';
  const r = (s: typeof m.home) => (s.rank ? `n.º ${s.rank}${s.rankPoints ? ` (${s.rankPoints.toLocaleString('es-ES')} pts)` : ''}` : 'fuera del top 150');
  return {
    matchId: m.id,
    threeWay: false,
    pHome, pDraw: 0, pAway: 1 - pHome,
    pick: pHome >= 0.5 ? 'home' : 'away',
    pickProb,
    confidence: confidenceOf(pickProb, false, quality),
    score: { home: fav.a, away: fav.b },
    model: { pHome, pDraw: 0, pAway: 1 - pHome },
    tennis: { sets, bestOf: n },
    factors: [
      `${m.home.team.name}: ${r(m.home)}.`,
      `${m.away.team.name}: ${r(m.away)}.`,
      `Partido al mejor de ${n} sets${m.round ? `, ${m.round.toLowerCase()}` : ''}.`,
      'El modelo compara los puntos del ranking; no conoce lesiones ni superficie.',
    ],
    quality,
  };
}

export function predict(m: Match, ctx: PredictContext): Prediction {
  if (m.sport === 'soccer') return predictSoccer(m, ctx);
  if (m.sport === 'tennis') return predictTennis(m);
  return predictUs(m, ctx);
}

/** ¿Acertó el pronóstico? undefined si el partido no ha terminado. */
export function hit(m: Match, p: Prediction): boolean | undefined {
  if (!m.completed) return undefined;
  const actual = actualOutcome(m);
  return actual ? actual === p.pick : undefined;
}

export function actualOutcome(m: Match): Outcome | undefined {
  if (!m.completed) return undefined;
  if (m.sport === 'tennis') {
    if (m.home.winner) return 'home';
    if (m.away.winner) return 'away';
    return undefined;
  }
  if (m.home.score === undefined || m.away.score === undefined) return undefined;
  if (m.sport !== 'soccer') {
    if (m.home.winner) return 'home';
    if (m.away.winner) return 'away';
  }
  return m.home.score > m.away.score ? 'home' : m.home.score < m.away.score ? 'away' : 'draw';
}
