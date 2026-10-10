import type { Match, Outcome } from '../data/types';
import { addDays, dayKey, parseDayKey } from '../data/source';

const LOCALE = 'es-ES';

export const pct = (p: number, digits = 0) =>
  `${(p * 100).toLocaleString(LOCALE, { maximumFractionDigits: digits, minimumFractionDigits: digits })} %`;
export const pctNum = (p: number) => Math.round(p * 100);
export const dec = (x: number, digits = 1) =>
  x.toLocaleString(LOCALE, { maximumFractionDigits: digits, minimumFractionDigits: digits });
export const odds2 = (d: number) => (Number.isFinite(d) ? d.toLocaleString(LOCALE, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—');

export const timeOf = (iso: string) =>
  new Date(iso).toLocaleTimeString(LOCALE, { hour: '2-digit', minute: '2-digit' });

export const longDate = (iso: string) =>
  new Date(iso).toLocaleDateString(LOCALE, { weekday: 'long', day: 'numeric', month: 'long' });

export const dateTime = (iso: string) =>
  new Date(iso).toLocaleString(LOCALE, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

export function dayLabel(k: string, today = dayKey(new Date())): { top: string; bottom: string } {
  const d = parseDayKey(k);
  const num = d.toLocaleDateString(LOCALE, { day: 'numeric', month: 'short' }).replace('.', '');
  if (k === today) return { top: 'Hoy', bottom: num };
  if (k === addDays(today, 1)) return { top: 'Mañana', bottom: num };
  if (k === addDays(today, -1)) return { top: 'Ayer', bottom: num };
  const wd = d.toLocaleDateString(LOCALE, { weekday: 'short' }).replace('.', '');
  return { top: wd.charAt(0).toUpperCase() + wd.slice(1), bottom: num };
}

const ordinal = (n?: number) => (n ? `${n}.º` : '');

function baseballInning(detail: string): string {
  const m = /^(Top|Bot|Bottom|Mid|Middle|End)\s+(\d+)/i.exec(detail);
  if (!m) return detail;
  const map: Record<string, string> = { top: 'Alta', bot: 'Baja', bottom: 'Baja', mid: 'Mitad', middle: 'Mitad', end: 'Fin' };
  return `${map[m[1].toLowerCase()]} ${m[2]}.ª`;
}

/** Texto corto de estado: hora, minuto en juego o "Final". */
export function statusText(m: Match): { text: string; kind: 'pre' | 'live' | 'final' | 'off' } {
  const off = (d: string) => (/susp/i.test(d) ? 'Suspendido' : /cancel/i.test(d) ? 'Cancelado' : 'Aplazado');
  if (m.status === 'pre') {
    if (/postpon|cancel|susp/i.test(m.statusDetail)) return { text: off(m.statusDetail), kind: 'off' };
    return { text: m.timeTbd ? 'Por conf.' : timeOf(m.start), kind: 'pre' };
  }
  if (m.status === 'post') {
    if (!m.completed) return { text: off(m.statusDetail), kind: 'off' };
    const d = m.statusDetail || '';
    if (/pen/i.test(d)) return { text: 'Final (pen.)', kind: 'final' };
    if (/AET|OT|\/1\d|SO/i.test(d)) return { text: m.sport === 'baseball' ? 'Final (extra)' : 'Final (pró.)', kind: 'final' };
    return { text: 'Final', kind: 'final' };
  }
  const d = m.statusDetail || '';
  switch (m.sport) {
    case 'soccer':
      if (/HT|half/i.test(d)) return { text: 'Descanso', kind: 'live' };
      return { text: m.clock && m.clock !== "0'" ? m.clock : 'En juego', kind: 'live' };
    case 'basketball':
    case 'football':
      if (/half/i.test(d)) return { text: 'Descanso', kind: 'live' };
      return { text: `${ordinal(m.period)} C · ${m.clock ?? ''}`.trim(), kind: 'live' };
    case 'hockey':
      if (/end|int/i.test(d)) return { text: `Fin ${ordinal(m.period)} P`, kind: 'live' };
      return { text: `${ordinal(m.period)} P · ${m.clock ?? ''}`.trim(), kind: 'live' };
    case 'baseball':
      return { text: baseballInning(d), kind: 'live' };
    default:
      return { text: 'En juego', kind: 'live' };
  }
}

export const outcomeCode = (o: Outcome, threeWay: boolean) => (threeWay ? (o === 'home' ? '1' : o === 'draw' ? 'X' : '2') : o === 'home' ? 'L' : 'V');

export function outcomeLabel(m: Match, o: Outcome): string {
  if (o === 'draw') return 'Empate';
  const t = o === 'home' ? m.home.team : m.away.team;
  return t.short || t.name;
}

export function pickSentence(m: Match, o: Outcome): string {
  if (o === 'draw') return 'Empate';
  return `Gana ${outcomeLabel(m, o)}`;
}

export const plural = (n: number, one: string, many: string) => `${n.toLocaleString(LOCALE)} ${n === 1 ? one : many}`;
