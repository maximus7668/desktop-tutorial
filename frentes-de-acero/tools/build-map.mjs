// Genera js/map.js: regiones de Europa en 1939 a partir de Natural Earth (world-atlas).
// Uso: cd tools && npm install && node build-map.mjs
import { createRequire } from 'module';
import { writeFileSync } from 'fs';
import { SEEDS, SEA_LINKS } from './seeds.mjs';

const require = createRequire(import.meta.url);
const d3 = require('d3-geo');
const topojson = require('topojson-client');
const world = require('world-atlas/countries-50m.json');

const W = 460, H = 330;          // celdas de la cuadrícula
const S = 2;                      // unidades SVG por celda
const countries = topojson.feature(world, world.objects.countries).features;

const projection = d3.geoConicConformal().parallels([35, 65]).rotate([-20, 0]);
const frame = { type: 'MultiPoint', coordinates: [] };
for (let lon = -11; lon <= 52; lon += 1) frame.coordinates.push([lon, 29], [lon, 69.5]);
for (let lat = 29; lat <= 69.5; lat += 1) frame.coordinates.push([-11, lat], [52, lat]);
projection.fitExtent([[0, 0], [W, H]], frame);

// Nombre del país actual -> país de 1939 (con ajustes de fronteras por coordenadas)
function code1939(name, lon, lat) {
  if (lat < 29.3 && lon < 36) return 'X';
  if (lon > 58 || (lon > 54 && name === 'Iran')) return 'X';
  if ((name === 'Kazakhstan' && lat < 47) || name === 'Turkmenistan' || name === 'Uzbekistan') return 'X';
  switch (name) {
    case 'Germany': case 'Austria': case 'Czechia': case 'Slovakia': return 'GER';
    case 'Poland':
      if (lat > 53.3 && lon > 19.4) return 'GER';
      if (lon < 16.0) return 'GER';
      if (lat > 53.6 && lon < 17.6) return 'GER';
      if (lat < 51.0 && lon < 18.4) return 'GER';
      return 'POL';
    case 'Russia':
      if (lon < 23.5 && lat > 54 && lat < 55.5) return 'GER';
      if (lat > 60.2 && lat < 62.6 && lon < 29.3 + (lat - 60.2) * 1.4) return 'FIN';
      if (lat > 69 && lon < 31.5) return 'FIN';
      return 'SOV';
    case 'Lithuania':
      if (lon < 21.6 && lat > 55.3) return 'GER';
      if (lon > 24.6 && lat < 55.3) return 'POL';
      return 'LIT';
    case 'Belarus': return lon < 27.2 + Math.max(0, lat - 53) * 0.5 ? 'POL' : 'SOV';
    case 'Ukraine':
      if (lat < 48.7 && lon < 24.6) return 'HUN';
      if (lat < 48.4 && lon < 27.0) return 'ROM';
      if (lat < 46.5 && lon < 30.0) return 'ROM';
      if (lat > 48.3 && lon < 26.3 + (lat - 48.3) * 0.35) return 'POL';
      return 'SOV';
    case 'Moldova': return lon > 29.6 ? 'SOV' : 'ROM';
    case 'Slovenia': case 'Croatia': case 'Bosnia and Herz.': case 'Serbia': case 'Montenegro':
    case 'Kosovo': case 'Macedonia': return 'YUG';
    case 'Albania': return 'ITA';
    case 'Estonia': return 'EST';
    case 'Latvia': return 'LAT';
    case 'Finland': case 'Åland': return 'FIN';
    case 'Sweden': return 'SWE';
    case 'Norway': return 'NOR';
    case 'Denmark': return 'DEN';
    case 'Netherlands': return 'NED';
    case 'Belgium': case 'Luxembourg': return 'BEL';
    case 'France': case 'Monaco': return 'FRA';
    case 'United Kingdom': case 'Jersey': case 'Guernsey': case 'Isle of Man': case 'Malta': return 'ENG';
    case 'Ireland': return 'IRL';
    case 'Spain': case 'Andorra': return 'SPA';
    case 'Portugal': return 'POR';
    case 'Switzerland': case 'Liechtenstein': return 'SWI';
    case 'Italy': case 'San Marino': case 'Vatican': return 'ITA';
    case 'Hungary': return 'HUN';
    case 'Romania': return 'ROM';
    case 'Bulgaria': return 'BUL';
    case 'Greece': return 'GRE';
    case 'Turkey': return 'TUR';
    case 'Cyprus': case 'N. Cyprus': return 'ENG';
    case 'Syria': case 'Lebanon': return 'FRA';
    case 'Israel': case 'Palestine': case 'Jordan': case 'Iraq': case 'Kuwait': case 'Egypt': return 'ENG';
    case 'Libya': return 'ITA';
    case 'Tunisia': case 'Algeria': case 'Morocco': return 'FRA';
    case 'Iran': return 'IRN';
    case 'Georgia': case 'Armenia': case 'Azerbaijan': case 'Kazakhstan': case 'Turkmenistan':
    case 'Uzbekistan': return 'SOV';
    default: return 'X';
  }
}

// --- Rasterizar países ---
const feats = countries.map(f => ({ f, name: f.properties.name, b: d3.geoBounds(f) }))
  .filter(o => (o.b[0][0] > o.b[1][0] || (o.b[1][0] > -15 && o.b[0][0] < 60)) && o.b[1][1] > 25 && o.b[0][1] < 75);
console.log('países candidatos:', feats.length);
const cellCode = new Array(W * H).fill(null);
const cellLL = new Array(W * H);
let lastHit = null;
for (let y = 0; y < H; y++) {
  for (let x = 0; x < W; x++) {
    const ll = projection.invert([x + 0.5, y + 0.5]);
    cellLL[y * W + x] = ll;
    const [lon, lat] = ll;
    const inB = o => {
      const [[x0, y0], [x1, y1]] = o.b;
      const inLon = x0 <= x1 ? lon >= x0 && lon <= x1 : lon >= x0 || lon <= x1;
      return inLon && lat >= y0 && lat <= y1;
    };
    let hit = null;
    if (lastHit && inB(lastHit) && d3.geoContains(lastHit.f, ll)) hit = lastHit;
    else for (const o of feats) if (o !== lastHit && inB(o) && d3.geoContains(o.f, ll)) { hit = o; break; }
    if (hit) { lastHit = hit; cellCode[y * W + x] = code1939(hit.name, lon, lat); }
  }
  if (y % 30 === 0) console.log('fila', y);
}

// --- Asignar regiones (semilla más cercana del mismo país) ---
const seeds = SEEDS.map(([id, name, code, lon, lat, terrain, ind, vp, extra = {}], i) => {
  const [sx, sy] = projection([lon, lat]);
  return { i, id, name, code, lon, lat, terrain, ind, vp, port: !!extra.port, fort: extra.fort || 0, sx, sy };
});
const byCode = {};
for (const s of seeds) (byCode[s.code] ||= []).push(s);
const WASTE = -2, SEA = -1;
const cellReg = new Int32Array(W * H).fill(SEA);
for (let k = 0; k < W * H; k++) {
  const c = cellCode[k];
  if (c === null) continue;
  const list = byCode[c];
  if (!list) { cellReg[k] = WASTE; continue; }
  const x = k % W + 0.5, y = Math.floor(k / W) + 0.5;
  let best = null, bd = Infinity;
  for (const s of list) { const d = (s.sx - x) ** 2 + (s.sy - y) ** 2; if (d < bd) { bd = d; best = s; } }
  cellReg[k] = best.i;
}

// Quitar islotes: componentes de < 3 celdas pasan a mar (salvo que sean la única parte de la región)
{
  const seen = new Uint8Array(W * H);
  const comps = [];
  for (let k = 0; k < W * H; k++) {
    if (seen[k] || cellReg[k] === SEA) continue;
    const r = cellReg[k], stack = [k], cells = [];
    seen[k] = 1;
    while (stack.length) {
      const c = stack.pop(); cells.push(c);
      const x = c % W, y = (c - x) / W;
      for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
        const nx = x + dx, ny = y + dy;
        if (nx < 0 || ny < 0 || nx >= W || ny >= H) continue;
        const n = ny * W + nx;
        if (!seen[n] && cellReg[n] === r) { seen[n] = 1; stack.push(n); }
      }
    }
    comps.push({ r, cells });
  }
  const biggest = {};
  for (const c of comps) if (!biggest[c.r] || biggest[c.r] < c.cells.length) biggest[c.r] = c.cells.length;
  for (const c of comps) if (c.cells.length < 4 && c.cells.length < biggest[c.r]) for (const k of c.cells) cellReg[k] = SEA;
}

// --- Contorno de cada región ---
function tracePaths(test) {
  // aristas dirigidas (sentido horario) entre celdas dentro/fuera
  const edges = new Map(); // "x,y" -> lista de [x2,y2]
  const add = (x1, y1, x2, y2) => { const k = x1 + ',' + y1; if (!edges.has(k)) edges.set(k, []); edges.get(k).push([x2, y2]); };
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    if (!test(y * W + x)) continue;
    const inside = (xx, yy) => xx >= 0 && yy >= 0 && xx < W && yy < H && test(yy * W + xx);
    if (!inside(x, y - 1)) add(x, y, x + 1, y);
    if (!inside(x + 1, y)) add(x + 1, y, x + 1, y + 1);
    if (!inside(x, y + 1)) add(x + 1, y + 1, x, y + 1);
    if (!inside(x - 1, y)) add(x, y + 1, x, y);
  }
  const loops = [];
  for (const [start, outs] of edges) {
    while (outs.length) {
      let [cx, cy] = start.split(',').map(Number);
      const loop = [[cx, cy]];
      let next = outs.pop();
      while (true) {
        const [nx, ny] = next;
        const dir = [nx - cx, ny - cy];
        cx = nx; cy = ny;
        if (cx + ',' + cy === start) break;
        const list = edges.get(cx + ',' + cy);
        if (!list || !list.length) break;
        loop.push([cx, cy]);
        // en vértices con dos salidas, girar a la derecha
        let pick = 0;
        if (list.length > 1) {
          const right = [-dir[1], dir[0]];
          const idx = list.findIndex(([px, py]) => px - cx === right[0] && py - cy === right[1]);
          if (idx >= 0) pick = idx;
        }
        next = list.splice(pick, 1)[0];
      }
      if (loop.length > 2) loops.push(loop);
    }
  }
  return loops;
}
function simplify(loop) { // quitar puntos colineales
  const out = [];
  for (let i = 0; i < loop.length; i++) {
    const a = loop[(i - 1 + loop.length) % loop.length], b = loop[i], c = loop[(i + 1) % loop.length];
    if ((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]) !== 0) out.push(b);
  }
  return out;
}
function chaikin(pts, it) {
  for (let n = 0; n < it; n++) {
    const out = [];
    for (let i = 0; i < pts.length; i++) {
      const a = pts[i], b = pts[(i + 1) % pts.length];
      out.push([a[0] * 0.75 + b[0] * 0.25, a[1] * 0.75 + b[1] * 0.25], [a[0] * 0.25 + b[0] * 0.75, a[1] * 0.25 + b[1] * 0.75]);
    }
    pts = out;
  }
  return pts;
}
function toPath(loops) {
  return loops.map(l => chaikin(simplify(l), 2)).filter(l => l.length > 2)
    .map(l => 'M' + l.map(([x, y]) => (x * S).toFixed(1).replace('.0', '') + ' ' + (y * S).toFixed(1).replace('.0', '')).join('L') + 'Z').join('');
}

const regions = [];
for (const s of seeds) {
  let count = 0;
  for (let k = 0; k < W * H; k++) if (cellReg[k] === s.i) count++;
  if (!count) { console.warn('¡Región sin celdas!', s.id); continue; }
  const path = toPath(tracePaths(k => cellReg[k] === s.i));
  // punto de etiqueta: celda más alejada del borde
  const dist = new Int32Array(W * H).fill(-1);
  const q = [];
  for (let k = 0; k < W * H; k++) {
    if (cellReg[k] !== s.i) continue;
    const x = k % W, y = (k - x) / W;
    const edge = [[1, 0], [-1, 0], [0, 1], [0, -1]].some(([dx, dy]) => {
      const nx = x + dx, ny = y + dy;
      return nx < 0 || ny < 0 || nx >= W || ny >= H || cellReg[ny * W + nx] !== s.i;
    });
    if (edge) { dist[k] = 0; q.push(k); }
  }
  for (let h = 0; h < q.length; h++) {
    const k = q[h], x = k % W, y = (k - x) / W;
    for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      const nx = x + dx, ny = y + dy;
      if (nx < 0 || ny < 0 || nx >= W || ny >= H) continue;
      const n = ny * W + nx;
      if (cellReg[n] === s.i && dist[n] < 0) { dist[n] = dist[k] + 1; q.push(n); }
    }
  }
  let best = -1, bk = -1;
  for (let k = 0; k < W * H; k++) {
    if (dist[k] < 0) continue;
    const x = k % W + 0.5, y = Math.floor(k / W) + 0.5;
    const score = Math.min(dist[k], 7) * 100 - Math.hypot(x - s.sx, y - s.sy);
    if (score > best) { best = score; bk = k; }
  }
  const lx = (bk % W + 0.5) * S, ly = (Math.floor(bk / W) + 0.5) * S;
  // la ciudad debe quedar dentro de su región
  let cx = s.sx, cy = s.sy;
  const ck = Math.floor(cy) * W + Math.floor(cx);
  if (cellReg[ck] !== s.i) { cx = lx / S; cy = ly / S + 3; if (cellReg[Math.floor(cy) * W + Math.floor(cx)] !== s.i) cy -= 3; }
  regions.push({
    id: s.id, name: s.name, code: s.code, terrain: s.terrain, ind: s.ind, vp: s.vp,
    port: s.port ? 1 : 0, fort: s.fort, cells: count,
    lx: Math.round(lx), ly: Math.round(ly), cx: Math.round(cx * S), cy: Math.round(cy * S), path,
  });
}

// --- Adyacencias ---
const pairs = new Map();
for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
  const a = cellReg[y * W + x];
  if (a < 0) continue;
  for (const [dx, dy] of [[1, 0], [0, 1]]) {
    const nx = x + dx, ny = y + dy;
    if (nx >= W || ny >= H) continue;
    const b = cellReg[ny * W + nx];
    if (b < 0 || b === a) continue;
    const key = Math.min(a, b) + '-' + Math.max(a, b);
    pairs.set(key, (pairs.get(key) || 0) + 1);
  }
}
const adj = {};
for (const r of regions) adj[r.id] = [];
for (const [key, n] of pairs) {
  if (n < 2) continue;
  const [a, b] = key.split('-').map(Number);
  adj[seeds[a].id].push(seeds[b].id); adj[seeds[b].id].push(seeds[a].id);
}
const sea = [];
for (const [a, b] of SEA_LINKS) {
  if (!adj[a] || !adj[b]) { console.warn('paso marítimo inválido', a, b); continue; }
  if (adj[a].includes(b)) continue;
  sea.push([a, b]);
}
// avisar de regiones aisladas
for (const r of regions) if (!adj[r.id].length && !sea.some(p => p.includes(r.id))) console.warn('Región aislada:', r.id);

// --- Tierras no jugables y etiquetas de países ---
const waste = toPath(tracePaths(k => cellReg[k] === WASTE));
const coast = toPath(tracePaths(k => cellReg[k] !== SEA));
const countryLabels = {};
for (const r of regions) {
  const c = (countryLabels[r.code] ||= { x: 0, y: 0, n: 0 });
  c.x += r.lx * r.cells; c.y += r.ly * r.cells; c.n += r.cells;
}
for (const k in countryLabels) {
  const c = countryLabels[k];
  countryLabels[k] = { x: Math.round(c.x / c.n), y: Math.round(c.y / c.n), size: c.n };
}

// rejilla de meridianos y paralelos
const grat = [];
for (let lon = -10; lon <= 50; lon += 10) {
  const pts = []; for (let lat = 28; lat <= 71; lat += 1) pts.push(projection([lon, lat]));
  grat.push('M' + pts.map(([x, y]) => (x * S).toFixed(0) + ' ' + (y * S).toFixed(0)).join('L'));
}
for (let lat = 30; lat <= 70; lat += 10) {
  const pts = []; for (let lon = -15; lon <= 56; lon += 1) pts.push(projection([lon, lat]));
  grat.push('M' + pts.map(([x, y]) => (x * S).toFixed(0) + ' ' + (y * S).toFixed(0)).join('L'));
}

const out = { W: W * S, H: H * S, regions, adj, sea, waste, coast, grat: grat.join(''), countryLabels };
writeFileSync(new URL('../js/map.js', import.meta.url),
  '// Generado por tools/build-map.mjs a partir de Natural Earth (dominio público). No editar a mano.\n' +
  'window.MAP = ' + JSON.stringify(out) + ';\n');
console.log('regiones:', regions.length, 'pasos marítimos:', sea.length,
  'tamaño KB:', Math.round(JSON.stringify(out).length / 1024));
console.log('más pequeñas:', regions.slice().sort((a, b) => a.cells - b.cells).slice(0, 8).map(r => r.id + ':' + r.cells).join(' '));
