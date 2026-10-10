import { describe, expect, it } from 'vitest';
import type { Match } from '../data/types';
import { aggregate } from '../data/teamStats';
import { allBets, evaluate, recommendBet } from './bets';
import { predict } from './predict';
import { expectedCounts, goalExtras, nbPmf, overProb, propMarkets } from './props';
import { scoreMatrix } from './soccer';

const team = (id: string) => ({ id, name: id, short: id, abbr: id });
const base = (over: Partial<Match> = {}): Match => ({
  id: 'x', leagueId: 'esp.1', sport: 'soccer', start: '2026-10-10T19:00Z', status: 'pre', statusDetail: '',
  completed: false, neutral: false, home: { team: team('A') }, away: { team: team('B') }, ...over,
});
const row = (id: string, gp: number, gf: number, ga: number) => ({ teamId: id, name: id, abbr: id, gp, w: 0, d: 0, l: 0, otl: 0, gf, ga });

describe('binomial negativa', () => {
  it('suma 1 y tiene la media pedida', () => {
    for (const k of [3, 15, 1000]) {
      const p = nbPmf(9.5, k);
      expect(p.reduce((s, x) => s + x, 0)).toBeCloseTo(1, 4);
      expect(p.reduce((s, x, i) => s + x * i, 0)).toBeCloseTo(9.5, 1);
    }
  });
  it('es más dispersa que una Poisson', () => {
    expect(overProb(nbPmf(10, 5), 14.5)).toBeGreaterThan(overProb(nbPmf(10, 1000), 14.5));
  });
});

describe('estadísticas de equipo', () => {
  const played = (id: string, h: string, a: string, hc: number, ac: number): Match => base({
    id, completed: true, status: 'post', home: { team: team(h), score: 1, stats: { corners: hc, sot: 4, shots: 12, fouls: 11, yellow: 2, red: 0, possession: 50 } },
    away: { team: team(a), score: 0, stats: { corners: ac, sot: 3, shots: 10, fouls: 12, yellow: 3, red: 0, possession: 50 } },
  });
  const ms = Array.from({ length: 12 }, (_, i) => played(`m${i}`, i % 2 ? 'A' : 'C', i % 2 ? 'C' : 'B', i % 2 ? 8 : 4, i % 2 ? 3 : 5));
  const agg = aggregate('esp.1', ms);
  it('suma a favor y en contra', () => {
    expect(agg.games).toBe(12);
    expect(agg.teams.A.gp).toBe(6);
    expect(agg.teams.A.for.corners).toBe(48);
    expect(agg.teams.A.for.cards).toBe(12);
  });
  it('un equipo que saca muchos córners tiene más córners esperados', () => {
    const e = expectedCounts('corners', { agg: agg.teams.A, league: agg }, { agg: agg.teams.B, league: agg }, false);
    expect(e.home).toBeGreaterThan(e.away);
    const mk = propMarkets(base(), { agg: agg.teams.A, league: agg }, { agg: agg.teams.B, league: agg });
    const c = mk.find((x) => x.stat === 'corners')!;
    expect(c.more.home + c.more.draw + c.more.away).toBeCloseTo(1, 5);
    expect(c.totalLines[0].over).toBeGreaterThan(c.totalLines[c.totalLines.length - 1].over);
  });
});

describe('mercados de goles', () => {
  it('descanso/final y porterías a cero son coherentes', () => {
    const g = goalExtras(scoreMatrix(1.8, 0.9), 1.8, 0.9);
    expect(g.htft.reduce((s, x) => s + x.p, 0)).toBeCloseTo(1, 4);
    expect(g.half.pHome + g.half.pDraw + g.half.pAway).toBeCloseTo(1, 5);
    expect(g.cleanSheet.home).toBeGreaterThan(g.cleanSheet.away);
    expect(g.winToNil.home).toBeLessThan(g.cleanSheet.home);
  });
});

describe('apuesta recomendada', () => {
  it('calcula valor esperado y Kelly', () => {
    const b = evaluate({ key: 'k', market: 'm', label: 'l', prob: 0.55, push: 0, odds: 2.1 });
    expect(b.ev).toBeCloseTo(0.155, 3);
    expect(b.kelly).toBeCloseTo((0.55 * 1.1 - 0.45) / 1.1, 5);
    expect(b.stake).toBeLessThanOrEqual(2);
  });
  it('no recomienda nada sin cuotas y sí con una cuota generosa', () => {
    const tables = { 'esp.1': { leagueId: 'esp.1', season: '', current: [row('A', 8, 20, 5), row('B', 8, 6, 18)], previous: [] } };
    const m0 = base();
    expect(recommendBet(m0, predict(m0, { tables }))).toBeUndefined();
    const m1 = base({ odds: { provider: 'X', home: 150, draw: 300, away: 600, total: 2.5, over: -110, under: -110 } });
    const p1 = predict(m1, { tables });
    const bet = recommendBet(m1, p1);
    expect(bet).toBeDefined();
    expect(bet!.ev).toBeGreaterThanOrEqual(0.03);
    expect(allBets(m1, p1).length).toBe(5);
  });
});
