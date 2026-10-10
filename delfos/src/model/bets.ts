// Apuesta recomendada: de todos los mercados con cuota real (1X2, hándicap y
// totales), la selección cuyo precio paga más de lo que vale según Delfos.
// Valor esperado = probabilidad × cuota − 1. El stake sale de un cuarto de
// Kelly, con tope del 2 % de la banca.
import type { Match } from '../data/types';
import { americanToDecimal, devig } from './odds';
import { MARKET_WEIGHT, type Prediction } from './predict';
import { phi } from './us';

export interface BetOption {
  /** Identificador estable: "ml:home", "total:over:2.5", "spread:away:-1.5"… */
  key: string;
  market: string;
  label: string;
  prob: number;
  /** Probabilidad de que se devuelva lo apostado (líneas enteras) */
  push: number;
  /** Cuota decimal del mercado */
  odds: number;
}

export interface Bet extends BetOption {
  ev: number;
  /** Fracción de Kelly completa */
  kelly: number;
  /** Stake sugerido en % de la banca */
  stake: number;
  implied: number;
  /** Cuota mínima a partir de la cual hay valor */
  minOdds: number;
}

export const MIN_EV = 0.04;
export const MIN_PROB = 0.33;
export const MAX_ODDS = 4.5;
export const KELLY_FRACTION = 0.25;
export const MAX_STAKE = 2;

const fmt = (x: number) => x.toLocaleString('es-ES');
const signed = (x: number) => `${x > 0 ? '+' : x < 0 ? '−' : ''}${fmt(Math.abs(x))}`;

function unitOf(m: Match) {
  return m.sport === 'soccer' ? 'goles' : m.sport === 'baseball' ? 'carreras' : m.sport === 'hockey' ? 'goles' : 'puntos';
}

/** Probabilidad de cubrir un hándicap en fútbol a partir de la matriz de marcadores. */
function soccerCover(matrix: number[][], side: 'home' | 'away', line: number) {
  let win = 0, push = 0;
  for (let i = 0; i < matrix.length; i++) {
    for (let j = 0; j < matrix[i].length; j++) {
      const diff = (side === 'home' ? i - j : j - i) + line;
      if (Math.abs(diff) < 1e-9) push += matrix[i][j];
      else if (diff > 0) win += matrix[i][j];
    }
  }
  return { win, push };
}

function soccerOver(matrix: number[][], line: number) {
  let over = 0, push = 0;
  for (let i = 0; i < matrix.length; i++) {
    for (let j = 0; j < matrix[i].length; j++) {
      const t = i + j;
      if (Math.abs(t - line) < 1e-9) push += matrix[i][j];
      else if (t > line) over += matrix[i][j];
    }
  }
  return { over, under: Math.max(0, 1 - over - push), push };
}

/** Líneas asiáticas de cuarto (±0,25, ±0,75) no se modelan. */
const supported = (line: number) => Number.isInteger(line * 2);

export function betOptions(m: Match, p: Prediction): BetOption[] {
  const o = m.odds;
  if (!o) return [];
  const out: BetOption[] = [];
  const dec = (a?: number) => (a === undefined ? undefined : americanToDecimal(a));
  const add = (key: string, market: string, label: string, prob: number, push: number, a?: number) => {
    const d = dec(a);
    if (d && d > 1.01 && prob > 0) out.push({ key, market, label, prob, push, odds: d });
  };
  /**
   * Los hándicaps y los totales que el modelo no ha ajustado al mercado se
   * mezclan con la probabilidad sin margen de su propio par de cuotas, con el
   * mismo peso que el 1X2. Así una diferencia del modelo no se convierte sola
   * en un "valor" exagerado.
   */
  const blendPair = (a: number, b: number, oddsA?: number, oddsB?: number, push = 0) => {
    const mk = devig([oddsA, oddsB]);
    if (!mk) return [a, b];
    const free = 1 - push;
    return [
      MARKET_WEIGHT * mk[0] * free + (1 - MARKET_WEIGHT) * a,
      MARKET_WEIGHT * mk[1] * free + (1 - MARKET_WEIGHT) * b,
    ];
  };
  const home = m.home.team.short || m.home.team.name;
  const away = m.away.team.short || m.away.team.name;
  const unit = unitOf(m);

  add('ml:home', 'Ganador', `Gana ${home}`, p.pHome, 0, o.home);
  add('ml:away', 'Ganador', `Gana ${away}`, p.pAway, 0, o.away);
  if (p.threeWay) add('ml:draw', 'Ganador', 'Empate', p.pDraw, 0, o.draw);

  if (p.soccer) {
    const mx = p.soccer.matrix;
    if (o.total !== undefined && supported(o.total)) {
      const t = soccerOver(mx, o.total);
      // La línea de 2,5 ya entra en el ajuste del modelo; las demás se mezclan aquí.
      const [ov, un] = o.total === 2.5 ? [t.over, t.under] : blendPair(t.over, t.under, o.over, o.under, t.push);
      add(`total:over:${o.total}`, 'Goles', `Más de ${fmt(o.total)} goles`, ov, t.push, o.over);
      add(`total:under:${o.total}`, 'Goles', `Menos de ${fmt(o.total)} goles`, un, t.push, o.under);
    }
    const hl = o.spreadHomeLine, al = o.spreadAwayLine;
    if (hl !== undefined && al !== undefined && supported(hl) && supported(al)) {
      const ch = soccerCover(mx, 'home', hl);
      const ca = soccerCover(mx, 'away', al);
      const [ph, pa] = Math.abs(hl + al) < 1e-9 ? blendPair(ch.win, ca.win, o.spreadHomeOdds, o.spreadAwayOdds, ch.push) : [ch.win, ca.win];
      const what = (line: number) => (line === 0.5 ? ' (gana o empata)' : line === -0.5 ? ' (gana)' : line <= -1.5 ? ` (gana por ${Math.ceil(-line)} o más)` : '');
      add(`spread:home:${hl}`, 'Hándicap', `${home} ${signed(hl)}${what(hl)}`, ph, ch.push, o.spreadHomeOdds);
      add(`spread:away:${al}`, 'Hándicap', `${away} ${signed(al)}${what(al)}`, pa, ca.push, o.spreadAwayOdds);
    }
  } else if (p.us) {
    const { margin, total, sigma, sigmaTotal } = p.us;
    if (o.total !== undefined) {
      const pOver = phi((total - o.total) / sigmaTotal);
      const [ov, un] = blendPair(pOver, 1 - pOver, o.over, o.under);
      add(`total:over:${o.total}`, 'Total', `Más de ${fmt(o.total)} ${unit}`, ov, 0, o.over);
      add(`total:under:${o.total}`, 'Total', `Menos de ${fmt(o.total)} ${unit}`, un, 0, o.under);
    }
    const hl = o.spreadHomeLine ?? o.spread;
    if (hl !== undefined) {
      // La normal reparte mal los partidos de un gol (prórrogas en la NHL): el mercado manda aquí.
      const pCover = phi((margin + hl) / sigma);
      const [ph, pa] = blendPair(pCover, 1 - pCover, o.spreadHomeOdds, o.spreadAwayOdds);
      add(`spread:home:${hl}`, 'Hándicap', `${home} ${signed(hl)}`, ph, 0, o.spreadHomeOdds);
      add(`spread:away:${-hl}`, 'Hándicap', `${away} ${signed(o.spreadAwayLine ?? -hl)}`, pa, 0, o.spreadAwayOdds);
    }
  }
  return out;
}

export function evaluate(b: BetOption): Bet {
  const lose = Math.max(0, 1 - b.prob - b.push);
  const ev = b.prob * b.odds + b.push - 1;
  const kelly = Math.max(0, (b.prob * (b.odds - 1) - lose) / (b.odds - 1));
  const stake = Math.min(MAX_STAKE, Math.round(KELLY_FRACTION * kelly * 100 * 4) / 4);
  // Cuota con la que el valor esperado sería +3 %.
  const minOdds = b.prob > 0 ? (1 + MIN_EV - b.push) / b.prob : Infinity;
  return { ...b, ev, kelly, stake, implied: 1 / b.odds, minOdds };
}

/** ¿Cumple esta apuesta los requisitos para recomendarse? */
export const qualifies = (b: Bet) => b.ev >= MIN_EV && b.prob >= MIN_PROB && b.odds <= MAX_ODDS && b.stake > 0;

/** Mejor apuesta del partido, o undefined si ninguna cuota ofrece valor suficiente. */
export function recommendBet(m: Match, p: Prediction): Bet | undefined {
  if (m.status !== 'pre' || p.quality === 'escasa' || m.seasonType === 1) return undefined;
  const bets = betOptions(m, p)
    .map(evaluate)
    .filter(qualifies);
  // Kelly ya equilibra valor y probabilidad: favorece ventajas claras a cuotas razonables.
  bets.sort((a, b) => b.kelly - a.kelly);
  return bets[0];
}

/** Todas las opciones con cuota, evaluadas y ordenadas por valor esperado. */
export function allBets(m: Match, p: Prediction): Bet[] {
  return betOptions(m, p).map(evaluate).sort((a, b) => b.ev - a.ev);
}

/** Lectura del valor para la interfaz. */
export function valueLevel(b: Bet): 'alto' | 'medio' | 'ajustado' {
  return b.ev >= 0.1 ? 'alto' : b.ev >= 0.06 ? 'medio' : 'ajustado';
}
