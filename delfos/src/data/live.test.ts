// Prueba de integración contra ESPN real. Solo se ejecuta con LIVE=1:
//   LIVE=1 npx vitest run src/data/live.test.ts
import { describe, expect, it } from 'vitest';
import { dayKey, loadDay, loadF1, loadTables } from './source';
import { tablesNeeded } from '../state';
import { predict } from '../model/predict';

describe.runIf(process.env.LIVE)('ESPN en directo', () => {
  it('carga el día de hoy, sus clasificaciones y pronostica cada partido', async () => {
    const day = await loadDay(dayKey(new Date()));
    expect(day.matches.length).toBeGreaterThan(0);
    const tables = await loadTables(tablesNeeded(day.matches));
    let ok = 0;
    for (const m of day.matches) {
      const p = predict(m, { tables });
      expect(p.pHome + p.pDraw + p.pAway).toBeCloseTo(1, 5);
      ok++;
    }
    console.log(`${ok} partidos, ${Object.keys(tables).length} tablas, fallos: ${day.failed.join(', ') || 'ninguno'}`);
  }, 120_000);
  it('carga la Fórmula 1', async () => {
    const f1 = await loadF1();
    expect(f1?.drivers.length).toBeGreaterThan(10);
  }, 60_000);
});
