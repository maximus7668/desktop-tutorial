import type { Match, Outcome } from '../data/types';
import { americanToDecimal } from '../model/odds';
import type { Prediction } from '../model/predict';
import type { SlipPick } from '../state';
import { outcomeLabel } from './format';

export function slipPickFor(m: Match, p: Prediction, o: Outcome | 'over' | 'under' | 'btts'): SlipPick {
  let prob = 0;
  let label = '';
  let market: number | undefined;
  if (o === 'home' || o === 'draw' || o === 'away') {
    prob = o === 'home' ? p.pHome : o === 'draw' ? p.pDraw : p.pAway;
    label = o === 'draw' ? 'Empate' : `Gana ${outcomeLabel(m, o)}`;
    const a = m.odds ? (o === 'home' ? m.odds.home : o === 'draw' ? m.odds.draw : m.odds.away) : undefined;
    market = a !== undefined ? americanToDecimal(a) : undefined;
  } else if (o === 'over' || o === 'under') {
    const t = p.totals!;
    prob = o === 'over' ? t.pOver : 1 - t.pOver;
    const line = t.line.toLocaleString('es-ES');
    label = `${o === 'over' ? 'Más' : 'Menos'} de ${line}`;
    const a = o === 'over' ? m.odds?.over : m.odds?.under;
    market = a !== undefined && m.odds?.total === t.line ? americanToDecimal(a) : undefined;
  } else {
    prob = p.soccer?.pBtts ?? 0;
    label = 'Ambos marcan';
  }
  return {
    matchId: m.id,
    outcome: o,
    label,
    matchLabel: `${m.home.team.short || m.home.team.name} – ${m.away.team.short || m.away.team.name}`,
    leagueId: m.leagueId,
    sport: m.sport,
    start: m.start,
    prob,
    market,
  };
}
