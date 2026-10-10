// Fórmula 1: fuerza de cada piloto según puntos por carrera (con más peso a
// las últimas) y lo que ya ha pasado en el fin de semana (libres, sprint,
// clasificación). Se simulan carreras con un modelo de Plackett-Luce.
import type { Driver, F1Data } from '../data/types';

export interface DriverOdds {
  driver: Driver;
  win: number;
  podium: number;
  points: number;
  expected: number;
  strength: number;
  grid?: number;
}

const SESSION_WEIGHT: Record<string, number> = {
  FP1: 0.15,
  FP2: 0.2,
  FP3: 0.25,
  SS: 0.45,
  SR: 0.6,
  Qual: 1.6,
};

/** Generador pseudoaleatorio con semilla (resultados estables entre recargas). */
function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function driverStrengths(data: F1Data): { driver: Driver; theta: number; grid?: number }[] {
  const sessions = data.race?.sessions || [];
  const done = sessions.filter((s) => s.status === 'post' && s.type !== 'Race' && s.order.length > 0);
  const qual = done.find((s) => s.type === 'Qual');
  return data.drivers
    .filter((d) => d.perRace.length > 0 || done.some((s) => s.order.includes(d.id)))
    .map((d) => {
      const races = d.perRace;
      const season = races.length ? races.reduce((s, x) => s + x, 0) / races.length : 0;
      const last = races.slice(-5);
      const wsum = last.reduce((s, _x, i) => s + (i + 1), 0) || 1;
      const recent = last.reduce((s, x, i) => s + x * (i + 1), 0) / wsum;
      const base = 0.45 * season + 0.55 * recent;
      let theta = Math.log(base + 1.2);
      for (const s of done) {
        const pos = s.order.indexOf(d.id);
        const w = SESSION_WEIGHT[s.type] ?? 0.1;
        if (pos >= 0) theta += w * -0.09 * pos;
        else theta += w * -0.09 * 15;
      }
      const grid = qual ? qual.order.indexOf(d.id) + 1 || undefined : undefined;
      return { driver: d, theta, grid };
    });
}

export function simulateRace(data: F1Data, runs = 12000, seed = 7): DriverOdds[] {
  const list = driverStrengths(data);
  const n = list.length;
  if (n === 0) return [];
  const rnd = mulberry32(seed);
  const win = new Float64Array(n), pod = new Float64Array(n), pts = new Float64Array(n), pos = new Float64Array(n);
  const keys = new Float64Array(n);
  const idx = new Array<number>(n);
  // Más contraste entre pilotos: las carreras son bastante previsibles.
  const scale = 1.5;
  // Abandonos: alrededor de un 7 % por piloto y carrera.
  const dnf = 0.07;
  for (let r = 0; r < runs; r++) {
    // Plackett-Luce con el truco de Gumbel: ordenar por theta + Gumbel.
    for (let i = 0; i < n; i++) {
      keys[i] = scale * list[i].theta - Math.log(-Math.log(rnd() || 1e-12));
      if (rnd() < dnf) keys[i] -= 1e6;
      idx[i] = i;
    }
    idx.sort((a, b) => keys[b] - keys[a]);
    for (let k = 0; k < n; k++) {
      const i = idx[k];
      if (k === 0) win[i]++;
      if (k < 3) pod[i]++;
      if (k < 10) pts[i]++;
      pos[i] += k + 1;
    }
  }
  return list
    .map((x, i) => ({
      driver: x.driver,
      win: win[i] / runs,
      podium: pod[i] / runs,
      points: pts[i] / runs,
      expected: pos[i] / runs,
      strength: x.theta,
      grid: x.grid,
    }))
    .sort((a, b) => b.win - a.win || a.expected - b.expected);
}
