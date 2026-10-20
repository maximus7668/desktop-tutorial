// Capturas del panel DEIKA con datos de ejemplo (negocio inventado), para el anuncio.
import { createRequire } from 'node:module';
const require = createRequire('/home/user/Deika-panel/package.json');
const { chromium } = require('playwright');
const OUT = new URL('./public/', import.meta.url).pathname; // cajas.json va luego a src/
const BASE = 'http://localhost:4173';

// Hoy: martes 20/10/2026, 11:47 en Madrid (UTC+2).
const iso = (dia, hm) => new Date(`2026-10-${String(dia).padStart(2, '0')}T${hm}:00+02:00`).toISOString();
const cita = (dia, ini, fin, cliente, servicio, notas = null) => ({ id: `c-${dia}-${ini}`, inicio: iso(dia, ini), fin: iso(dia, fin), titulo: servicio, servicio, cliente, telefono: '+34600000000', notas, estado: 'aceptada', tipoEventoId: 1 });
const relleno = (dia, n) => Array.from({ length: n }, (_, i) => cita(dia, `${String(9 + i).padStart(2, '0')}:00`, `${String(9 + i).padStart(2, '0')}:45`, 'Cliente', 'Corte'));
const CITAS = [
  ...relleno(19, 6),
  cita(20, '09:30', '10:15', 'Ana Ruiz', 'Corte y peinado'),
  cita(20, '10:30', '11:30', 'Pilar Sanz', 'Mechas'),
  cita(20, '12:30', '13:45', 'Lucía Gómez', 'Corte y color', 'Reservada por DEIKA por teléfono'),
  cita(20, '16:00', '17:00', 'Nerea Ortiz', 'Tinte'),
  cita(20, '17:00', '17:30', 'Javier Martín', 'Corte caballero', 'Reservada por DEIKA por WhatsApp'),
  cita(20, '18:30', '19:15', 'Irene Blanco', 'Peinado'),
  ...relleno(21, 5), ...relleno(22, 8), ...relleno(23, 9), ...relleno(24, 6),
];
const LLAMADAS = [
  { id: 'l1', fecha: iso(20, '11:32'), canal: 'llamada', cliente: 'Laura Pérez', telefono: '+34600000001', motivo: 'Cita para corte y color', detalle: null, cita: 'Jueves 22, 10:00 · Corte y color', resumen: 'Quería cita esta semana para corte y color. Le he dado el jueves a las 10:00 y ya está en tu agenda.', urgente: 0, duracion_seg: 74, devuelta: 0, devuelta_por: null },
  { id: 'l2', fecha: iso(20, '11:05'), canal: 'llamada', cliente: 'Raúl Castro', telefono: '+34600000002', motivo: 'Le pica la cabeza tras el tinte', detalle: null, cita: null, resumen: 'Se tiñó ayer aquí y hoy tiene el cuero cabelludo rojo y le pica. Quiere hablar con Marta cuanto antes.', urgente: 1, duracion_seg: 63, devuelta: 0, devuelta_por: null },
  { id: 'l3', fecha: iso(20, '10:41'), canal: 'whatsapp', cliente: 'Elena Moreno', telefono: '+34600000003', motivo: 'Precio de las mechas', detalle: null, cita: 'Sábado 24, 11:00 · Mechas', resumen: 'Preguntaba cuánto cuestan las mechas. Le he dicho 45 € y ha reservado el sábado a las 11:00.', urgente: 0, duracion_seg: 0, devuelta: 0, devuelta_por: null },
  { id: 'l4', fecha: iso(20, '10:12'), canal: 'llamada', cliente: null, telefono: null, motivo: 'Horario del sábado', detalle: null, cita: null, resumen: 'Preguntaba si abrimos el sábado. Le he dicho que de 9:00 a 14:00.', urgente: 0, duracion_seg: 28, devuelta: 0, devuelta_por: null },
  { id: 'l5', fecha: iso(20, '09:20'), canal: 'llamada', cliente: 'Carmen López', telefono: '+34600000005', motivo: 'Cambiar su cita del viernes', detalle: null, cita: 'Sábado 24, 12:00 · Corte', resumen: 'No puede venir el viernes. Su cita ha pasado al sábado a las 12:00.', urgente: 0, duracion_seg: 52, devuelta: 0, devuelta_por: null },
  { id: 'l6', fecha: iso(19, '19:48'), canal: 'llamada', cliente: 'Marcos Gil', telefono: '+34600000006', motivo: 'Cita para corte', detalle: null, cita: 'Miércoles 21, 17:30 · Corte caballero', resumen: 'Llamó con el salón cerrado. Le he dado cita el miércoles a las 17:30.', urgente: 0, duracion_seg: 47, devuelta: 0, devuelta_por: null },
  { id: 'l7', fecha: iso(19, '13:15'), canal: 'llamada', cliente: 'Rosa Díaz', telefono: '+34600000007', motivo: 'Anular su cita', detalle: null, cita: null, resumen: 'Anula la cita del martes. Le he ofrecido otro día y llamará ella.', urgente: 0, duracion_seg: 39, devuelta: 1, devuelta_por: 'Marta' },
];
const CONVERSACION = [
  { quien: 'DEIKA', texto: 'Peluquería Marta, buenas. Soy la asistente de IA, ¿en qué te ayudo?' },
  { quien: 'Cliente', texto: 'Hola, quería cita para corte y color esta semana.' },
  { quien: 'DEIKA', texto: 'Tengo el jueves a las 10:00 o el viernes a las 16:30. ¿Cuál prefieres?' },
  { quien: 'Cliente', texto: 'El jueves.' },
  { quien: 'DEIKA', texto: 'Perfecto, jueves a las 10:00. ¿Me dices tu nombre?' },
  { quien: 'Cliente', texto: 'Laura Pérez.' },
  { quien: 'DEIKA', texto: 'Apuntado, Laura. ¡Te esperamos!' },
];
const AVISOS = [
  { id: 'a1', tipo: 'reserva', titulo: 'Nueva cita', cuerpo: 'Laura Pérez · Corte y color · jueves 22, 10:00', fecha: iso(20, '11:33'), leido: 0 },
  { id: 'a2', tipo: 'llamada_urgente', titulo: 'Llamada urgente', cuerpo: 'Raúl Castro · Le pica la cabeza tras el tinte', fecha: iso(20, '11:06'), leido: 0 },
  { id: 'a3', tipo: 'reserva', titulo: 'Nueva cita', cuerpo: 'Elena Moreno · Mechas · sábado 24, 11:00', fecha: iso(20, '10:42'), leido: 1 },
  { id: 'a4', tipo: 'cambio', titulo: 'Cita cambiada', cuerpo: 'Carmen López · ahora el sábado 24, 12:00', fecha: iso(20, '09:21'), leido: 1 },
  { id: 'a5', tipo: 'anulacion', titulo: 'Cita anulada', cuerpo: 'Rosa Díaz · Corte · martes 20, 18:00', fecha: iso(19, '13:16'), leido: 1 },
];
const RECEP = {
  horarios: [{ dias: [0, 1, 2, 3, 4], tramos: [['09:30', '14:00'], ['16:00', '20:00']] }, { dias: [5], tramos: [['09:00', '14:00']] }],
  cerrados: [{ desde: '2026-11-01' }, { desde: '2026-12-08' }],
  servicios: [{ nombre: 'Corte', precio: '18 €' }, { nombre: 'Corte caballero', precio: '14 €' }, { nombre: 'Tinte', precio: '35 €' }, { nombre: 'Mechas', precio: '45 €' }, { nombre: 'Peinado', precio: '20 €' }],
  faq: [{ pregunta: '¿Hay que pedir cita?', respuesta: 'Sí, siempre con cita.' }, { pregunta: '¿Se puede pagar con tarjeta?', respuesta: 'Sí, y con Bizum.' }],
  avisos: '',
  actualizada: iso(18, '10:00'), conectada: true, peticiones: [], numero: null, asistente: 'DEIKA', sector: 'Peluquería',
};
const YO = { usuario: { nombre: 'Marta', email: 'marta@ejemplo.com', rol: 'dueño', viendo: false }, negocio: { nombre: 'Peluquería Marta', plan: 'Básico', recepcion_conectada: 1 }, avisosSinLeer: 2 };
const RESUMEN = { citasHoy: 6, proxima: { inicio: iso(20, '12:30'), cliente: 'Lucía Gómez', servicio: 'Corte y color' }, llamadasHoy: 9, porDevolver: 1, mes: { llamadas: 142, citas: 61, ticketMedio: 32, euros: 1952 } };

function responder(url) {
  const p = url.pathname;
  if (p === '/api/yo') return YO;
  if (p === '/api/resumen') return RESUMEN;
  if (p === '/api/citas') return { citas: CITAS, conectada: true };
  if (p === '/api/llamadas') {
    const f = url.searchParams.get('filtro');
    return { llamadas: LLAMADAS.filter((l) => (f === 'urgentes' ? l.urgente : f === 'pendientes' ? l.urgente && !l.devuelta : true)) };
  }
  if (/\/api\/llamadas\/[^/]+\/grabacion/.test(p)) return { audio: '/demo.wav', transcripcion: CONVERSACION };
  if (p === '/api/avisos') return { avisos: AVISOS };
  if (p === '/api/recepcionista') return RECEP;
  if (p.startsWith('/api/agenda/estado')) return { avisos: true };
  return {};
}

// Un segundo de silencio para que se vea el reproductor de la grabación.
const wav = (() => { const n = 8000, b = Buffer.alloc(44 + n); b.write('RIFF', 0); b.writeUInt32LE(36 + n, 4); b.write('WAVEfmt ', 8); b.writeUInt32LE(16, 16); b.writeUInt16LE(1, 20); b.writeUInt16LE(1, 22); b.writeUInt32LE(8000, 24); b.writeUInt32LE(8000, 28); b.writeUInt16LE(1, 32); b.writeUInt16LE(8, 34); b.write('data', 36); b.writeUInt32LE(n, 40); b.fill(128, 44); return b; })();

const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium', args: ['--lang=es-ES'] });
const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true, locale: 'es-ES', timezoneId: 'Europe/Madrid', colorScheme: 'light' });
await ctx.addInitScript(() => { try { localStorage.setItem('deika-instalar-cerrado', '1'); } catch {} });
await ctx.route('**/api/**', (r) => r.fulfill({ json: responder(new URL(r.request().url())) }));
await ctx.route('**/demo.wav', (r) => r.fulfill({ body: wav, contentType: 'audio/wav' }));
const page = await ctx.newPage();
await page.clock.install({ time: new Date('2026-10-20T11:47:00+02:00') });
const foto = async (nombre, full = false) => { await page.waitForTimeout(600); await page.screenshot({ path: `${OUT}${nombre}.png`, fullPage: full }); console.log('ok', nombre); };

await page.goto(`${BASE}/`); await page.waitForSelector('.resumen-hoy'); await page.waitForSelector('.cita');
await foto('agenda'); await foto('agenda-larga', true);
const cajas = {};
const caja = async (nombre, loc) => { const b = await loc.boundingBox(); cajas[nombre] = b; };
await caja('resumen', page.locator('.resumen-hoy'));
await page.evaluate(() => { const h = document.querySelector('.dia-titulo'); scrollTo(0, h.getBoundingClientRect().top + scrollY - 70); });
await foto('agenda-citas');
await caja('citaDeika', page.locator('.cita').nth(2));
await page.goto(`${BASE}/llamadas`); await page.waitForSelector('.llamada');
await foto('llamadas'); await caja('filaLaura', page.locator('.llamada .fila').first());

await page.locator('.llamada .fila').first().click(); await page.waitForSelector('.detalle');
await foto('llamada-abierta'); await caja('detalle', page.locator('.detalle').first());
await page.getByText('Escuchar la llamada y ver la conversación').click(); await page.waitForSelector('.conversacion');
await foto('llamada-conversacion'); await foto('llamada-conversacion-larga', true);
await page.locator('.llamada .fila').first().click();
await page.locator('.llamada .fila').nth(1).click(); await page.waitForSelector('.detalle');
await foto('llamada-urgente'); await caja('urgente', page.locator('.llamada.urgente'));
await page.goto(`${BASE}/avisos`); await page.waitForSelector('.aviso'); await page.waitForTimeout(500); await page.evaluate(() => document.querySelector('section > .tarjeta.info')?.remove());
await foto('avisos'); await foto('avisos-larga', true);
await page.goto(`${BASE}/recepcionista`); await page.waitForSelector('.tabla');
await foto('recepcion'); await caja('editar', page.getByRole('button', { name: 'Editar' }));
await foto('recepcion-larga', true);
await page.getByRole('button', { name: 'Editar' }).click(); await page.waitForSelector('.editor');
await foto('recepcion-editar'); await caja('horarioEdit', page.locator('.horario-edit').first()); await foto('recepcion-editar-larga', true);
require('node:fs').writeFileSync(OUT + 'cajas.json', JSON.stringify(cajas, null, 1));
await browser.close();
