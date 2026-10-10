// Estadísticas de temporada por equipo (fútbol): córners, tarjetas, tiros a
// puerta, tiros y faltas, a favor y en contra, sumadas partido a partido desde
// los marcadores de ESPN. Alimentan los mercados de córners, tarjetas, etc.
import type { Match, MatchStats } from './types';

export type PropStat = 'corners' | 'cards' | 'sot' | 'shots' | 'fouls';
export const PROP_STATS: PropStat[] = ['corners', 'cards', 'sot', 'shots', 'fouls'];

type Rec = Record<PropStat, number>;
const zero = (): Rec => ({ corners: 0, cards: 0, sot: 0, shots: 0, fouls: 0 });

export interface TeamAgg {
  gp: number;
  /** Partidos con datos de tarjetas */
  cardGames: number;
  for: Rec;
  against: Rec;
  possession: number;
}

export interface LeagueAgg {
  leagueId: string;
  games: number;
  teams: Record<string, TeamAgg>;
  /** Media por equipo y partido */
  avg: Rec;
  /** Media del local dividida por la del visitante */
  homeRatio: Rec;
}

const DEFAULT_AVG: Rec = { corners: 4.8, cards: 2.2, sot: 4.3, shots: 12.5, fouls: 12 };

function value(s: MatchStats | undefined, k: PropStat): number | undefined {
  if (!s) return undefined;
  if (k === 'cards') return s.yellow === undefined ? undefined : s.yellow + (s.red ?? 0);
  return s[k];
}

export function aggregate(leagueId: string, matches: Match[]): LeagueAgg {
  const teams: Record<string, TeamAgg> = {};
  const homeSum = zero(), awaySum = zero(), cnt = zero();
  let games = 0;
  const seen = new Set<string>();
  for (const m of matches) {
    if (seen.has(m.id) || !m.completed || m.sport !== 'soccer' || !m.home.stats || !m.away.stats) continue;
    seen.add(m.id);
    games++;
    const sides = [
      { id: m.home.team.id, own: m.home.stats, opp: m.away.stats },
      { id: m.away.team.id, own: m.away.stats, opp: m.home.stats },
    ];
    for (const s of sides) {
      const t = (teams[s.id] ??= { gp: 0, cardGames: 0, for: zero(), against: zero(), possession: 0 });
      t.gp++;
      t.possession += s.own.possession ?? 50;
      if (value(s.own, 'cards') !== undefined) t.cardGames++;
      for (const k of PROP_STATS) {
        const a = value(s.own, k), b = value(s.opp, k);
        if (a !== undefined) t.for[k] += a;
        if (b !== undefined) t.against[k] += b;
      }
    }
    for (const k of PROP_STATS) {
      const h = value(m.home.stats, k), a = value(m.away.stats, k);
      if (h === undefined || a === undefined) continue;
      homeSum[k] += h;
      awaySum[k] += a;
      cnt[k]++;
    }
  }
  const avg = zero(), homeRatio = zero();
  for (const k of PROP_STATS) {
    avg[k] = cnt[k] >= 10 ? (homeSum[k] + awaySum[k]) / (2 * cnt[k]) : DEFAULT_AVG[k];
    homeRatio[k] = cnt[k] >= 20 && awaySum[k] > 0 ? Math.min(1.35, Math.max(0.8, homeSum[k] / awaySum[k])) : 1.1;
  }
  // Las tarjetas por partido dependen de cuántos partidos tienen datos de tarjetas.
  for (const t of Object.values(teams)) {
    if (t.cardGames < t.gp) {
      const f = t.cardGames ? t.gp / t.cardGames : 0;
      t.for.cards *= f;
      t.against.cards *= f;
    }
  }
  return { leagueId, games, teams, avg, homeRatio };
}
