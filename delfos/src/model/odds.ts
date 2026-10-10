/** Cuota americana -> decimal (europea). */
export function americanToDecimal(a: number): number {
  return a > 0 ? 1 + a / 100 : 1 + 100 / Math.abs(a);
}

/** Probabilidad implícita de una cuota decimal. */
export const implied = (decimal: number) => 1 / decimal;

/**
 * Quita el margen de la casa repartiéndolo en proporción (método básico).
 * Devuelve probabilidades que suman 1, o undefined si falta alguna cuota.
 */
export function devig(americans: (number | undefined)[]): number[] | undefined {
  if (americans.some((a) => a === undefined)) return undefined;
  const raw = (americans as number[]).map((a) => implied(americanToDecimal(a)));
  const sum = raw.reduce((s, x) => s + x, 0);
  if (!(sum > 0.9 && sum < 1.4)) return undefined;
  return raw.map((x) => x / sum);
}

/** Cuota justa (sin margen) para una probabilidad. */
export const fairDecimal = (p: number) => (p > 0 ? 1 / p : Infinity);

export const formatDecimal = (d: number) => (Number.isFinite(d) ? d.toFixed(2) : '—');
