// IA sencilla: focos, producción, ataques con buena probabilidad y reparto de tropas según la amenaza.
(function () {
  const Game = window.Game;
  const { REG, RIDS, LAND, SEA, UNIT } = Game;

  const ARM_SHARE = { GER: 0.3, SOV: 0.22, ENG: 0.2, USA: 0.3, FRA: 0.15, ITA: 0.12 };

  function power(u, key) { return UNIT[u.t][key] * u.s / 100; }
  function defenseAt(n, r, includeAllies) {
    const t = Game.TERRAIN[REG[r].terrain].def * (1 + 0.25 * (Game.G.fort[r] || 0)) * Game.mod(n, 'def');
    let s = 0;
    for (const u of Game.unitsAt(r)) {
      if (u.n === n) s += power(u, 'def') * t;
      else if (includeAllies && Game.friendlyNations(u.n, n)) s += power(u, 'def') * t * 0.7;
    }
    return s;
  }
  // nación con la que la IA se prepara para una guerra que aún no ha empezado
  function plannedEnemies(n) {
    const G = Game.G, out = [];
    if (n === 'SOV' && G.turn >= Game.dateIdxOf('1940-03') && Game.alive('GER') && !Game.atWar('SOV', 'GER') && !Game.friendlyNations('SOV', 'GER')) out.push(['GER', 0.8]);
    if (n === 'GER' && G.turn >= Game.dateIdxOf('1941-01') && Game.alive('SOV') && !Game.atWar('SOV', 'GER') && !Game.friendlyNations('SOV', 'GER')) out.push(['SOV', 0.6]);
    if (n === 'ITA' && !Game.faction('ITA')) out.push(['FRA', 0.4]);
    if (n === 'FIN' && Game.alive('SOV')) out.push(['SOV', 0.6]);
    return out;
  }
  function threatAt(n, r, planned) {
    let s = 0;
    const add = (nb, w) => {
      const o = Game.G.owner[nb];
      let k = Game.atWar(n, o) ? 1 : 0;
      for (const [p, pw] of planned) if (o === p || (Game.faction(p) && Game.faction(o) === Game.faction(p))) k = Math.max(k, pw);
      if (!k) return;
      if (w === 1 && Game.atWar(n, o)) s = Math.max(s, 2.5);
      for (const u of Game.unitsAt(nb)) if (Game.atWar(n, u.n) || planned.some(([p]) => p === u.n)) s += power(u, 'atk') * Game.mod(u.n, 'atk') * (u.t === 'arm' ? Game.mod(u.n, 'arm') : 1) * w * k;
    };
    for (const nb of LAND[r]) add(nb, 1);
    for (const nb of SEA[r]) add(nb, 0.3);
    return s;
  }

  // ¿Ataca la IA a este dueño ahora? (guerra de broma en el oeste hasta mayo de 1940)
  function mayAttack(n, owner) {
    const G = Game.G;
    if (n === 'GER' && ['FRA', 'ENG', 'BEL', 'NED'].includes(owner) && G.turn < Game.dateIdxOf('1940-05')) return false;
    return true;
  }
  function threshold(n, owner) {
    let t = Game.DIFF[Game.G.difficulty].thr;
    if ((n === 'FRA' || n === 'ENG') && Game.G.turn < Game.dateIdxOf('1941-06') && owner === 'GER') t += 0.15;
    if (Game.N(n).timed.some(x => x.key === 'atk' && x.val > 0)) t -= 0.08; // ofensiva en marcha
    return t;
  }

  function pickFocus(n) {
    const nat = Game.N(n);
    if (nat.focus) return;
    for (const f of Game.focusList(n)) {
      if (f.aiSkip) continue;
      if (Game.focusState(n, f).st === 'available') { Game.setFocus(n, f.id); return; }
    }
  }

  function production(n, deficits) {
    const nat = Game.N(n);
    const major = !!window.DATA.nations[n].major;
    const own = Game.G.units.filter(u => u.n === n);
    if (!major && !Game.faction(n) && own.length >= Game.regionCount(n) * 1.5 + 1) return;
    let guard = 30;
    while (guard-- > 0) {
      const armShare = own.length ? own.filter(u => u.t === 'arm').length / own.length : 0;
      let t = 'inf';
      if (major && armShare < (ARM_SHARE[n] || 0.1) && nat.pp >= UNIT.arm.pp + 5) t = 'arm';
      if (major && nat.air < 4 + own.length * 0.2 && nat.pp >= Game.AIR_COST && Game.rand() < 0.35) t = 'air';
      if (t === 'inf' && nat.mp < UNIT.inf.mp && nat.mp >= UNIT.arm.mp && nat.pp >= UNIT.arm.pp && major) t = 'arm';
      let r = null;
      if (t !== 'air') {
        r = deficits.find(d => Game.deployable(n, d.r) && d.need > 0);
        r = r ? r.r : null;
      }
      const res = Game.build(n, t, r || undefined);
      if (!res.ok) break;
      if (t !== 'air') {
        own.push({ t });
        const d = deficits.find(d => d.r === res.r);
        if (d) d.need -= UNIT[t].def;
      }
    }
  }

  function attacks(n) {
    const G = Game.G;
    for (let iter = 0; iter < 80; iter++) {
      const mine = G.units.filter(u => u.n === n && u.mv > 0);
      if (!mine.length) return;
      const targets = new Set();
      for (const u of mine) for (const nb of LAND[u.r].concat(u.mv >= UNIT[u.t].mv ? SEA[u.r] : [])) {
        const o = G.owner[nb];
        if (Game.atWar(n, o) && mayAttack(n, o)) targets.add(nb);
      }
      let best = null;
      for (const t of targets) {
        const owner = G.owner[t];
        const defenders = Game.unitsAt(t);
        const avail = mine.filter(u => LAND[u.r].includes(t) || (SEA[u.r].includes(t) && u.mv >= UNIT[u.t].mv));
        if (!avail.length) continue;
        if (!defenders.length) {
          // ocupar región vacía con una sola unidad (preferible blindado)
          const pick = avail.filter(u => LAND[u.r].includes(t)).sort((a, b) => (b.t === 'arm') - (a.t === 'arm'))[0];
          if (!pick) continue;
          if (Game.unitsAt(pick.r).filter(x => x.n === n).length <= 1 && threatAt(n, pick.r, []) > 0) continue;
          const score = 2 + REG[t].vp * 0.1;
          if (!best || score > best.score) best = { t, units: [pick], score, empty: true };
          continue;
        }
        // dejar guarnición en regiones amenazadas por otros vecinos
        const bySrc = {};
        for (const u of avail) (bySrc[u.r] ||= []).push(u);
        let use = [];
        for (const src in bySrc) {
          const list = bySrc[src].sort((a, b) => power(b, 'atk') - power(a, 'atk'));
          const other = LAND[src].concat(SEA[src]).filter(x => x !== t && Game.atWar(n, G.owner[x])).length;
          const stay = Game.unitsAt(src).filter(x => x.n === n && !list.includes(x)).length;
          if (other && !stay && list.length > 1) {
            const keep = list.filter(u => u.t === 'inf').pop() || list.pop();
            list.splice(list.indexOf(keep), 1);
          } else if (other && !stay && list.length === 1) continue;
          use = use.concat(list);
        }
        if (!use.length) continue;
        use.sort((a, b) => power(b, 'atk') - power(a, 'atk'));
        const thr = threshold(n, owner);
        const full = Game.battleOdds(use, t);
        if (full.p < thr) continue;
        let chosen = use;
        for (let k = 1; k <= use.length; k++) {
          const o = Game.battleOdds(use.slice(0, k), t);
          if (o.p >= thr + 0.12 || k === use.length) { chosen = use.slice(0, k); break; }
        }
        const p = Game.battleOdds(chosen, t).p;
        const score = p + REG[t].vp * 0.06 + (t === Game.N(owner).capital ? 0.3 : 0);
        if (!best || score > best.score) best = { t, units: chosen, score };
      }
      if (!best) return;
      if (best.empty) Game.moveUnits(best.units.map(u => u.id), best.t);
      else Game.attack(best.units.map(u => u.id), best.t);
    }
  }

  function computeDeficits(n) {
    const G = Game.G;
    const planned = plannedEnemies(n);
    const out = [];
    const capital = Game.N(n).capital;
    for (const r of RIDS) {
      if (G.owner[r] !== n && !(Game.unitsAt(r).some(u => u.n === n) && Game.friendly(n, r))) continue;
      const th = threatAt(n, r, planned);
      const landWar = LAND[r].some(nb => Game.atWar(n, G.owner[nb]));
      const seaWar = SEA[r].some(nb => Game.atWar(n, G.owner[nb]) && Game.unitsAt(nb).length);
      let want = th * 1.15;
      if (landWar || seaWar) want = Math.max(want, 3);
      if (r === capital && (landWar || seaWar || LAND[r].some(nb => LAND[nb].some(x => Game.atWar(n, G.owner[x]))))) want = Math.max(want, 8);
      if (!want) continue;
      // concentrar fuerzas (con límite) frente a enemigos débiles para atacar el próximo turno
      for (const nb of LAND[r]) {
        if (!Game.atWar(n, G.owner[nb]) || !mayAttack(n, G.owner[nb])) continue;
        const ed = defenseAt(G.owner[nb], nb, true);
        want = Math.max(want, Math.min(ed * 1.1 + REG[nb].vp, 30));
      }
      const cur = defenseAt(n, r, true);
      out.push({ r, need: want - cur, cur, want, threat: th });
    }
    out.sort((a, b) => b.need - a.need);
    return out;
  }

  function positioning(n, deficits) {
    const G = Game.G;
    const dmap = {};
    for (const d of deficits) dmap[d.r] = d;
    // unidades libres: con todos sus movimientos y en regiones sin amenaza o con sobrante
    const free = [];
    const byRegion = {};
    for (const u of G.units) if (u.n === n && u.mv >= UNIT[u.t].mv) (byRegion[u.r] ||= []).push(u);
    for (const r in byRegion) {
      const d = dmap[r];
      const list = byRegion[r].sort((a, b) => (a.t === 'arm') - (b.t === 'arm'));
      if (!d) { free.push(...list); continue; }
      let surplus = -d.need;
      const terr = Game.TERRAIN[REG[r].terrain].def * (1 + 0.25 * (G.fort[r] || 0));
      for (const u of list.slice().reverse()) {
        const v = power(u, 'def') * terr;
        if (surplus - v > 0.5 && Game.unitsAt(r).filter(x => x.n === n).length - free.filter(x => x.r === r).length > 1) { free.push(u); surplus -= v; }
      }
      if (surplus < 0) d.need = -surplus; else d.need = 0;
    }
    const needy = deficits.filter(d => d.need > 0.3);
    if (!needy.length || !free.length) return;
    const reach = {};
    for (const u of free) {
      const from = u.r;
      if (!reach[from]) reach[from] = Game.reachable(n, from);
      // preferir el destino más necesitado alcanzable (primero los vecinos inmediatos)
      let target = null;
      for (const d of needy) {
        if (d.need <= 0.3 || d.r === from) continue;
        if (!reach[from].has(d.r) || Game.room(n, d.r) <= 0) continue;
        target = d; break;
      }
      if (!target) continue;
      const res = Game.moveUnits([u.id], target.r);
      if (res.ok) target.need -= power(u, 'def') * Game.TERRAIN[REG[target.r].terrain].def;
    }
  }

  function runAI(n) {
    if (!Game.alive(n)) return;
    pickFocus(n);
    const deficits = computeDeficits(n);
    production(n, deficits);
    if (!Game.faction(n) && !plannedEnemies(n).length) return;
    if (Game.faction(n)) attacks(n);
    positioning(n, computeDeficits(n));
  }

  window.AI = { runAI, computeDeficits };
})();
