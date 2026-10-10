import { describe, expect, it } from 'vitest';
import { americanToDecimal, devig } from './odds';
import { fitLambdas, scoreMatrix, summarize, strengthOf, leagueAverages } from './soccer';
import { phi, marginFor } from './us';
import { setProbFromMatch, setScores, tennisWinProb } from './tennis';
import { simulateRace } from './f1';
import { predict, withoutResult, actualOutcome } from './predict';
import type { Match, TeamStats } from '../data/types';

const row = (id: string, gp: number, w: number, d: number, l: number, gf: number, ga: number): TeamStats => ({
  teamId: id, name: id, abbr: id, gp, w, d, l, otl: 0, gf, ga,
});

const match = (over: Partial<Match> = {}): Match => ({
  id: 'm1', leagueId: 'esp.1', sport: 'soccer', start: '2026-10-10T19:00Z', status: 'pre', statusDetail: '',
  completed: false, neutral: false,
  home: { team: { id: 'A', name: 'Equipo A', short: 'A', abbr: 'AAA' } },
  away: { team: { id: 'B', name: 'Equipo B', short: 'B', abbr: 'BBB' } },
  ...over,
});

describe('cuotas', () => {
  it('convierte cuotas americanas a decimales', () => {
    expect(americanToDecimal(150)).toBeCloseTo(2.5);
    expect(americanToDecimal(-200)).toBeCloseTo(1.5);
  });
  it('quita el margen y suma 1', () => {
    const p = devig([190, 275, 130])!;
    expect(p.reduce((s, x) => s + x, 0)).toBeCloseTo(1);
    expect(p[2]).toBeGreaterThan(p[0]);
  });
  it('rechaza cuotas incompletas', () => {
    expect(devig([150, undefined])).toBeUndefined();
  });
});

describe('fútbol', () => {
  it('la matriz suma 1 y el local favorito gana más', () => {
    const m = scoreMatrix(2.0, 0.8);
    const s = summarize(m);
    expect(s.pHome + s.pDraw + s.pAway).toBeCloseTo(1, 6);
    expect(s.pHome).toBeGreaterThan(0.6);
    expect(s.best.h).toBeGreaterThanOrEqual(s.best.a);
  });
  it('ajusta lambdas a un 1X2 objetivo', () => {
    const f = fitLambdas({ lh: 1.3, la: 1.1 }, { pHome: 0.55, pAway: 0.2 });
    const s = summarize(scoreMatrix(f.lh, f.la));
    expect(s.pHome).toBeCloseTo(0.55, 2);
    expect(s.pAway).toBeCloseTo(0.2, 2);
  });
  it('encoge la fuerza hacia el histórico al principio de temporada', () => {
    const avg = { mu: 1.4 };
    const early = strengthOf(row('A', 1, 1, 0, 0, 5, 0), undefined, avg);
    expect(early.att).toBeLessThan(2);
    expect(early.att).toBeGreaterThan(0.9);
  });
  it('un equipo claramente mejor es favorito', () => {
    const cur = [row('A', 8, 7, 1, 0, 22, 4), row('B', 8, 1, 2, 5, 6, 16), row('C', 8, 3, 2, 3, 10, 10)];
    const p = predict(match(), { tables: { 'esp.1': { leagueId: 'esp.1', season: '', current: cur, previous: [] } } });
    expect(p.pick).toBe('home');
    expect(p.pHome).toBeGreaterThan(0.6);
    expect(p.pHome + p.pDraw + p.pAway).toBeCloseTo(1, 6);
    expect(leagueAverages(cur).mu).toBeGreaterThan(1);
  });
  it('mezcla el mercado cuando hay cuotas', () => {
    const cur = [row('A', 8, 4, 2, 2, 12, 9), row('B', 8, 4, 2, 2, 12, 9)];
    const p = predict(match({ odds: { provider: 'X', home: 300, draw: 250, away: -120 } }), {
      tables: { 'esp.1': { leagueId: 'esp.1', season: '', current: cur, previous: [] } },
    });
    expect(p.market).toBeDefined();
    expect(p.pAway).toBeGreaterThan(p.model.pAway);
  });
  it('quita el propio resultado al evaluar partidos jugados', () => {
    const m = match({ completed: true, status: 'post', home: { team: { id: 'A', name: 'A', short: 'A', abbr: 'A' }, score: 3 }, away: { team: { id: 'B', name: 'B', short: 'B', abbr: 'B' }, score: 1 } });
    const r = withoutResult(row('A', 5, 4, 0, 1, 12, 4), m, 'home')!;
    expect(r.gp).toBe(4);
    expect(r.gf).toBe(9);
    expect(r.ga).toBe(3);
    expect(r.w).toBe(3);
    expect(actualOutcome(m)).toBe('home');
  });
});

describe('EE. UU.', () => {
  it('phi es simétrica', () => {
    expect(phi(0)).toBeCloseTo(0.5, 4);
    expect(phi(1) + phi(-1)).toBeCloseTo(1, 4);
    expect(marginFor(0.7, 13.5)).toBeCloseTo(13.5 * 0.5244, 1);
  });
  it('NFL: el mejor diferencial gana y no hay empates en el marcador', () => {
    const cur = [row('A', 4, 4, 0, 0, 118, 77), row('B', 4, 1, 0, 3, 70, 100)];
    const p = predict(match({ sport: 'football', leagueId: 'nfl' }), { tables: { nfl: { leagueId: 'nfl', season: '', current: cur, previous: [] } } });
    expect(p.pick).toBe('home');
    expect(p.score.home).not.toBe(p.score.away);
    expect(p.pDraw).toBe(0);
  });
});

describe('tenis', () => {
  it('el mejor ranking es favorito con límites', () => {
    expect(tennisWinProb(11000, 1000)).toBeGreaterThan(0.85);
    expect(tennisWinProb(11000, 10)).toBeLessThanOrEqual(0.92);
  });
  it('los sets son coherentes con el partido', () => {
    const ps = setProbFromMatch(0.7, 3);
    expect(ps * ps * (3 - 2 * ps)).toBeCloseTo(0.7, 4);
    const s = setScores(0.7, 3);
    expect(s.reduce((x, y) => x + y.p, 0)).toBeCloseTo(1, 6);
  });
});

describe('F1', () => {
  it('el líder con mejor forma es el favorito', () => {
    const d = (id: string, pts: number[]) => ({ id, name: id, short: id, abbr: id, rank: 1, points: pts.reduce((s, x) => s + x, 0), perRace: pts });
    const res = simulateRace({ drivers: [d('A', [25, 25, 18, 25]), d('B', [10, 8, 12, 6]), d('C', [1, 0, 2, 0])], constructors: [] }, 4000);
    expect(res[0].driver.id).toBe('A');
    expect(res.reduce((s, r) => s + r.win, 0)).toBeCloseTo(1, 6);
  });
});
