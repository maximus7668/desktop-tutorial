// Colores de equipo para las barras de probabilidad: se usan los colores
// reales de cada club, corregidos para que se distingan entre sí y del fondo.

function hexToRgb(hex: string): [number, number, number] | undefined {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return undefined;
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

const lin = (c: number) => {
  const s = c / 255;
  return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
};

/** RGB -> OKLab */
function oklab([r, g, b]: [number, number, number]): [number, number, number] {
  const R = lin(r), G = lin(g), B = lin(b);
  const l = Math.cbrt(0.4122214708 * R + 0.5363325363 * G + 0.0514459929 * B);
  const m = Math.cbrt(0.2119034982 * R + 0.6806995451 * G + 0.1073969566 * B);
  const s = Math.cbrt(0.0883024619 * R + 0.2817188376 * G + 0.6299787005 * B);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
}

const dist = (a: string, b: string) => {
  const x = hexToRgb(a), y = hexToRgb(b);
  if (!x || !y) return 1;
  const p = oklab(x), q = oklab(y);
  return Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]);
};

const lightness = (hex: string) => {
  const c = hexToRgb(hex);
  return c ? oklab(c)[0] : 0.5;
};

/** Mezcla hacia blanco o negro hasta que el color se vea sobre el fondo. */
function visible(hex: string, dark: boolean): string {
  const L = lightness(hex);
  const c = hexToRgb(hex);
  if (!c) return hex;
  if (!dark && L > 0.86) return mix(c, [40, 48, 66], 0.78);
  if (dark && L < 0.3) return mix(c, [235, 240, 248], 0.5);
  return hex;
}

function mix(a: [number, number, number], b: [number, number, number], t: number): string {
  const v = a.map((x, i) => Math.round(x + (b[i] - x) * t));
  return `#${v.map((x) => x.toString(16).padStart(2, '0')).join('')}`;
}

const FALLBACK_HOME = '#2F55D4';
const FALLBACK_AWAY = '#E0892B';
/** Gris del empate en cada tema: los equipos no deben confundirse con él. */
const DRAW = { light: '#a3abbb', dark: '#5f6982' };

/** ¿Sirve este color tal cual sobre el fondo y frente al gris del empate? */
function usable(hex: string | undefined, dark: boolean): hex is string {
  if (!hex || !hexToRgb(hex)) return false;
  const L = lightness(hex);
  if (!dark && L > 0.86) return false;
  if (dark && L < 0.32) return false;
  return dist(hex, dark ? DRAW.dark : DRAW.light) > 0.09;
}

export function railColors(
  home: { color?: string; alt?: string },
  away: { color?: string; alt?: string },
  dark: boolean,
): { home: string; away: string } {
  const h = [home.color, home.alt].find((c) => usable(c, dark)) ?? (home.color ? visible(home.color, dark) : FALLBACK_HOME);
  const options = [away.color, away.alt].filter((c): c is string => usable(c, dark));
  const a = options.find((c) => dist(h, c) > 0.12)
    ?? [FALLBACK_AWAY, FALLBACK_HOME, '#1FA37A'].find((c) => dist(h, c) > 0.12)
    ?? '#7A8396';
  return { home: h, away: a };
}

/** Tinta legible (blanca o casi negra) sobre un color de relleno. */
export const inkOn = (hex: string) => (lightness(hex) > 0.68 ? '#0C1322' : '#FFFFFF');
