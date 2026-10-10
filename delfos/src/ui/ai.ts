// Análisis en lenguaje natural con la capacidad `sample` del visor de
// Artifacts. Fuera de claude.ai no existe y el botón no se muestra.
import { LEAGUE_BY_ID } from '../data/leagues';
import type { Match } from '../data/types';
import type { Prediction } from '../model/predict';
import { longDate, timeOf } from './format';

interface SampleUpdate { text: string; delta: string }
type Sampler = ((input: string, opts?: { onText?: (u: SampleUpdate) => void; modelTier?: 'quick' | 'default' | 'complex'; cache?: boolean; signal?: AbortSignal }) => Promise<{ text: string }>);

let samplerPromise: Promise<Sampler | null> | null = null;

export function getSampler(): Promise<Sampler | null> {
  if (samplerPromise) return samplerPromise;
  const c = (window as unknown as { claude?: { use?: (n: string) => Promise<unknown> } }).claude;
  if (!c?.use) return (samplerPromise = Promise.resolve(null));
  samplerPromise = c.use('sample').then((s) => (typeof s === 'function' ? (s as Sampler) : null)).catch(() => null);
  return samplerPromise;
}

const p100 = (x: number) => `${Math.round(x * 100)}%`;

export function buildPrompt(m: Match, p: Prediction): string {
  const l = LEAGUE_BY_ID[m.leagueId];
  const lines = [
    `Competición: ${l?.name ?? m.leagueId}${m.round ? `, ${m.round}` : ''}${m.note ? ` (${m.note})` : ''}`,
    `Partido: ${m.home.team.name} (local) contra ${m.away.team.name} (visitante), ${longDate(m.start)} a las ${timeOf(m.start)}${m.venue ? `, ${m.venue}` : ''}.`,
    p.threeWay
      ? `Probabilidades Delfos: local ${p100(p.pHome)}, empate ${p100(p.pDraw)}, visitante ${p100(p.pAway)}.`
      : `Probabilidades Delfos: ${m.home.team.name} ${p100(p.pHome)}, ${m.away.team.name} ${p100(p.pAway)}.`,
    `Marcador más probable para el pronóstico: ${p.score.home}-${p.score.away}. Confianza: ${p.confidence}.`,
    p.market ? `Mercado (${p.market.provider}) sin margen: local ${p100(p.market.pHome)}${p.threeWay ? `, empate ${p100(p.market.pDraw)}` : ''}, visitante ${p100(p.market.pAway)}.` : 'Sin cuotas de mercado.',
    p.soccer ? `Goles esperados: ${p.soccer.xgHome.toFixed(2)} - ${p.soccer.xgAway.toFixed(2)}. Más de 2,5 goles: ${p100(p.soccer.pOver25)}. Ambos marcan: ${p100(p.soccer.pBtts)}.` : '',
    m.home.form || m.away.form ? `Racha (G/E/P en inglés W/D/L): ${m.home.team.name} ${m.home.form ?? 'n/d'}, ${m.away.team.name} ${m.away.form ?? 'n/d'}.` : '',
    m.home.probable || m.away.probable ? `Probables: ${m.home.probable ?? 'n/d'} y ${m.away.probable ?? 'n/d'}.` : '',
    m.series ? `Serie: ${m.series}.` : '',
    ...p.factors.map((f) => `Dato: ${f}`),
  ].filter(Boolean);
  return [
    'Eres el analista de Delfos, una app de pronósticos deportivos. Escribe en español de España un análisis previo del partido.',
    'Usa SOLO los datos de abajo; no inventes lesiones, alineaciones ni noticias. Si un dato no está, no lo menciones.',
    'Formato: tres párrafos breves (60-120 palabras en total). 1) Qué dice el modelo y por qué. 2) La clave del partido según los números. 3) Una lectura prudente del riesgo.',
    'No animes a apostar ni des consejos de apuesta. Sin títulos, sin listas, sin emojis.',
    '',
    ...lines,
  ].join('\n');
}
