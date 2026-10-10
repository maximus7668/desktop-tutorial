import type { Match, Outcome } from '../data/types';
import type { Bet } from '../model/bets';
import { americanToDecimal } from '../model/odds';
import type { Prediction } from '../model/predict';
import type { SlipPick } from '../state';
import { outcomeLabel } from './format';

const matchLabel = (m: Match) => `${m.home.team.short || m.home.team.name} – ${m.away.team.short || m.away.team.name}`;

const base = (m: Match) => ({ matchId: m.id, matchLabel: matchLabel(m), leagueId: m.leagueId, sport: m.sport, start: m.start });

export const mlKey = (o: Outcome) => `ml:${o}`;

/** Selección del ganador (1X2 o 1-2). */
export function slipPickFor(m: Match, p: Prediction, o: Outcome): SlipPick {
  const prob = o === 'home' ? p.pHome : o === 'draw' ? p.pDraw : p.pAway;
  const a = m.odds ? (o === 'home' ? m.odds.home : o === 'draw' ? m.odds.draw : m.odds.away) : undefined;
  return {
    ...base(m),
    key: mlKey(o),
    label: o === 'draw' ? 'Empate' : `Gana ${outcomeLabel(m, o)}`,
    prob,
    market: a !== undefined ? americanToDecimal(a) : undefined,
  };
}

/** Apuesta con cuota de mercado (recomendada o de la tabla de cuotas). */
export function slipPickForBet(m: Match, b: Bet): SlipPick {
  return { ...base(m), key: b.key, label: b.label, prob: b.prob, market: b.odds };
}

/** Mercado sin cuota de referencia (córners, tarjetas…): solo cuota justa. */
export function slipPickForProp(m: Match, key: string, label: string, prob: number): SlipPick {
  return { ...base(m), key, label, prob };
}
