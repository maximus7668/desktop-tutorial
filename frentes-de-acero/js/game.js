// Motor del juego: estado, reglas, combate, economía y eventos. Sin DOM (se puede simular en Node).
(function () {
  const M = window.MAP, D = window.DATA;
  const { AX, AL } = D;
  const REG = {};
  M.regions.forEach(r => { REG[r.id] = r; });
  const RIDS = M.regions.map(r => r.id);
  const LAND = M.adj;
  const SEA = {};
  RIDS.forEach(id => { SEA[id] = []; });
  M.sea.forEach(([a, b]) => { SEA[a].push(b); SEA[b].push(a); });

  const MONTHS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
  const START_Y = 1939, START_M = 9;
  const LAST_TURN = 72; // agosto de 1945

  const UNIT = {
    inf: { name: 'Infantería', atk: 2, def: 3, mv: 1, pp: 10, mp: 3 },
    arm: { name: 'Blindados', atk: 5, def: 3, mv: 2, pp: 25, mp: 2 },
  };
  const AIR_COST = 15;
  const TERRAIN = {
    p: { name: 'Llanura', def: 1, arm: 1 },
    f: { name: 'Bosque', def: 1.25, arm: 0.8 },
    m: { name: 'Montaña', def: 1.6, arm: 0.6 },
    w: { name: 'Pantano', def: 1.4, arm: 0.5 },
    d: { name: 'Desierto', def: 1, arm: 1.15 },
  };
  const DIFF = {
    facil: { name: 'Fácil', player: 1.2, aiPP: 0.85, thr: 0.68 },
    normal: { name: 'Normal', player: 1, aiPP: 1, thr: 0.6 },
    dificil: { name: 'Difícil', player: 0.9, aiPP: 1.15, thr: 0.54 },
  };
  const UK_HOME = ['londres', 'portsmouth', 'cornualles', 'anglia', 'midlands', 'gales', 'manchester', 'newcastle', 'glasgow', 'highlands', 'belfast'];
  const SOV_SPHERE = ['vilna', 'pinsk', 'volinia', 'lwow', 'bialystok'];
  const VICHY = ['lyon', 'marsella', 'toulouse', 'limoges', 'macizo', 'alpes', 'corcega', 'dijon', 'burdeos'];
  const ITALY_NORTH = ['milan', 'turin', 'venecia', 'bolonia', 'florencia', 'roma', 'abruzos', 'albania', 'cerdena'];
  const K = 2.2; // cuanto mayor, menos azar en las batallas
  const STACK = 12; // máximo de unidades de un bando en una región

  let G = null;
  const cache = { unitIdx: null, supply: {}, ownerVer: -1 };

  // ---------- utilidades ----------
  function rand() { // generador con semilla guardada en la partida (mulberry32)
    let t = G.rngState = (G.rngState + 0x6D2B79F5) | 0;
    t = Math.imul(t ^ t >>> 15, 1 | t);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  }
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const N = n => G.nations[n];
  const nname = n => D.nations[n] ? D.nations[n].name : n;
  const dateIdxOf = s => { const [y, m] = s.split('-').map(Number); return (y - START_Y) * 12 + (m - START_M); };
  const dateIdx = () => G.turn;
  function dateOf(turn) { const t = START_M - 1 + turn; return { y: START_Y + Math.floor(t / 12), m: t % 12 + 1 }; }
  function dateText(turn = G.turn) { const d = dateOf(turn); return MONTHS[d.m - 1] + ' de ' + d.y; }
  function isWinter(turn = G.turn) { const m = dateOf(turn).m; return m === 12 || m === 1 || m === 2; }

  function log(text, type = 'info', who = []) { G.log.push({ i: (G.logSeq = (G.logSeq || 0) + 1), t: G.turn, text, type, who }); if (G.log.length > 600) G.log.splice(0, 100); }
  function popup(ev) { G.popups.push(ev); }

  // ---------- consultas ----------
  function alive(n) {
    if (!G.nations[n] || N(n).capitulated) return false;
    if (n === 'USA') return !!N(n).faction;
    return regionCount(n) > 0;
  }
  function regionCount(n) { let c = 0; for (const id of RIDS) if (G.owner[id] === n) c++; return c; }
  function faction(n) { return G.nations[n] ? N(n).faction : null; }
  function atWar(a, b) { const fa = faction(a), fb = faction(b); return !!(fa && fb && fa !== fb); }
  function friendlyNations(a, b) { return a === b || (!!faction(a) && faction(a) === faction(b)); }
  function friendly(n, r) { return friendlyNations(n, G.owner[r]); }
  function enemyOf(n, r) { return atWar(n, G.owner[r]); }

  function unitIdx() {
    if (!cache.unitIdx) {
      cache.unitIdx = {};
      for (const u of G.units) (cache.unitIdx[u.r] ||= []).push(u);
    }
    return cache.unitIdx;
  }
  const dirtyUnits = () => { cache.unitIdx = null; };
  const unitsAt = r => unitIdx()[r] || [];
  const unitById = id => G.units.find(u => u.id === id);

  function supplyKey(n) { return faction(n) || ('N:' + n); }
  function supplySet(n) {
    if (cache.ownerVer !== G.ownerVer) { cache.supply = {}; cache.ownerVer = G.ownerVer; }
    const key = supplyKey(n);
    if (cache.supply[key]) return cache.supply[key];
    const members = faction(n) ? Object.keys(G.nations).filter(m => faction(m) === faction(n)) : [n];
    const isMember = r => members.includes(G.owner[r]);
    const set = new Set(), q = [];
    for (const r of RIDS) {
      if (!isMember(r)) continue;
      const cap = members.some(m => N(m).capital === r);
      if (cap || REG[r].port) { set.add(r); q.push(r); }
    }
    for (let i = 0; i < q.length; i++) {
      for (const nb of LAND[q[i]].concat(SEA[q[i]])) if (!set.has(nb) && isMember(nb)) { set.add(nb); q.push(nb); }
    }
    cache.supply[key] = set;
    return set;
  }
  const inSupply = (n, r) => supplySet(n).has(r);

  function mod(n, key) {
    const nat = N(n);
    let v = 1 + (nat.mods[key] || 0);
    for (const t of nat.timed) if (t.key === key) v += t.val;
    return v;
  }
  function hasTimed(n, key) { return N(n).timed.some(t => t.key === key); }

  // ---------- estado inicial ----------
  function newGame(player, difficulty = 'normal', seed = Date.now()) {
    G = {
      v: 1, turn: 0, player, difficulty, nations: {}, owner: {}, units: [], nextId: 1, fort: {}, indMod: {},
      log: [], fired: {}, battles: [], popups: [], over: null, ownerVer: 0, rngState: Math.abs(seed | 0) % 2147483647 || 1,
      stats: { won: 0, lost: 0, captured: 0, destroyed: 0, lostUnits: 0 },
    };
    cache.unitIdx = null; cache.supply = {}; cache.ownerVer = -1;
    for (const code in D.nations) {
      const d = D.nations[code];
      G.nations[code] = {
        faction: d.faction, capital: d.capital, pp: d.pp || 0, mp: d.mp || 0, air: d.air || 0,
        mods: { atk: 0, def: 0, arm: 0, pp: 0, mp: 0, ppFlat: 0 }, timed: [], flags: {}, focus: null, done: [],
        capitulated: false, lastIncome: 0,
      };
    }
    N('SOV').mods.atk = -0.25; // purgas
    N('SOV').mods.pp = -0.2;
    N('ENG').mods.pp = -0.2; // la Royal Navy se lleva gran parte de la industria británica // economía desorganizada hasta el Plan Quinquenal
    N('GER').mods.atk = 0.15; N('GER').mods.def = 0.2; // mejor doctrina y mando
    for (const r of M.regions) { G.owner[r.id] = r.code; G.fort[r.id] = r.fort || 0; }
    for (const code in D.deploy) for (const r in D.deploy[code]) {
      const [i, a] = D.deploy[code][r];
      for (let k = 0; k < i; k++) addUnit(code, 'inf', r, true);
      for (let k = 0; k < a; k++) addUnit(code, 'arm', r, true);
    }
    for (const code in D.autoDeploy) {
      const regs = M.regions.filter(r => r.code === code).sort((a, b) => (b.id === N(code).capital) - (a.id === N(code).capital) || b.vp - a.vp);
      for (let k = 0; k < D.autoDeploy[code]; k++) addUnit(code, 'inf', regs[k % regs.length].id, true);
    }
    log('1 de septiembre de 1939: Alemania invade Polonia. El Reino Unido y Francia le declaran la guerra.', 'event', ['GER', 'POL', 'ENG', 'FRA']);
    return G;
  }

  function addUnit(n, t, r, ready) {
    const u = { id: G.nextId++, n, t, r, s: 100, mv: ready ? UNIT[t].mv : 0 };
    G.units.push(u); dirtyUnits();
    return u;
  }
  function removeUnit(u, why = 'otro') {
    G.units.splice(G.units.indexOf(u), 1); dirtyUnits();
    const l = (G.losses ||= {})[u.n] ||= {};
    l[why] = (l[why] || 0) + 1;
  }

  function setOwner(r, n) {
    if (G.owner[r] === n) return;
    G.owner[r] = n; G.ownerVer++;
  }

  // ---------- economía ----------
  function industry(r) { return REG[r].ind + (G.indMod[r] || 0); }
  function income(n) {
    const nat = N(n);
    if (n === 'USA') {
      if (!nat.faction) return 0;
      const t = G.turn;
      return t < dateIdxOf('1942-06') ? 18 : t < dateIdxOf('1943-06') ? 32 : 45;
    }
    let ind = 0;
    for (const r of RIDS) if (G.owner[r] === n) ind += REG[r].code === n ? industry(r) : industry(r) * 0.6;
    let v = (ind + (D.nations[n].major ? 4 : 1)) * (mod(n, 'pp') + mobilization(n)) + (nat.mods.ppFlat || 0);
    if (n === G.player) v *= DIFF[G.difficulty].player;
    else v *= DIFF[G.difficulty].aiPP;
    return Math.round(v);
  }
  // Movilización total: las potencias que pierden su territorio se vuelcan en la guerra
  function coreRatio(n) {
    const core = M.regions.filter(r => r.code === n);
    if (!core.length) return 1;
    const total = core.reduce((s, r) => s + r.vp + 1, 0);
    return core.filter(r => friendly(n, r.id)).reduce((s, r) => s + r.vp + 1, 0) / total;
  }
  function mobilization(n) { return D.nations[n].major && faction(n) ? Math.min(0.5, (1 - coreRatio(n)) * 0.8) : 0; }
  function mpIncome(n) {
    const d = D.nations[n];
    if (n === 'USA') return N(n).faction ? 15 : 0;
    const core = M.regions.filter(r => r.code === n);
    const held = core.filter(r => G.owner[r.id] === n).length;
    const ratio = core.length ? held / core.length : 1;
    return Math.round(d.mpInc * (mod(n, 'mp') + mobilization(n)) * (0.3 + 0.7 * ratio) * 10) / 10;
  }

  function canBuild(n, t, r) {
    const nat = N(n);
    if (t === 'air') return nat.pp >= AIR_COST ? { ok: true } : { ok: false, reason: 'Necesitas ' + AIR_COST + ' de producción.' };
    const c = UNIT[t];
    if (nat.pp < c.pp) return { ok: false, reason: 'Necesitas ' + c.pp + ' de producción.' };
    if (nat.mp < c.mp) return { ok: false, reason: 'Necesitas ' + c.mp + ' reclutas.' };
    if (r && !deployable(n, r)) return { ok: false, reason: 'Solo puedes desplegar en tus regiones con suministro.' };
    return { ok: true };
  }
  function stackCount(n, r) { return unitsAt(r).filter(u => friendlyNations(u.n, n)).length; }
  function room(n, r) { return STACK - stackCount(n, r); }
  function deployable(n, r) { return G.owner[r] === n && inSupply(n, r) && room(n, r) > 0; }
  function defaultDeploy(n) {
    const cap = N(n).capital;
    if (cap && deployable(n, cap)) return cap;
    return RIDS.find(r => deployable(n, r)) || null;
  }
  function build(n, t, r) {
    const chk = canBuild(n, t, r);
    if (!chk.ok) return chk;
    const nat = N(n);
    if (t === 'air') { nat.pp -= AIR_COST; nat.air += 1; return { ok: true }; }
    r = r || defaultDeploy(n);
    if (n === 'USA') r = r || usaLanding();
    if (!r) return { ok: false, reason: 'No tienes dónde desplegar.' };
    nat.pp -= UNIT[t].pp; nat.mp -= UNIT[t].mp;
    addUnit(n, t, r, false);
    return { ok: true, r };
  }
  function usaLanding() {
    for (const r of ['londres', 'portsmouth', 'anglia', 'midlands', 'manchester', 'gales', 'casablanca', 'argel', 'alejandria']) if (friendly('USA', r) && inSupply('USA', r) && room('USA', r) > 0) return r;
    return RIDS.find(r => friendly('USA', r) && REG[r].port && room('USA', r) > 0) || null;
  }

  // ---------- movimiento ----------
  function reachable(n, from) { // regiones alcanzables por ferrocarril/transporte a través de territorio propio o aliado
    const set = new Set([from]), q = [from];
    for (let i = 0; i < q.length; i++) {
      for (const nb of LAND[q[i]].concat(SEA[q[i]])) if (!set.has(nb) && friendly(n, nb)) { set.add(nb); q.push(nb); }
    }
    return set;
  }
  // ¿Qué pasa si las unidades `units` (todas en la misma región) van a `to`?
  function moveKind(units, to) {
    if (!units.length) return { ok: false, reason: 'Selecciona unidades.' };
    const from = units[0].r, n = units[0].n;
    if (to === from) return { ok: false, reason: '' };
    const land = LAND[from].includes(to), sea = SEA[from].includes(to);
    const owner = G.owner[to];
    const full = units.every(u => u.mv >= UNIT[u.t].mv);
    const anyMv = units.every(u => u.mv > 0);
    if (!friendly(n, to) && !atWar(n, owner)) {
      if (land || sea) return { ok: false, kind: 'neutral', reason: nname(owner) + ' es neutral. Debes declararle la guerra para entrar.' };
      return { ok: false, reason: 'Territorio neutral.' };
    }
    if (friendly(n, to) && room(n, to) < units.length) return { ok: false, reason: 'Región llena: máximo ' + STACK + ' unidades por región.' };
    if (friendly(n, to)) {
      if (land) return anyMv ? { ok: true, kind: 'move' } : { ok: false, reason: 'Estas unidades ya no pueden moverse este turno.' };
      if (!full) return { ok: false, reason: 'Los traslados largos o por mar necesitan unidades que no se hayan movido.' };
      if (sea && friendly(n, from)) return { ok: true, kind: 'sea' };
      if (reachable(n, from).has(to)) return { ok: true, kind: 'rail' };
      return { ok: false, reason: 'No hay camino por territorio amigo.' };
    }
    // enemigo
    if (!land && !sea) return { ok: false, reason: 'Solo puedes atacar regiones vecinas.' };
    if (sea && !land && !full) return { ok: false, reason: 'Un desembarco necesita unidades que no se hayan movido.' };
    if (!anyMv) return { ok: false, reason: 'Estas unidades ya no pueden moverse este turno.' };
    const defenders = unitsAt(to);
    return { ok: true, kind: defenders.length ? 'attack' : 'occupy', amphib: !land };
  }
  function moveUnits(ids, to) {
    const units = ids.map(unitById).filter(Boolean);
    const k = moveKind(units, to);
    if (!k.ok) return k;
    if (k.kind === 'attack') return { ok: false, reason: 'Usa attack()' };
    for (const u of units) {
      u.r = to;
      u.mv = k.kind === 'move' ? u.mv - 1 : 0; // ocupar territorio enemigo detiene el avance
    }
    dirtyUnits();
    if (k.kind === 'occupy') {
      const prev = G.owner[to];
      capture(to, units[0].n);
      log(nname(units[0].n) + ' ocupa ' + REG[to].name + ' sin resistencia.', 'battle', [units[0].n, prev]);
    }
    return { ok: true, kind: k.kind };
  }

  // ---------- combate ----------
  function battleOdds(attackers, target) {
    const t = REG[target];
    const defenders = unitsAt(target);
    const atkN = attackers[0].n;
    const defOwner = G.owner[target];
    const fA = [], fD = [];
    let A = 0, Dp = 0;
    const amphibUnits = attackers.filter(u => !LAND[u.r].includes(target));
    const winter = isWinter() && ['SOV', 'FIN'].includes(t.code) && !['SOV', 'FIN'].includes(atkN);
    const air = 1 + 0.25 * (N(atkN).air - N(defOwner).air) / (N(atkN).air + N(defOwner).air + 4);
    for (const u of attackers) {
      let v = UNIT[u.t].atk * u.s / 100 * mod(u.n, 'atk');
      if (u.t === 'arm') v *= TERRAIN[t.terrain].arm * mod(u.n, 'arm');
      if (!inSupply(u.n, u.r)) v *= 0.5;
      if (amphibUnits.includes(u)) v *= amphibMult(u.n, target);
      if (winter) v *= 0.6;
      v *= distMult(u);
      v *= air;
      if (u.n === G.player) v *= DIFF[G.difficulty].player;
      A += v;
    }
    const terr = TERRAIN[t.terrain].def, fort = 1 + 0.25 * (G.fort[target] || 0);
    for (const u of defenders) {
      let v = UNIT[u.t].def * u.s / 100 * mod(u.n, 'def') * terr * fort;
      if (t.code === u.n) v *= 1.15;
      if (!inSupply(u.n, target)) v *= 0.5;
      if (u.n === G.player) v *= DIFF[G.difficulty].player;
      Dp += v;
    }
    // explicación para el jugador
    if (terr !== 1) fD.push(['Terreno: ' + TERRAIN[t.terrain].name, terr]);
    if (fort > 1) fD.push(['Fortificaciones nivel ' + G.fort[target], fort]);
    const armUnits = attackers.filter(u => u.t === 'arm');
    if (armUnits.length && TERRAIN[t.terrain].arm !== 1) fA.push(['Blindados en ' + TERRAIN[t.terrain].name.toLowerCase(), TERRAIN[t.terrain].arm]);
    if (amphibUnits.length) fA.push([hasTimed(atkN, 'amphib') ? 'Desembarco preparado' : (UK_HOME.includes(target) && !N(atkN).flags.sealion ? 'Desembarco contra la Royal Navy' : 'Desembarco desde el mar'),
      amphibMult(atkN, target)]);
    if (winter) fA.push(['Invierno ruso', 0.6]);
    const dm = Math.min(...attackers.map(distMult));
    if (dm < 1) fA.push(['Lejos de casa: ' + homeDist(atkN, attackers.find(u => distMult(u) === dm).r) + ' regiones', dm]);
    if (defenders.some(u => u.n === t.code)) fD.push(['Defienden su patria', 1.15]);
    if (Math.abs(air - 1) > 0.01) fA.push([air > 1 ? 'Superioridad aérea' : 'Inferioridad aérea', air]);
    if (attackers.some(u => !inSupply(u.n, u.r))) fA.push(['Atacantes sin suministro', 0.5]);
    if (defenders.length && !inSupply(defenders[0].n, target)) fD.push(['Defensores sin suministro', 0.5]);
    const ma = mod(atkN, 'atk'); if (Math.abs(ma - 1) > 0.01) fA.push([ma > 1 ? 'Bonificaciones de ataque' : 'Penalización de ataque', ma]);
    if (defenders.length) { const md = mod(defenders[0].n, 'def'); if (Math.abs(md - 1) > 0.01) fD.push([md > 1 ? 'Bonificaciones de defensa' : 'Defensa debilitada', md]); }
    const p = Dp <= 0 ? 1 : A ** K / (A ** K + Dp ** K);
    return { A, D: Dp, p, fA, fD, defenders, amphib: amphibUnits.length > 0 };
  }

  // Distancia (en regiones) desde el territorio nacional propio o aliado: cuanto más lejos, peor suministro
  function homeDist(n, r) {
    const key = (faction(n) || n) + ':' + G.turn;
    let d = cache.dist && cache.dist[key];
    if (!d) {
      d = {};
      const q = [];
      for (const id of RIDS) if (friendlyNations(REG[id].code, n) && alive(REG[id].code)) { d[id] = 0; q.push(id); }
      for (let i = 0; i < q.length; i++) for (const nb of LAND[q[i]].concat(SEA[q[i]])) if (d[nb] === undefined) { d[nb] = d[q[i]] + 1; q.push(nb); }
      (cache.dist ||= {})[key] = d;
    }
    return d[r] === undefined ? 10 : d[r];
  }
  function distMult(u) { return clamp(1 - 0.05 * homeDist(u.n, u.r), 0.6, 1); }

  function amphibMult(n, target) {
    if (hasTimed(n, 'amphib')) return 0.8;
    return UK_HOME.includes(target) && !N(n).flags.sealion && faction(n) !== faction('ENG') ? 0.25 : 0.4;
  }

  function retreatTarget(units, from, attackerN) {
    const n = units[0].n;
    let best = null, bs = -1;
    for (const nb of LAND[from]) {
      if (!friendly(n, nb) || room(n, nb) < units.length) continue;
      const s = unitsAt(nb).filter(u => friendlyNations(u.n, n)).length * 2 + (inSupply(n, nb) ? 3 : 0) + rand();
      if (s > bs) { bs = s; best = nb; }
    }
    if (!best && REG[from].port) for (const nb of SEA[from]) if (friendly(n, nb)) { best = nb; break; }
    return best;
  }

  function breakout(n, from) {
    const seen = new Set([from]), q = [from];
    for (let i = 0; i < q.length && i < 60; i++) {
      for (const nb of LAND[q[i]]) {
        if (seen.has(nb)) continue;
        seen.add(nb);
        if (friendly(n, nb)) return nb;
        if (!atWar(n, G.owner[nb]) && G.owner[nb] !== n) continue; // no se cruza territorio neutral
        q.push(nb);
      }
    }
    return null;
  }

  function attack(ids, target) {
    const units = ids.map(unitById).filter(u => u && u.mv > 0);
    if (!units.length) return { ok: false, reason: 'No hay unidades disponibles.' };
    const atkN = units[0].n;
    if (!atWar(atkN, G.owner[target])) return { ok: false, reason: 'No estás en guerra con ' + nname(G.owner[target]) + '.' };
    const odds = battleOdds(units, target);
    const defOwner = G.owner[target];
    if (!odds.defenders.length) { moveUnits(ids, target); return { ok: true, win: true, p: 1, occupied: true }; }
    const win = rand() < odds.p;
    const q = odds.A / Math.max(odds.D, 0.01);
    const res = { ok: true, win, p: odds.p, target, attacker: atkN, defender: defOwner, attLoss: 0, defLoss: 0, attDestroyed: 0, defDestroyed: 0, encircled: 0, brokeOut: 0, retreatTo: null };
    const hit = (u, amount) => { const d = Math.min(u.s, Math.round(amount)); u.s -= d; return d; };
    if (win) {
      for (const u of odds.defenders) res.defLoss += hit(u, 25 + 25 * clamp((q - 1) / 2, 0, 1) + rand() * 10);
      for (const u of units) res.attLoss += hit(u, clamp(6 + 12 / Math.max(q, 0.5), 6, 30) + rand() * 6);
    } else {
      for (const u of units) res.attLoss += hit(u, 18 + 12 * clamp(1 / Math.max(q, 0.1) - 1, 0, 1) + rand() * 12);
      for (const u of odds.defenders) res.defLoss += hit(u, 5 + 10 * clamp(q, 0, 1) + rand() * 5);
    }
    for (const u of units.slice()) if (u.s <= 5) { removeUnit(u, 'batalla'); res.attDestroyed++; }
    for (const u of odds.defenders.slice()) if (u.s <= 5) { removeUnit(u, 'batalla'); res.defDestroyed++; }
    const aliveAtt = units.filter(u => G.units.includes(u));
    if (win) {
      const defs = unitsAt(target).slice();
      if (defs.length) {
        const to = retreatTarget(defs, target, atkN);
        if (to) { for (const u of defs) { u.r = to; u.mv = 0; } res.retreatTo = to; }
        else {
          // rodeadas: intentan romper el cerco hacia la región amiga más cercana con grandes pérdidas
          const esc = breakout(defs[0].n, target);
          for (const u of defs) {
            u.s -= 35;
            if (u.s <= 5 || !esc) { removeUnit(u, 'cerco'); res.encircled++; } else { u.r = esc; u.mv = 0; res.brokeOut++; }
          }
        }
        dirtyUnits();
      }
      aliveAtt.forEach((u, i) => { if (i < STACK) u.r = target; u.mv = 0; });
      dirtyUnits();
      if (aliveAtt.length) capture(target, atkN);
    } else {
      for (const u of aliveAtt) u.mv = 0;
    }
    G.battles.push({ r: target, turn: G.turn, win, att: atkN, def: defOwner });
    const who = [atkN, defOwner];
    const txt = nname(atkN) + (win ? ' conquista ' : ' fracasa al atacar ') + REG[target].name + ' (' + nname(defOwner) + ')' +
      (res.encircled ? '. ¡' + res.encircled + ' unidades rodeadas y destruidas!' : '') +
      (res.brokeOut ? '. ' + res.brokeOut + ' unidades rompen el cerco con grandes pérdidas.' : '');
    log(txt, 'battle', who);
    if (atkN === G.player) { win ? G.stats.won++ : G.stats.lost++; G.stats.destroyed += res.defDestroyed + res.encircled; G.stats.lostUnits += res.attDestroyed; }
    if (defOwner === G.player) { G.stats.destroyed += res.attDestroyed; G.stats.lostUnits += res.defDestroyed + res.encircled; }
    return res;
  }

  function capture(r, n) {
    const prev = G.owner[r];
    const core = REG[r].code;
    let to = n;
    if (core !== n && friendlyNations(core, n) && alive(core) && core !== prev) to = core; // liberación
    setOwner(r, to);
    if (n === G.player) G.stats.captured++;
    if (prev && prev !== to) checkCapitulation(prev);
  }

  // Unidades que quedan en territorio que ya no es amigo se retiran o se pierden
  function evict(regions) {
    for (const r of regions) {
      for (const u of unitsAt(r).slice()) {
        if (friendly(u.n, r)) continue;
        const to = retreatTarget([u], r, null);
        if (to) u.r = to; else removeUnit(u, 'expulsada');
      }
      dirtyUnits();
    }
  }
  function evictAll() { evict(RIDS); }

  // ---------- diplomacia ----------
  const opposite = f => f === AX ? AL : AX;
  function joinFaction(n, f) {
    if (!G.nations[n] || faction(n) === f) return;
    N(n).faction = f;
    log(nname(n) + ' se une ' + (f === AX ? 'al Eje' : 'a los Aliados') + '.', 'diplo', [n]);
  }
  function declareWar(a, b) {
    if (!alive(b) || a === b) return false;
    const fa = faction(a), fb = faction(b);
    if (fa && fb) return fa !== fb;
    if (!fa && !fb) return false;
    if (fa) joinFaction(b, opposite(fa)); else joinFaction(a, opposite(fb));
    log(nname(a) + ' declara la guerra a ' + nname(b) + '.', 'diplo', [a, b]);
    if (b === G.player) popup({ title: '¡' + nname(a) + ' te declara la guerra!', text: 'Ahora estás en guerra. Defiende tus fronteras.' });
    return true;
  }
  function canDeclare(a, b) {
    if (!alive(b) || a === b || atWar(a, b) || friendlyNations(a, b)) return false;
    return !!(faction(a) || faction(b));
  }
  function switchSides(n, f) {
    N(n).faction = f;
    log(nname(n) + ' cambia de bando y se une ' + (f === AX ? 'al Eje' : 'a los Aliados') + '.', 'diplo', [n]);
    evictAll();
  }
  function leaveWar(n, cessions = {}) {
    N(n).faction = null;
    for (const r in cessions) if (G.owner[r] === n) setOwner(r, cessions[r]);
    // devolver lo ocupado a sus dueños originales si siguen vivos, si no, queda neutral
    for (const r of RIDS) if (G.owner[r] === n && REG[r].code !== n && alive(REG[r].code)) setOwner(r, REG[r].code);
    log(nname(n) + ' sale de la guerra.', 'diplo', [n]);
    evictAll();
  }
  function transfer(ids, to) { for (const r of ids) setOwner(r, to); evict(ids); }
  function annex(m, to) {
    const regs = RIDS.filter(r => G.owner[r] === m);
    for (const u of G.units.filter(u => u.n === m)) removeUnit(u);
    transfer(regs, to);
    N(m).capitulated = true; N(m).faction = null;
  }

  function checkCapitulation(x) {
    if (!G.nations[x] || x === 'USA' || N(x).capitulated) return;
    const nat = N(x);
    const owned = RIDS.filter(r => G.owner[r] === x);
    if (!owned.length) return capitulate(x);
    if (nat.flags.exile) return; // gobierno en el exilio: solo cae si lo pierde todo
    const core = M.regions.filter(r => r.code === x);
    if (!core.length) return;
    const total = core.reduce((s, r) => s + r.vp + 1, 0);
    const held = core.filter(r => friendly(x, r.id)).reduce((s, r) => s + r.vp + 1, 0);
    const ratio = held / total;
    const capHeld = nat.capital && G.owner[nat.capital] === x;
    if (!capHeld && x === 'SOV' && !nat.flags.moved && G.owner.kuibyshev === 'SOV') {
      nat.flags.moved = 1; nat.capital = 'kuibyshev';
      log('El gobierno soviético se traslada a Kúibyshev.', 'event', ['SOV']);
      if (ratio >= 0.35) return;
    }
    const minor = !D.nations[x].major;
    const lim = x === 'SOV' ? 0.3 : 0.5;
    if ((!capHeld && (minor || ratio < lim)) || ratio < lim / 2) capitulate(x);
  }

  function capitulate(x) {
    const nat = N(x);
    if (nat.capitulated) return;
    const cap = D.nations[x].capital;
    let conq = cap && atWar(G.owner[cap], x) ? G.owner[cap] : null;
    if (!conq) {
      const cnt = {};
      for (const r of M.regions) if (r.code === x && atWar(G.owner[r.id], x)) cnt[G.owner[r.id]] = (cnt[G.owner[r.id]] || 0) + 1;
      conq = Object.keys(cnt).sort((a, b) => cnt[b] - cnt[a])[0] || null;
    }
    const owned = RIDS.filter(r => G.owner[r] === x);
    // Francia: régimen de Vichy (o Francia Libre si la juega el jugador)
    if (x === 'FRA' && conq && faction(conq) === AX && !nat.flags.exile) {
      const colonies = owned.filter(r => !REG[r].code || isColony(r));
      const south = owned.filter(r => VICHY.includes(r));
      const north = owned.filter(r => !colonies.includes(r) && !south.includes(r));
      transfer(north, conq);
      const N_VIC = N('VIC');
      N_VIC.capitulated = false; N_VIC.faction = null;
      if (x === G.player && colonies.length) {
        for (const u of G.units.filter(u => u.n === 'FRA' && !colonies.includes(u.r))) removeUnit(u);
        transfer(south, 'VIC');
        nat.flags.exile = 1;
        nat.capital = colonies.includes('argel') ? 'argel' : colonies[0];
        evictAll();
        log('París ha caído. Francia firma el armisticio, pero tú continúas la lucha desde el imperio: ¡la Francia Libre!', 'event', ['FRA']);
        popup({ title: 'La Francia Libre', text: 'El norte de Francia queda ocupado y el sur pasa al régimen de Vichy. Tú sigues luchando desde las colonias. Si aguantas, los aliados volverán a Europa.', hist: 'El 18 de junio de 1940 De Gaulle llamó a resistir desde Londres.' });
        return;
      }
      for (const u of G.units.filter(u => u.n === 'FRA')) removeUnit(u);
      transfer(south.concat(colonies), 'VIC');
      for (const r of ['lyon', 'marsella', 'argel', 'casablanca', 'tunez', 'damasco']) if (G.owner[r] === 'VIC') addUnit('VIC', 'inf', r, true);
      nat.capitulated = true; nat.faction = null;
      evictAll();
      log('¡Francia capitula! El norte queda ocupado y el sur pasa al régimen de Vichy.', 'event', ['FRA', 'GER', 'ENG']);
      popup({ title: 'Francia capitula', text: 'El norte de Francia queda ocupado por ' + nname(conq) + '. En el sur se forma la Francia de Vichy, neutral.', hist: 'El armisticio se firmó el 22 de junio de 1940 en Compiègne, en el mismo vagón de tren de 1918.' });
      endCheck();
      return;
    }
    for (const u of G.units.filter(u => u.n === x)) removeUnit(u);
    if (x === 'POL' && alive('SOV') && !faction('SOV') && !G.fired.molotov) {
      G.fired.molotov = 1;
      const sphere = owned.filter(r => SOV_SPHERE.includes(r));
      transfer(sphere, 'SOV');
    }
    const rest = RIDS.filter(r => G.owner[r] === x);
    if (conq) transfer(rest, conq);
    nat.capitulated = true; nat.faction = null;
    evictAll();
    log('¡' + nname(x) + ' capitula!' + (conq ? ' Sus territorios pasan a ' + nname(conq) + '.' : ''), 'event', [x, conq]);
    if (D.nations[x].major || x === G.player || conq === G.player) popup({ title: nname(x) + ' capitula', text: conq ? 'Sus territorios pasan a ' + nname(conq) + '.' : '' });
    endCheck();
  }
  function isColony(r) { return ['argel', 'oran', 'constantina', 'sahara', 'tunez', 'mareth', 'casablanca', 'fez', 'atlas', 'damasco', 'alepo'].includes(r); }

  // ---------- eventos especiales ----------
  function sovietSphere() {
    G.fired.molotov = 1;
    const regs = SOV_SPHERE.filter(r => G.owner[r] === 'POL');
    for (const u of G.units.filter(u => u.n === 'POL' && regs.includes(u.r))) removeUnit(u);
    transfer(regs, 'SOV');
    checkCapitulation('POL');
  }
  // reparte unidades nuevas entre las regiones de `n` que tocan a `enemy`
  function spawnFront(n, enemy, t, count) {
    const front = RIDS.filter(r => G.owner[r] === n && LAND[r].some(nb => G.owner[nb] === enemy));
    spawn(n, t, count, front.sort((a, b) => room(n, b) - room(n, a)));
  }
  function barbarossa(n) {
    declareWar(n, 'SOV');
    spawnFront(n, 'SOV', 'inf', 10);
    spawnFront(n, 'SOV', 'arm', 4);
    N(n).timed.push({ key: 'atk', val: 0.15, until: G.turn + 4, label: 'Ofensiva en el este' });
    N('SOV').timed.push({ key: 'def', val: -0.3, until: G.turn + 2, label: 'Sorpresa' }, { key: 'atk', val: -0.3, until: G.turn + 3, label: 'Sorpresa' });
    if (alive('FIN') && !faction('FIN')) joinFaction('FIN', faction(n));
  }
  function usaJoins() {
    if (faction('USA')) return;
    N('USA').faction = AL;
    N('USA').air = 6;
    log('Estados Unidos entra en la guerra junto a los Aliados.', 'diplo', ['USA']);
  }
  function torch() {
    const col = RIDS.filter(r => G.owner[r] === 'VIC' && isColony(r));
    const metro = RIDS.filter(r => G.owner[r] === 'VIC' && !isColony(r));
    for (const u of G.units.filter(u => u.n === 'VIC')) removeUnit(u);
    const lib = alive('FRA') && faction('FRA') === AL ? 'FRA' : 'USA';
    transfer(col, lib);
    const occ = alive('GER') && faction('GER') === AX ? 'GER' : alive('ITA') && faction('ITA') === AX ? 'ITA' : null;
    if (occ) transfer(metro, occ);
    N('VIC').capitulated = true;
    spawn('USA', 'inf', 3, ['casablanca', 'argel', 'oran']);
    spawn('USA', 'arm', 1, ['casablanca', 'argel', 'oran']);
  }
  function italianArmistice() {
    const regs = RIDS.filter(r => G.owner[r] === 'ITA');
    for (const u of G.units.filter(u => u.n === 'ITA')) removeUnit(u);
    const ger = alive('GER') && faction('GER') === AX;
    const north = regs.filter(r => ITALY_NORTH.includes(r) || REG[r].code !== 'ITA');
    const south = regs.filter(r => !north.includes(r));
    const lib = alive('ENG') ? 'ENG' : 'USA';
    if (ger) transfer(north, 'GER'); else transfer(north, lib);
    transfer(south, lib);
    N('ITA').capitulated = true; N('ITA').faction = null;
    evictAll();
  }
  function nearEnemy(n) {
    for (const r of RIDS) if (G.owner[r] === n) for (const nb of LAND[r]) if (atWar(n, G.owner[nb])) return true;
    return false;
  }

  // ---------- API para focos y eventos ----------
  function addMod(n, key, v) { N(n).mods[key] = (N(n).mods[key] || 0) + v; }
  function addAir(n, v) { N(n).air += v; }
  function addTimed(n, key, val, turns, label) { N(n).timed.push({ key, val, until: G.turn + turns, label }); }
  function spawn(n, t, count, prefs = []) {
    for (let k = 0; k < count; k++) {
      let r = prefs.find(p => G.owner[p] && friendly(n, p) && inSupply(n, p) && room(n, p) > 0);
      if (!r) r = n === 'USA' ? usaLanding() : defaultDeploy(n);
      if (!r) return;
      addUnit(n, t, r, false);
    }
  }
  function fort(ids, k) { for (const r of ids) G.fort[r] = Math.min(5, (G.fort[r] || 0) + k); }
  function addIndustry(r, k) { G.indMod[r] = (G.indMod[r] || 0) + k; }

  // ---------- focos ----------
  function focusList(n) { return D.focuses[n] || []; }
  function focusState(n, f) {
    const nat = N(n);
    if (nat.done.includes(f.id)) return { st: 'done' };
    if (nat.focus && nat.focus.id === f.id) return { st: 'active', progress: nat.focus.progress };
    const missing = (f.req || []).filter(id => !nat.done.includes(id));
    if (missing.length) return { st: 'locked', reason: 'Requiere: ' + missing.map(id => focusList(n).find(x => x.id === id).name).join(', ') };
    if (f.minDate && G.turn < dateIdxOf(f.minDate)) return { st: 'locked', reason: 'Disponible en ' + dateText(dateIdxOf(f.minDate)) };
    if (f.cond && !f.cond()) return { st: 'locked', reason: f.condText || 'Ahora no tendría efecto' };
    return { st: 'available' };
  }
  function setFocus(n, id) {
    const f = focusList(n).find(x => x.id === id);
    if (!f) return false;
    if (focusState(n, f).st !== 'available') return false;
    N(n).focus = { id, progress: 0 };
    return true;
  }
  function completeFocus(n, f) {
    const nat = N(n);
    nat.done.push(f.id); nat.focus = null;
    f.effect(n);
    log(nname(n) + ' completa el foco «' + f.name + '».', 'focus', [n]);
    if (n === G.player) popup({ title: 'Foco completado: ' + f.name, text: f.desc, hist: f.hist, focus: true });
  }

  // ---------- turnos ----------
  function endTurn(aiFn) {
    if (G.over) return;
    G.popups = [];
    const order = Object.keys(G.nations).filter(n => n !== G.player && alive(n))
      .sort((a, b) => (faction(b) === AX) - (faction(a) === AX));
    for (const n of order) if (alive(n) && !G.over) aiFn(n);
    if (!G.over) endRound();
  }
  function endRound() {
    for (const n in G.nations) {
      if (!alive(n)) continue;
      const nat = N(n);
      const inc = income(n);
      nat.pp += inc; nat.lastIncome = inc;
      nat.mp += mpIncome(n);
      if (nat.focus) {
        const f = focusList(n).find(x => x.id === nat.focus.id);
        nat.focus.progress++;
        if (nat.focus.progress >= f.turns) completeFocus(n, f);
      }
    }
    // refuerzos y desgaste
    for (const u of G.units.slice()) {
      const nat = N(u.n);
      if (inSupply(u.n, u.r)) {
        const need = Math.min(20, 100 - u.s);
        const cost = need * 0.01;
        if (need > 0 && nat.mp >= cost) { u.s += need; nat.mp -= cost; }
      } else {
        u.s -= 15;
        if (u.s <= 5) { removeUnit(u, 'suministro'); log('Una unidad de ' + nname(u.n) + ' se ha rendido por falta de suministro en ' + REG[u.r].name + '.', 'battle', [u.n]); }
      }
    }
    G.turn++;
    for (const n in G.nations) N(n).timed = N(n).timed.filter(t => t.until > G.turn);
    for (const u of G.units) u.mv = UNIT[u.t].mv;
    G.battles = G.battles.filter(b => b.turn >= G.turn - 1);
    runEvents();
    endCheck();
  }
  function runEvents() {
    for (const e of D.events) {
      if (G.fired[e.id]) continue;
      if (G.turn < dateIdxOf(e.date)) continue;
      if (e.ai && e.ai === G.player) { G.fired[e.id] = 1; continue; }
      if (!e.cond()) continue;
      G.fired[e.id] = 1;
      e.apply();
      log(e.title + ': ' + e.text, 'event', []);
      popup({ title: e.title, text: e.text, hist: e.hist, event: true });
    }
  }

  // ---------- victoria ----------
  function factionVP(f) {
    let s = 0, tot = 0;
    for (const r of M.regions) { tot += r.vp; if (faction(G.owner[r.id]) === f) s += r.vp; }
    return { s, tot };
  }
  function endCheck() {
    if (G.over) return;
    const p = G.player;
    if (!alive(p)) { G.over = { result: 'derrota', text: nname(p) + ' ha capitulado.' }; return; }
    const f = faction(p);
    if (f) {
      const enemies = ['GER', 'ITA', 'ENG', 'FRA', 'SOV'].filter(m => alive(m) && faction(m) && faction(m) !== f);
      const everEnemy = ['GER', 'ENG', 'SOV'].some(m => m !== p);
      if (!enemies.length && everEnemy && G.turn > 0 && ['GER', 'ENG', 'SOV'].filter(m => m !== p && !friendlyNations(m, p)).every(m => !alive(m))) {
        G.over = { result: 'victoria total', text: 'Todas las potencias enemigas han capitulado.' }; return;
      }
    }
    if (G.turn >= LAST_TURN) {
      const vp = f ? factionVP(f) : { s: RIDS.filter(r => G.owner[r] === p).reduce((s, r) => s + REG[r].vp, 0), tot: factionVP(AX).tot };
      const share = vp.s / vp.tot;
      const result = share >= 0.6 ? 'victoria decisiva' : share >= 0.45 ? 'victoria' : share >= 0.3 ? 'tablas' : 'derrota';
      G.over = { result, text: 'La guerra termina en agosto de 1945. Tu bando controla el ' + Math.round(share * 100) + ' % de los puntos de victoria.' };
    }
  }

  // ---------- guardar ----------
  function save() { return JSON.stringify(G); }
  function load(json) { G = JSON.parse(json); cache.unitIdx = null; cache.supply = {}; cache.ownerVer = -1; return G; }

  window.Game = {
    get G() { return G; }, newGame, save, load, REG, RIDS, LAND, SEA, UNIT, TERRAIN, DIFF, AIR_COST, LAST_TURN, UK_HOME,
    N, nname, alive, faction, atWar, friendly, friendlyNations, enemyOf, unitsAt, unitById, inSupply, supplySet, mod, hasTimed, room, stackCount, STACK,
    income, mpIncome, mobilization, coreRatio, canBuild, build, deployable, defaultDeploy, reachable, moveKind, moveUnits, battleOdds, attack,
    declareWar, canDeclare, joinFaction, switchSides, leaveWar, transfer, annex, capitulate, checkCapitulation,
    sovietSphere, barbarossa, usaJoins, torch, italianArmistice, nearEnemy,
    addMod, addAir, addTimed, spawn, spawnFront, fort, addIndustry, industry,
    focusList, focusState, setFocus, endTurn, dateText, dateOf, dateIdx, dateIdxOf, isWinter, factionVP, rand, log,
    regionCount,
  };
})();
