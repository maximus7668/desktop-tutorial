// Simulación sin interfaz: la IA juega todas las naciones. Uso: node simulate.mjs [semilla] [jugador]
import { readFileSync } from 'fs';
import vm from 'vm';
const ctx = { console, Math, JSON, Date };
ctx.window = ctx;
vm.createContext(ctx);
for (const f of ['map.js', 'data.js', 'game.js', 'ai.js']) vm.runInContext(readFileSync(new URL('../js/' + f, import.meta.url), 'utf8'), ctx, { filename: f });
const { Game, AI } = ctx.window;
const seed = +(process.argv[2] || 1), player = process.argv[3] || 'ENG';
const verbose = process.argv.includes('-v');
Game.newGame(player, 'normal', seed);
const t0 = Date.now();
const majors = ['GER', 'ITA', 'ENG', 'FRA', 'SOV', 'USA'];
while (!Game.G.over) {
  AI.runAI(player);
  const before = Game.G.log.length;
  Game.endTurn(AI.runAI);
  const G = Game.G;
  if (verbose) for (const l of G.log.slice(before)) if (l.type !== 'battle') console.log('   ', l.text);
  const row = majors.map(n => n + ':' + Game.regionCount(n) + '/' + G.units.filter(u => u.n === n).length + (Game.faction(n) ? Game.faction(n)[1] : '-')).join(' ');
  console.log(Game.dateText(G.turn - 1).padEnd(22), row, 'u=' + G.units.length);
}
console.log('FIN', JSON.stringify(Game.G.over), 'ms', Date.now() - t0);
for (const f of ['AX', 'AL']) console.log(f, JSON.stringify(Game.factionVP(f)));
