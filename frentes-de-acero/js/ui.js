// Interfaz: mapa SVG con zoom, paneles, combate, asesor, tutorial e informes.
(function () {
  const D = window.DATA, M = window.MAP, Game = window.Game, AI = window.AI;
  const { REG, RIDS, LAND, SEA, UNIT } = Game;
  const SAVE_KEY = 'frentes-de-acero-partida';
  const $ = s => document.querySelector(s);
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const pct = p => Math.round(p * 100) + ' %';
  const G = () => Game.G;
  const P = () => G().player;
  const color = n => (D.nations[n] || {}).color || '#777';
  const nname = n => Game.nname(n);

  const ui = { sel: null, selUnits: new Set(), tab: 'region', mode: 'paises', view: null, k: 1, tut: -1, targets: {}, reportFrom: 0, confirmWar: null, focusConfirm: null };

  // ---------- iconos ----------
  const ICON = {
    pp: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 21V10l5 3V10l5 3V6l5 3v12z"/><path d="M3 21h18"/></svg>',
    mp: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="9" cy="7" r="3"/><circle cx="17" cy="8" r="2.5"/><path d="M3 20c0-3.5 2.7-6 6-6s6 2.5 6 6M14 14.5c3 0 7 1.5 7 5"/></svg>',
    air: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2l2 8 8 4v2l-8-2-1 5 3 2v1l-4-1-4 1v-1l3-2-1-5-8 2v-2l8-4z"/></svg>',
  };
  const nato = (t, c = 'currentColor') => t === 'inf'
    ? `<svg class="nato" viewBox="0 0 26 17"><rect x="1" y="1" width="24" height="15" fill="none" stroke="${c}" stroke-width="1.6"/><path d="M1 1l24 15M25 1L1 16" stroke="${c}" stroke-width="1.6"/></svg>`
    : `<svg class="nato" viewBox="0 0 26 17"><rect x="1" y="1" width="24" height="15" fill="none" stroke="${c}" stroke-width="1.6"/><ellipse cx="13" cy="8.5" rx="8" ry="4.3" fill="none" stroke="${c}" stroke-width="1.6"/></svg>`;

  // ---------- utilidades de estado ----------
  const myUnits = r => Game.unitsAt(r).filter(u => u.n === P());
  const selectedUnits = () => [...ui.selUnits].map(Game.unitById).filter(u => u && u.r === ui.sel && u.mv > 0);
  function factionColor(n) {
    const f = Game.faction(n);
    if (f === 'AX') return getVar('--axis');
    if (f === 'AL') return getVar('--allies');
    if (n === 'SOV') return getVar('--comintern');
    return getVar('--neutral');
  }
  const varCache = {};
  function getVar(v) { return varCache[v] ||= getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }
  function relation(n) {
    if (n === P()) return ['Tú', 'brass'];
    if (Game.atWar(P(), n)) return ['Enemigo', 'bad'];
    if (Game.friendlyNations(P(), n)) return ['Aliado', 'good'];
    return ['Neutral', ''];
  }
  function toast(msg) {
    const t = $('#toast');
    t.textContent = msg; t.classList.add('on');
    clearTimeout(toast.h); toast.h = setTimeout(() => t.classList.remove('on'), 2600);
  }

  // ---------- mapa ----------
  const svg = $('#map');
  function buildMap() {
    $('#grat').setAttribute('d', M.grat);
    $('#wasteland').setAttribute('d', M.waste);
    $('#gRegions').innerHTML = M.regions.map(r => `<path class="reg" data-id="${r.id}" d="${r.path}" fill-rule="evenodd"></path>`).join('');
    $('#gSea').innerHTML = M.sea.map(([a, b]) => {
      const A = REG[a], B = REG[b];
      const mx = (A.lx + B.lx) / 2, my = (A.ly + B.ly) / 2, dx = B.lx - A.lx, dy = B.ly - A.ly;
      return `<path class="sealink" d="M${A.lx} ${A.ly}Q${mx - dy * 0.15} ${my + dx * 0.15} ${B.lx} ${B.ly}"></path>`;
    }).join('');
    $('#gCities').innerHTML = M.regions.filter(r => r.vp >= 1).map(r => {
      const cap = Object.values(D.nations).some(n => n.capital === r.id);
      return cap ? `<rect class="city cap" x="${r.cx - 2.2}" y="${r.cy - 2.2}" width="4.4" height="4.4"></rect>` : `<circle class="city" cx="${r.cx}" cy="${r.cy}" r="${r.vp >= 2 ? 2 : 1.4}"></circle>`;
    }).join('');
    const clbl = Object.entries(M.countryLabels).filter(([, c]) => c.size > 160).map(([code, c]) =>
      `<text class="clbl" x="${c.x}" y="${c.y}">${esc(D.nations[code] ? D.nations[code].name : '')}</text>`).join('');
    $('#gLabels').innerHTML = M.regions.map(r => `<text class="lbl" x="${r.lx}" y="${r.ly + 14}">${esc(r.name)}</text>`).join('') + clbl;
  }
  function paintRegions() {
    const paths = $('#gRegions').children;
    let occ = '';
    for (const p of paths) {
      const id = p.dataset.id, o = G().owner[id];
      p.setAttribute('fill', ui.mode === 'bandos' ? factionColor(o) : color(o));
      p.classList.toggle('mine', o === P());
      if (o !== REG[id].code) occ += `<path class="occ" d="${REG[id].path}" fill="url(#occ)" fill-rule="evenodd"></path>`;
    }
    $('#gOcc').innerHTML = occ;
    legend();
  }
  function legend() {
    const L = $('#legend');
    if (ui.mode === 'bandos') {
      const items = [['--axis', 'Eje'], ['--allies', 'Aliados'], ['--neutral', 'Neutrales']];
      if (!Game.faction('SOV') && Game.alive('SOV')) items.push(['--comintern', 'URSS (neutral)']);
      L.innerHTML = items.map(([v, t]) => `<div><i class="chip-sw" style="background:var(${v})"></i>${t}</div>`).join('');
    } else {
      L.innerHTML = `<div><i class="chip-sw" style="background:${color(P())}"></i>${esc(nname(P()))}</div>
        <div><i class="chip-sw" style="background:repeating-linear-gradient(45deg,#777 0 2px,#bbb 2px 4px)"></i>Ocupado</div>
        <div><svg width="14" height="14"><rect x="3" y="3" width="8" height="8" fill="var(--brass)" stroke="#000"/></svg>Capital</div>`;
    }
  }

  function counterSvg(r, n, units, s) {
    const inf = units.filter(u => u.t === 'inf').length, arm = units.length - inf;
    const fs = 9 * s, h = 15 * s, iconW = 13 * s, pad = 4 * s;
    let w = pad, parts = '';
    const icon = (t, x) => t === 'inf'
      ? `<rect x="${x}" y="${-4.5 * s}" width="${iconW}" height="${9 * s}" fill="none" stroke="#fff" stroke-width="${s}"/><path d="M${x} ${-4.5 * s}l${iconW} ${9 * s}M${x + iconW} ${-4.5 * s}l${-iconW} ${9 * s}" stroke="#fff" stroke-width="${s}"/>`
      : `<rect x="${x}" y="${-4.5 * s}" width="${iconW}" height="${9 * s}" fill="none" stroke="#fff" stroke-width="${s}"/><ellipse cx="${x + iconW / 2}" cy="0" rx="${iconW * 0.32}" ry="${2.4 * s}" fill="none" stroke="#fff" stroke-width="${s}"/>`;
    for (const [t, c] of [['inf', inf], ['arm', arm]]) {
      if (!c) continue;
      parts += icon(t, w);
      w += iconW + 2 * s;
      parts += `<text x="${w}" y="0" style="font-size:${fs}px">${c}</text>`;
      w += String(c).length * 5.6 * s + pad;
    }
    const mine = n === P();
    const ready = mine ? units.filter(u => u.mv > 0).length : 0;
    const nosup = mine && !Game.inSupply(n, r);
    const cls = 'ctr' + (mine && ui.sel === r ? ' sel' : '') + (nosup ? ' nosup' : '');
    const dot = ready ? `<circle cx="${w - 1.5 * s}" cy="${-h / 2}" r="${2.6 * s}" fill="var(--good)" stroke="#000" stroke-width="${0.6 * s}"/>` : '';
    return `<g class="${cls}"><rect class="bg" x="0" y="${-h / 2}" width="${w}" height="${h}" rx="${2.5 * s}" fill="${color(n)}" stroke-width="${(mine && ui.sel === r ? 1.8 : 0.8) * s}"/>${parts}${dot}</g>`;
  }
  function renderCounters() {
    const s = 1.25 / ui.k;
    let out = '';
    const idx = {};
    for (const u of G().units) ((idx[u.r] ||= {})[u.n] ||= []).push(u);
    for (const r in idx) {
      const R = REG[r];
      const ns = Object.keys(idx[r]).sort((a, b) => (b === P()) - (a === P()));
      ns.forEach((n, i) => {
        out += `<g transform="translate(${R.lx - 14 * s} ${R.ly + i * 17 * s})">${counterSvg(r, n, idx[r][n], s)}</g>`;
      });
    }
    $('#gCounters').innerHTML = out;
    // marcas de combate del último mes
    $('#gBattles').innerHTML = G().battles.filter(b => b.turn >= G().turn - 1).map(b => {
      const R = REG[b.r], x = R.lx + 18 * s, y = R.ly - 12 * s, c = b.win ? '#f2c14e' : '#e2654f';
      return `<g class="boom"><circle cx="${x}" cy="${y}" r="${5 * s}" fill="rgba(0,0,0,.55)"/><path d="M${x - 3 * s} ${y - 3 * s}l${6 * s} ${6 * s}M${x + 3 * s} ${y - 3 * s}l${-6 * s} ${6 * s}" stroke="${c}" stroke-width="${1.6 * s}" stroke-linecap="round"/></g>`;
    }).join('');
    renderPills();
  }
  function renderHighlights() {
    let out = '';
    ui.targets = {};
    if (ui.sel) out += `<path class="hl sel" d="${REG[ui.sel].path}" fill-rule="evenodd"></path>`;
    const units = selectedUnits();
    if (units.length) {
      for (const r of RIDS) {
        if (r === ui.sel) continue;
        const k = Game.moveKind(units, r);
        if (!k.ok && k.kind !== 'neutral') continue;
        let cls = k.kind;
        if (k.kind === 'attack') { cls = 'atk'; ui.targets[r] = { kind: 'attack', p: Game.battleOdds(units, r).p }; }
        else if (k.kind === 'occupy') { cls = 'atk'; ui.targets[r] = { kind: 'occupy' }; }
        else if (k.kind === 'move' || k.kind === 'sea') cls = 'move';
        else if (k.kind === 'rail') cls = 'rail';
        out += `<path class="hl ${cls}" d="${REG[r].path}" fill-rule="evenodd"></path>`;
      }
    }
    $('#gHl').innerHTML = out;
    renderPills();
  }
  function renderPills() {
    const s = 1 / ui.k;
    let out = '';
    for (const r in ui.targets) {
      const t = ui.targets[r], R = REG[r];
      const txt = t.kind === 'occupy' ? 'Ocupar' : pct(t.p);
      const c = t.kind === 'occupy' ? '#9fd3a4' : t.p >= 0.7 ? '#8fd18f' : t.p >= 0.45 ? '#f0c95a' : '#f08a73';
      const w = (txt.length * 6.2 + 10) * s;
      out += `<g class="pill" transform="translate(${R.lx} ${R.ly - 16 * s})"><rect x="${-w / 2}" y="${-7.5 * s}" width="${w}" height="${15 * s}" rx="${7.5 * s}" fill="${c}" stroke-width="${0.7 * s}"/><text style="font-size:${11 * s}px">${txt}</text></g>`;
    }
    $('#gPills').innerHTML = out;
  }

  // vista y zoom
  function fitHeight(w) { const r = svg.getBoundingClientRect(); return w * (r.height || 1) / (r.width || 1); }
  function setView(x, y, w) {
    w = Math.max(M.W / 9, Math.min(M.W * 1.1, w));
    const h = fitHeight(w);
    x = Math.max(-w * 0.3, Math.min(M.W - w * 0.7, x));
    y = Math.max(-h * 0.3, Math.min(M.H - h * 0.7, y));
    ui.view = { x, y, w, h };
    svg.setAttribute('viewBox', `${x} ${y} ${w} ${h}`);
    const rect = svg.getBoundingClientRect();
    ui.k = (rect.width || 800) / w;
    svg.style.setProperty('--s', (1 / ui.k).toFixed(4));
    svg.classList.toggle('z2', ui.k >= 2.1);
    svg.classList.toggle('z3', ui.k >= 3.3);
    cancelAnimationFrame(setView.raf);
    setView.raf = requestAnimationFrame(renderCounters);
  }
  function zoomAt(f, cx, cy) {
    const v = ui.view;
    const nw = Math.max(M.W / 9, Math.min(M.W * 1.1, v.w / f));
    const ratio = nw / v.w;
    setView(cx - (cx - v.x) * ratio, cy - (cy - v.y) * ratio, nw);
  }
  function toMap(ev) {
    const r = svg.getBoundingClientRect();
    return [ui.view.x + (ev.clientX - r.left) / ui.k, ui.view.y + (ev.clientY - r.top) / ui.k];
  }
  function centerOn(id, w) {
    const R = REG[id];
    w = w || Math.min(ui.view ? ui.view.w : M.W, M.W / 2.6);
    setView(R.lx - w / 2, R.ly - fitHeight(w) / 2, w);
  }
  function homeView() {
    const cap = Game.N(P()).capital || RIDS.find(r => G().owner[r] === P());
    if (cap) centerOn(cap, M.W / 2.3); else setView(0, 0, M.W);
  }

  // puntero: arrastrar, pellizcar, clic
  const ptrs = new Map();
  let drag = null;
  svg.addEventListener('pointerdown', e => {
    svg.setPointerCapture(e.pointerId);
    ptrs.set(e.pointerId, [e.clientX, e.clientY]);
    if (ptrs.size === 1) drag = { x: e.clientX, y: e.clientY, v: { ...ui.view }, moved: false, target: e.target };
    else drag = { pinch: true, d: dist(), v: { ...ui.view }, mid: midMap() };
  });
  function dist() { const [a, b] = [...ptrs.values()]; return Math.hypot(a[0] - b[0], a[1] - b[1]); }
  function midMap() { const [a, b] = [...ptrs.values()]; return toMap({ clientX: (a[0] + b[0]) / 2, clientY: (a[1] + b[1]) / 2 }); }
  svg.addEventListener('pointermove', e => {
    if (!ptrs.has(e.pointerId)) return;
    ptrs.set(e.pointerId, [e.clientX, e.clientY]);
    if (!drag) return;
    if (drag.pinch && ptrs.size === 2) {
      const f = dist() / drag.d;
      const nw = drag.v.w / f, [mx, my] = drag.mid;
      const ratio = nw / drag.v.w;
      setView(mx - (mx - drag.v.x) * ratio, my - (my - drag.v.y) * ratio, nw);
      return;
    }
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (!drag.moved && Math.hypot(dx, dy) < 5) return;
    drag.moved = true;
    svg.classList.add('panning');
    setView(drag.v.x - dx / ui.k, drag.v.y - dy / ui.k, drag.v.w);
  });
  function endPtr(e) {
    ptrs.delete(e.pointerId);
    svg.classList.remove('panning');
    if (drag && !drag.pinch && !drag.moved && e.type === 'pointerup') {
      const reg = e.target.closest && e.target.closest('.reg');
      if (reg) regionClick(reg.dataset.id); else clearSel();
    }
    if (!ptrs.size) drag = null;
    else if (ptrs.size === 1) { const [p] = [...ptrs.values()]; drag = { x: p[0], y: p[1], v: { ...ui.view }, moved: true }; }
  }
  svg.addEventListener('pointerup', endPtr);
  svg.addEventListener('pointercancel', endPtr);
  svg.addEventListener('wheel', e => {
    e.preventDefault();
    const [mx, my] = toMap(e);
    zoomAt(e.deltaY < 0 ? 1.18 : 1 / 1.18, mx, my);
  }, { passive: false });
  svg.addEventListener('contextmenu', e => { e.preventDefault(); clearSel(); });
  $('#zIn').onclick = () => zoomAt(1.35, ui.view.x + ui.view.w / 2, ui.view.y + ui.view.h / 2);
  $('#zOut').onclick = () => zoomAt(1 / 1.35, ui.view.x + ui.view.w / 2, ui.view.y + ui.view.h / 2);
  $('#zHome').onclick = homeView;
  window.addEventListener('resize', () => { if (ui.view) setView(ui.view.x, ui.view.y, ui.view.w); });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { if (!$('#modal').hidden && ui.modalClosable) closeModal(); else clearSel(); }
  });
  $('#modeSeg').addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    ui.mode = b.dataset.mode;
    for (const x of $('#modeSeg').children) x.classList.toggle('on', x === b);
    paintRegions();
  });

  // ---------- selección y órdenes ----------
  function select(id) {
    ui.sel = id;
    ui.selUnits = new Set(myUnits(id).filter(u => u.mv > 0).map(u => u.id));
    ui.confirmWar = null;
    setTab('region');
    renderHighlights(); renderCounters();
  }
  function clearSel() { ui.sel = null; ui.selUnits = new Set(); renderHighlights(); renderCounters(); if (ui.tab === 'region') renderPanel(); }
  function regionClick(id) {
    if (G().over) { select(id); return; }
    const units = selectedUnits();
    if (units.length && ui.sel && id !== ui.sel) {
      const k = Game.moveKind(units, id);
      if (k.ok) {
        if (k.kind === 'attack') return openBattle(id);
        const from = ui.sel;
        const res = Game.moveUnits(units.map(u => u.id), id);
        if (res.ok) {
          const exposed = !Game.unitsAt(from).some(u => Game.friendlyNations(u.n, P())) && G().owner[from] === P() &&
            LAND[from].some(nb => Game.atWar(P(), G().owner[nb]));
          if (exposed) { setTimeout(() => toast('Cuidado: ' + REG[from].name + ' queda sin defensa y el enemigo podría entrar sin luchar.'), 2700); }
          toast(k.kind === 'occupy' ? '¡' + REG[id].name + ' ocupada!' : k.kind === 'rail' ? 'Traslado por ferrocarril a ' + REG[id].name + '. Llegan sin movimientos.' : k.kind === 'sea' ? 'Transporte por mar a ' + REG[id].name + '.' : 'Unidades movidas a ' + REG[id].name + '.');
          afterAction();
          select(id);
          return;
        }
      } else if (k.kind === 'neutral') {
        ui.sel = id; ui.selUnits = new Set(); ui.confirmWar = G().owner[id];
        setTab('region'); renderHighlights(); renderCounters();
        return;
      } else if (k.reason && (LAND[ui.sel].includes(id) || SEA[ui.sel].includes(id))) {
        toast(k.reason);
      }
    }
    select(id);
  }
  function afterAction() { paintRegions(); renderTop(); renderAdvisor(); if (G().over) showGameOver(); }

  // ---------- barra superior ----------
  function renderTop() {
    const n = P(), nat = Game.N(n);
    const f = Game.faction(n);
    $('#tbNation').innerHTML = `<i class="chip-sw" style="background:${color(n)}"></i><div>${esc(nname(n))}<small>${f === 'AX' ? 'Eje' : f === 'AL' ? 'Aliados' : 'Neutral'}${nat.flags.exile ? ' · Francia Libre' : ''}</small></div>`;
    $('#tbDate').innerHTML = `${Game.dateText()}<small>Turno ${G().turn + 1} de ${Game.LAST_TURN}</small>`;
    const inc = Game.income(n), mpi = Game.mpIncome(n);
    $('#tbRes').innerHTML = `
      <div class="res" data-tip="Producción: se gasta en divisiones y aviones. Viene de la industria de tus regiones (las ocupadas rinden menos).">${ICON.pp}<div><span>Producción</span><b>${Math.floor(nat.pp)}</b> <em>+${inc}</em></div></div>
      <div class="res" data-tip="Reclutas: hacen falta para crear divisiones y para reponer las bajas.">${ICON.mp}<div><span>Reclutas</span><b>${Math.floor(nat.mp)}</b> <em>+${mpi}</em></div></div>
      <div class="res" data-tip="Aviación: si tienes más aviones que tu enemigo, ganas ventaja en todas las batallas contra él.">${ICON.air}<div><span>Aviación</span><b>${nat.air}</b></div></div>`;
    const tabs = $('#tabs').children;
    for (const t of tabs) {
      const dot = (t.dataset.tab === 'focus' && !nat.focus && Game.focusList(n).some(f => Game.focusState(n, f).st === 'available')) ||
        (t.dataset.tab === 'build' && nat.pp >= UNIT.inf.pp && nat.mp >= UNIT.inf.mp);
      t.innerHTML = t.textContent.replace(/\s*$/, '') + (dot ? '<i class="dot"></i>' : '');
    }
  }

  // ---------- panel lateral ----------
  function setTab(t) {
    ui.tab = t;
    for (const b of $('#tabs').children) b.classList.toggle('on', b.dataset.tab === t);
    renderPanel();
  }
  $('#tabs').addEventListener('click', e => { const b = e.target.closest('button'); if (b) setTab(b.dataset.tab); });
  function renderPanel() {
    const p = $('#panel');
    if (!G()) return;
    p.innerHTML = ui.tab === 'region' ? panelRegion() : ui.tab === 'build' ? panelBuild() : ui.tab === 'focus' ? panelFocus() : panelWar();
    p.scrollTop = 0;
  }
  function strBar(s) { return `<div class="bar ${s < 40 ? 'low' : s < 70 ? 'mid' : ''}"><i style="width:${s}%"></i></div>`; }
  function panelRegion() {
    if (!ui.sel) {
      const n = P();
      const units = G().units.filter(u => u.n === n);
      const ready = units.filter(u => u.mv > 0).length;
      const pl = D.playable.find(x => x.code === n);
      return `<div><p class="eyebrow">Mando supremo</p><h2 class="h">${esc(nname(n))}</h2></div>
        <p class="sub">Haz clic en una región del mapa para ver qué hay y dar órdenes a tus tropas.</p>
        ${pl ? `<div class="goal"><b>Objetivo:</b> ${esc(pl.goal)}</div>` : ''}
        <dl class="kv"><dt>Regiones</dt><dd>${Game.regionCount(n)}</dd><dt>Divisiones</dt><dd>${units.length} (${units.filter(u => u.t === 'arm').length} blindadas)</dd><dt>Listas para mover</dt><dd>${ready}</dd></dl>
        ${ready ? `<button class="btn small" data-act="nextReady">Ir a la siguiente con movimientos</button>` : ''}`;
    }
    const r = ui.sel, R = REG[r], o = G().owner[r];
    const [rel, relC] = relation(o);
    const fort = G().fort[r] || 0;
    const t = Game.TERRAIN[R.terrain];
    let html = `<div><p class="eyebrow">Región</p><h2 class="h">${esc(R.name)}</h2></div>
      <div class="row"><span class="tag ${relC}"><i class="chip-sw" style="background:${color(o)}"></i>${esc(nname(o))} · ${rel}</span>
      ${R.code !== o ? `<span class="tag warn">Ocupada · de ${esc(nname(R.code))}</span>` : ''}
      ${R.vp ? `<span class="tag brass" data-tip="Puntos de victoria: cuentan para ganar la partida y para que un país se rinda.">${R.vp} PV</span>` : ''}</div>
      <dl class="kv">
        <dt>Terreno</dt><dd data-tip="Defensa ×${t.def}; blindados al atacar ×${t.arm}.">${t.name} <span class="sub">(defensa ×${t.def})</span></dd>
        <dt>Fortificación</dt><dd>${fort ? 'Nivel ' + fort + ' <span class="sub">(defensa ×' + (1 + 0.25 * fort) + ')</span>' : 'Ninguna'}</dd>
        <dt>Industria</dt><dd>${Game.industry(r)}${R.port ? ' · Puerto' : ''}</dd>
        ${Game.friendly(P(), r) ? `<dt>Suministro</dt><dd>${Game.inSupply(P(), r) ? '<span class="tag good">Conectado</span>' : '<span class="tag bad">Cortado</span>'}</dd>` : ''}
      </dl>`;
    const mine = myUnits(r);
    if (mine.length) {
      html += `<div class="box"><div class="row between"><b>Tus divisiones (${mine.length})</b>
        <div class="row"><button class="btn small" data-act="selAll">Todas</button><button class="btn small" data-act="selNone">Ninguna</button></div></div>
        <div class="units">${mine.sort((a, b) => (a.t > b.t) - (a.t < b.t) || b.s - a.s).map(u => `
          <label class="unit ${u.mv ? '' : 'used'}"><input type="checkbox" data-uid="${u.id}" ${ui.selUnits.has(u.id) ? 'checked' : ''} ${u.mv ? '' : 'disabled'}>
          ${nato(u.t)}<span>${UNIT[u.t].name}</span>${strBar(u.s)}<span class="mv" title="Movimientos que le quedan">${u.mv}/${UNIT[u.t].mv}</span></label>`).join('')}</div>
        <p class="sub">${selectedUnits().length ? 'Haz clic en una región vecina: <b style="color:var(--good)">verde</b> para mover, <b style="color:var(--bad)">roja</b> para atacar (verás tu % de victoria). Las regiones verde claro se alcanzan por ferrocarril.' : 'Marca las divisiones que quieres mover.'}</p></div>`;
    }
    const others = Game.unitsAt(r).filter(u => u.n !== P());
    if (others.length) {
      const byN = {};
      for (const u of others) (byN[u.n] ||= []).push(u);
      html += `<div class="box flat">${Object.entries(byN).map(([n, us]) => {
        const def = us.reduce((s, u) => s + UNIT[u.t].def * u.s / 100, 0) * t.def * (1 + 0.25 * fort);
        return `<div class="row between"><span class="row"><i class="chip-sw" style="background:${color(n)}"></i>${esc(nname(n))}</span>
          <span class="stats"><span>${nato('inf')}</span><b>${us.filter(u => u.t === 'inf').length}</b><span>${nato('arm')}</span><b>${us.filter(u => u.t === 'arm').length}</b></span></div>
          ${Game.atWar(P(), n) ? `<p class="sub">Defensa estimada: <b>${def.toFixed(1)}</b></p>` : ''}`;
      }).join('')}</div>`;
    }
    if (ui.confirmWar && ui.confirmWar === o) html += Game.canDeclare(P(), o) ? warBox(o)
      : `<div class="box" style="border-color:var(--warn)"><b>${esc(nname(o))} es neutral</b><p class="sub">Ni tú ni ${esc(nname(o))} estáis en un bando, así que no podéis entrar en guerra todavía. Únete primero al Eje o a los Aliados.</p></div>`;
    else if (!Game.friendly(P(), r) && !Game.atWar(P(), o) && Game.canDeclare(P(), o)) html += `<button class="btn small" data-act="askWar" data-n="${o}">Declarar la guerra a ${esc(nname(o))}…</button>`;
    if (Game.deployable(P(), r)) {
      html += `<div class="row"><button class="btn small" data-act="build" data-t="inf">Reclutar infantería aquí</button><button class="btn small" data-act="build" data-t="arm">Blindados aquí</button></div>`;
    }
    return html;
  }
  function warBox(o) {
    const f = Game.faction(P()), fo = Game.faction(o);
    const consequence = f ? `${nname(o)} se unirá ${f === 'AX' ? 'a los Aliados' : 'al Eje'}.` : `Te unirás ${fo === 'AX' ? 'a los Aliados' : 'al Eje'} y estarás en guerra con todo su bando contrario.`;
    return `<div class="box" style="border-color:var(--warn)"><b>¿Declarar la guerra a ${esc(nname(o))}?</b><p class="sub">${esc(consequence)} No se puede deshacer.</p>
      <div class="row"><button class="btn danger small" data-act="war" data-n="${o}">Sí, declarar la guerra</button><button class="btn small" data-act="noWar">Cancelar</button></div></div>`;
  }

  function panelBuild() {
    const n = P(), nat = Game.N(n);
    const deps = RIDS.filter(r => Game.deployable(n, r));
    if (!ui.deploy || !deps.includes(ui.deploy)) ui.deploy = deps.includes(ui.sel) ? ui.sel : deps.includes(nat.capital) ? nat.capital : deps[0];
    const card = (t, title, cost, mp, desc, stats) => {
      const chk = Game.canBuild(n, t, t === 'air' ? null : ui.deploy);
      return `<div class="card"><div class="row between"><h4 class="row">${t === 'air' ? `<span style="width:22px;color:var(--brass)">${ICON.air}</span>` : nato(t)}${title}</h4>
        <span class="stats"><span><b>${cost}</b> prod.</span>${mp ? `<span><b>${mp}</b> reclutas</span>` : ''}</span></div>
        <p>${desc}</p><div class="stats">${stats}</div>
        <div class="row"><button class="btn small ${chk.ok ? 'primary' : ''}" data-act="build" data-t="${t}" ${chk.ok ? '' : 'disabled'}>${t === 'air' ? 'Construir aviones' : 'Reclutar'}</button>
        ${t !== 'air' ? `<button class="btn small" data-act="build5" data-t="${t}" ${chk.ok ? '' : 'disabled'}>×5</button>` : ''}
        ${chk.ok ? '' : `<span class="sub">${esc(chk.reason)}</span>`}</div></div>`;
    };
    return `<div><p class="eyebrow">Producción</p><h2 class="h">Fábricas y reclutas</h2></div>
      <p class="sub">Cada mes recibes <b>+${Game.income(n)}</b> de producción y <b>+${Game.mpIncome(n)}</b> reclutas. Las divisiones nuevas aparecen sin movimientos: podrán actuar el mes que viene.</p>
      <label class="sub" for="deploySel">Desplegar en</label>
      <select id="deploySel">${deps.map(r => `<option value="${r}" ${r === ui.deploy ? 'selected' : ''}>${esc(REG[r].name)} (${Game.stackCount(n, r)}/${Game.STACK})</option>`).join('')}</select>
      ${card('inf', 'Infantería', UNIT.inf.pp, UNIT.inf.mp, 'Barata y buena defendiendo. La base de cualquier frente.', '<span>Ataque <b>2</b></span><span>Defensa <b>3</b></span><span>Mueve <b>1</b></span>')}
      ${card('arm', 'Blindados', UNIT.arm.pp, UNIT.arm.mp, 'Muy fuertes atacando en llanuras y desiertos; pierden fuerza en bosques, montañas y pantanos.', '<span>Ataque <b>5</b></span><span>Defensa <b>3</b></span><span>Mueve <b>2</b></span>')}
      ${card('air', 'Aviación', Game.AIR_COST, 0, 'Cada punto suma a tu fuerza aérea. Si tienes más aviones que tu enemigo, ganas ventaja en todas las batallas contra él.', `<span>Tienes <b>${nat.air}</b></span>`)}`;
  }

  function panelFocus() {
    const n = P(), nat = Game.N(n);
    const list = Game.focusList(n);
    if (!list.length) return `<p class="empty">Esta nación no tiene focos nacionales.</p>`;
    const act = nat.focus && list.find(f => f.id === nat.focus.id);
    let html = `<div><p class="eyebrow">Focos nacionales</p><h2 class="h">Decisiones históricas</h2></div>
      <p class="sub">Elige un foco: tarda unos meses y después da su efecto. Solo puede haber uno activo a la vez.</p>`;
    if (act) html += `<div class="card active"><div class="row between"><h4>${esc(act.name)}</h4><span class="tag brass">En curso</span></div>
      <div class="progress"><i style="width:${nat.focus.progress / act.turns * 100}%"></i></div>
      <p class="sub">${nat.focus.progress} de ${act.turns} meses · ${esc(act.desc)}</p></div>`;
    const order = { available: 0, locked: 1, done: 2, active: 3 };
    const items = list.map(f => ({ f, st: Game.focusState(n, f) })).filter(x => x.st.st !== 'active').sort((a, b) => order[a.st.st] - order[b.st.st]);
    html += items.map(({ f, st }) => `<div class="card ${st.st}"><div class="row between"><h4>${esc(f.name)}</h4>
      <span class="tag ${st.st === 'done' ? 'good' : ''}">${st.st === 'done' ? 'Hecho' : f.turns + (f.turns === 1 ? ' mes' : ' meses')}</span></div>
      <p>${esc(f.desc)}</p><p class="hist">${esc(f.hist)}</p>
      ${st.st === 'available' ? (ui.focusConfirm === f.id
        ? `<div class="row"><span class="sub">Perderás el progreso de «${esc(act.name)}».</span><button class="btn small primary" data-act="focus" data-id="${f.id}" data-force="1">Cambiar</button><button class="btn small" data-act="focusCancel">Cancelar</button></div>`
        : `<div><button class="btn small primary" data-act="focus" data-id="${f.id}">Empezar</button></div>`)
        : st.st === 'locked' ? `<p class="sub">🔒 ${esc(st.reason)}</p>` : ''}</div>`).join('');
    return html;
  }

  function panelWar() {
    const p = P();
    const ax = Game.factionVP('AX'), al = Game.factionVP('AL');
    const group = f => Object.keys(G().nations).filter(n => Game.alive(n) && Game.faction(n) === f);
    const neutral = Object.keys(G().nations).filter(n => Game.alive(n) && !Game.faction(n));
    const row = n => {
      const [rel, c] = relation(n);
      const cd = Game.canDeclare(p, n);
      return `<div class="nrow"><i class="chip-sw" style="background:${color(n)}"></i><span class="grow">${esc(nname(n))} <span class="sub">${n === 'USA' ? '' : Game.regionCount(n) + ' reg.'}</span></span>
        <span class="tag ${c}">${rel}</span>${cd && !Game.faction(n) ? `<button class="btn small" data-act="askWarTab" data-n="${n}">Guerra</button>` : ''}</div>`;
    };
    const mine = new Set([p]);
    const logs = G().log.filter(l => l.type !== 'battle' || l.who.some(w => mine.has(w))).slice(-14).reverse();
    return `<div><p class="eyebrow">Situación</p><h2 class="h">La guerra en Europa</h2></div>
      <div class="box"><div class="row between"><b>Puntos de victoria</b><span class="stats"><span>Eje <b>${ax.s}</b></span><span>Aliados <b>${al.s}</b></span><span>de <b>${ax.tot}</b></span></span></div>
      <div class="vpbar"><i style="width:${ax.s / ax.tot * 100}%;background:var(--axis)"></i><i style="width:${(ax.tot - ax.s - al.s) / ax.tot * 100}%;background:var(--neutral)"></i><i style="width:${al.s / ax.tot * 100}%;background:var(--allies)"></i></div>
      <p class="sub">Al acabar la guerra (agosto de 1945) gana el bando con más puntos. Si todas las potencias enemigas se rinden, ganas antes.</p></div>
      ${ui.confirmWar && Game.canDeclare(p, ui.confirmWar) ? warBox(ui.confirmWar) : ''}
      <div class="nations"><p class="eyebrow">Eje</p>${group('AX').map(row).join('') || '<p class="empty">Nadie</p>'}</div>
      <div class="nations"><p class="eyebrow">Aliados</p>${group('AL').map(row).join('') || '<p class="empty">Nadie</p>'}</div>
      <div class="nations"><p class="eyebrow">Neutrales</p>${neutral.map(row).join('') || '<p class="empty">Nadie</p>'}</div>
      <div><p class="eyebrow">Últimos acontecimientos</p><ul class="loglist">${logs.map(l => `<li class="${l.type}"><small>${Game.dateText(l.t)}</small>${esc(l.text)}</li>`).join('')}</ul></div>`;
  }

  $('#panel').addEventListener('change', e => {
    if (e.target.matches('input[data-uid]')) {
      const id = +e.target.dataset.uid;
      e.target.checked ? ui.selUnits.add(id) : ui.selUnits.delete(id);
      renderHighlights(); renderCounters();
      const hint = $('#panel .box .sub:last-child'); if (hint) renderPanel();
    }
    if (e.target.id === 'deploySel') { ui.deploy = e.target.value; renderPanel(); }
  });
  $('#panel').addEventListener('click', e => {
    const b = e.target.closest('[data-act]'); if (!b) return;
    const a = b.dataset.act;
    if (a === 'selAll') { ui.selUnits = new Set(myUnits(ui.sel).filter(u => u.mv > 0).map(u => u.id)); renderHighlights(); renderCounters(); renderPanel(); }
    if (a === 'selNone') { ui.selUnits = new Set(); renderHighlights(); renderCounters(); renderPanel(); }
    if (a === 'nextReady') nextReady();
    if (a === 'build' || a === 'build5') {
      const t = b.dataset.t;
      const where = ui.tab === 'region' ? ui.sel : ui.deploy;
      let made = 0;
      for (let i = 0; i < (a === 'build5' ? 5 : 1); i++) { const res = Game.build(P(), t, t === 'air' ? null : where); if (!res.ok) { if (!made) toast(res.reason); break; } made++; }
      if (made) toast(t === 'air' ? '+1 de aviación.' : made + ' ' + (t === 'inf' ? 'infantería' : 'blindados') + ' en ' + REG[where].name + '. Podrán moverse el mes que viene.');
      renderCounters(); renderTop(); renderPanel(); renderAdvisor();
    }
    if (a === 'focus') {
      const nat = Game.N(P());
      if (nat.focus && !b.dataset.force) { ui.focusConfirm = b.dataset.id; renderPanel(); return; }
      nat.focus = null; ui.focusConfirm = null;
      if (Game.setFocus(P(), b.dataset.id)) toast('Foco iniciado.');
      renderPanel(); renderTop(); renderAdvisor();
    }
    if (a === 'focusCancel') { ui.focusConfirm = null; renderPanel(); }
    if (a === 'askWar' || a === 'askWarTab') { ui.confirmWar = b.dataset.n; renderPanel(); }
    if (a === 'noWar') { ui.confirmWar = null; renderPanel(); }
    if (a === 'war') {
      const n = b.dataset.n;
      if (Game.declareWar(P(), n)) toast('Has declarado la guerra a ' + nname(n) + '.');
      ui.confirmWar = null;
      paintRegions(); renderTop(); renderHighlights(); renderCounters(); renderPanel(); renderAdvisor();
    }
  });
  function nextReady() {
    const regs = [...new Set(G().units.filter(u => u.n === P() && u.mv > 0).map(u => u.r))];
    if (!regs.length) return toast('Todas tus divisiones han actuado.');
    const i = (regs.indexOf(ui.sel) + 1) % regs.length;
    select(regs[i]); centerOn(regs[i]);
  }

  // ---------- combate ----------
  function openBattle(target) {
    const srcUnits = {};
    const add = (r, us) => { if (us.length) srcUnits[r] = us; };
    add(ui.sel, selectedUnits());
    for (const r of LAND[target].concat(SEA[target])) {
      if (r === ui.sel) continue;
      const sea = !LAND[target].includes(r);
      add(r, myUnits(r).filter(u => u.mv > 0 && (!sea || u.mv >= UNIT[u.t].mv)));
    }
    const chosen = new Set([ui.sel]);
    ui.modalClosable = true;
    const draw = () => {
      const units = [...chosen].flatMap(r => srcUnits[r] || []);
      const o = Game.battleOdds(units, target);
      const defN = G().owner[target];
      const li = ([t, m]) => `<li><span>${esc(t)}</span><span class="${m >= 1 ? 'up' : 'down'}">×${m.toFixed(2)}</span></li>`;
      openModal(`<div><p class="eyebrow">Ataque</p><h2 class="h">${esc(REG[target].name)}</h2><p class="sub">Defiende ${esc(nname(defN))} · ${Game.TERRAIN[REG[target].terrain].name}${G().fort[target] ? ' · fortificación ' + G().fort[target] : ''}</p></div>
        <div class="vs"><div class="side"><span class="sub">Tu ataque</span><span class="num">${o.A.toFixed(1)}</span><span class="sub">${units.length} divisiones</span></div>
        <div class="odds"><b style="color:${o.p >= 0.7 ? 'var(--good)' : o.p >= 0.45 ? 'var(--warn)' : 'var(--bad)'}">${pct(o.p)}</b><span>Probabilidad de victoria</span></div>
        <div class="side r"><span class="sub">Su defensa</span><span class="num">${o.D.toFixed(1)}</span><span class="sub">${o.defenders.length} divisiones</span></div></div>
        <div class="row" style="align-items:flex-start;gap:16px"><ul class="mods" style="flex:1;min-width:150px">${o.fA.map(li).join('') || '<li class="sub">Sin modificadores</li>'}</ul>
        <ul class="mods" style="flex:1;min-width:150px">${o.fD.map(li).join('') || '<li class="sub">Sin modificadores</li>'}</ul></div>
        <div class="srcs"><p class="eyebrow">Atacar desde</p>${Object.keys(srcUnits).map(r => `<label class="check"><input type="checkbox" data-src="${r}" ${chosen.has(r) ? 'checked' : ''}>
          ${esc(REG[r].name)}: ${srcUnits[r].length} divisiones${LAND[target].includes(r) ? '' : ' <span class="tag warn">desembarco</span>'}</label>`).join('')}</div>
        <p class="sub">Si ganas, tus tropas entran en la región y el defensor se retira. Si no tiene a dónde retirarse, queda rodeado. Las unidades que atacan no pueden volver a moverse este mes.</p>
        <div class="foot"><button class="btn" data-m="cancel">Cancelar</button><button class="btn primary" data-m="go" ${units.length ? '' : 'disabled'}>¡Atacar! (${pct(o.p)})</button></div>`);
      $('#modalCard').onchange = e => { const r = e.target.dataset.src; if (!r) return; e.target.checked ? chosen.add(r) : chosen.delete(r); draw(); };
      $('#modalCard').onclick = e => {
        const m = e.target.closest('[data-m]'); if (!m) return;
        if (m.dataset.m === 'cancel') closeModal();
        if (m.dataset.m === 'go') {
          ui.lastBattleSrcs = [...chosen];
          const res = Game.attack(units.map(u => u.id), target);
          showResult(res, target);
        }
      };
    };
    draw();
  }
  function showResult(res, target) {
    ui.modalClosable = true;
    if (!res.ok) { closeModal(); toast(res.reason); return; }
    const win = res.win;
    openModal(`<div class="result ${win ? 'win' : 'lose'}"><b>${win ? '¡Victoria!' : 'Ataque rechazado'}</b>
      <p class="sub">${win ? 'Conquistas ' + esc(REG[target].name) + '.' : 'El enemigo resiste en ' + esc(REG[target].name) + '.'} Tenías un ${pct(res.p)} de probabilidad.</p></div>
      <dl class="kv"><dt>Tus bajas</dt><dd>${res.attLoss} puntos de fuerza${res.attDestroyed ? ' · ' + res.attDestroyed + ' divisiones destruidas' : ''}</dd>
      <dt>Bajas enemigas</dt><dd>${res.defLoss} puntos de fuerza${res.defDestroyed ? ' · ' + res.defDestroyed + ' divisiones destruidas' : ''}</dd>
      ${res.encircled ? `<dt>Rodeadas</dt><dd>¡${res.encircled} divisiones enemigas destruidas al no poder retirarse!</dd>` : ''}
      ${res.brokeOut ? `<dt>Cerco</dt><dd>${res.brokeOut} divisiones enemigas escapan con grandes pérdidas.</dd>` : ''}
      ${res.retreatTo ? `<dt>Retirada</dt><dd>El enemigo se retira a ${esc(REG[res.retreatTo].name)}.</dd>` : ''}</dl>
      <p class="sub">Las divisiones dañadas se recuperan solas cada mes si tienen suministro (cuesta algunos reclutas).</p>
      <div class="foot"><button class="btn primary" data-m="ok">Continuar</button></div>`);
    $('#modalCard').onclick = e => { if (e.target.closest('[data-m]')) closeModal(); };
    if (win) { ui.sel = target; ui.selUnits = new Set(); }
    const left = ui.lastBattleSrcs || [];
    const bare = left.filter(r => G().owner[r] === P() && !Game.unitsAt(r).some(u => Game.friendlyNations(u.n, P())) && LAND[r].some(nb => Game.atWar(P(), G().owner[nb])));
    if (win && bare.length) setTimeout(() => toast('Cuidado: ' + bare.map(r => REG[r].name).join(', ') + ' queda sin defensa.'), 300);
    afterAction(); renderHighlights(); renderCounters(); renderPanel();
  }

  // ---------- ventanas ----------
  function openModal(html, wide) {
    const c = $('#modalCard');
    c.className = 'modal-card' + (wide ? ' wide' : '');
    c.innerHTML = html;
    c.onclick = null; c.onchange = null;
    $('#modal').hidden = false;
  }
  function closeModal() { $('#modal').hidden = true; if (ui.afterModal) { const f = ui.afterModal; ui.afterModal = null; f(); } }
  $('#modal').addEventListener('click', e => { if (e.target.id === 'modal' && ui.modalClosable) closeModal(); });

  // ---------- turno ----------
  $('#btnEnd').onclick = endTurn;
  function endTurn() {
    if (!G() || G().over) return;
    $('#busy').hidden = false;
    ui.reportFrom = G().logSeq || 0;
    const prevTurn = G().turn;
    setTimeout(() => {
      try { Game.endTurn(AI.runAI); } catch (err) { console.error(err); }
      $('#busy').hidden = true;
      autosave();
      ui.sel = null; ui.selUnits = new Set();
      paintRegions(); renderTop(); renderHighlights(); renderCounters(); renderPanel(); renderAdvisor();
      if (G().over) return showGameOver();
      showReport(prevTurn);
    }, 40);
  }
  function showReport(prevTurn) {
    const p = P();
    const logs = G().log.filter(l => (l.i || 0) > ui.reportFrom);
    const pops = G().popups || [];
    const myBattles = logs.filter(l => l.type === 'battle' && l.who.includes(p));
    const focusDone = pops.filter(x => x.focus);
    const events = pops.filter(x => !x.focus);
    const diplo = logs.filter(l => l.type === 'diplo');
    const nat = Game.N(p);
    ui.modalClosable = true;
    openModal(`<div><p class="eyebrow">Informe del mando</p><h2 class="h">${Game.dateText()}</h2>
      <p class="sub">Ingresos: +${nat.lastIncome} de producción y +${Game.mpIncome(p)} reclutas. Tus divisiones heridas se han recuperado donde había suministro.</p></div>
      <div class="report">
      ${events.map(e => `<div class="evt"><h4>${esc(e.title)}</h4><p>${esc(e.text)}</p>${e.hist ? `<p class="hist">${esc(e.hist)}</p>` : ''}</div>`).join('')}
      ${focusDone.map(e => `<div class="evt"><h4>✓ ${esc(e.title)}</h4><p>${esc(e.text)}</p></div>`).join('')}
      ${diplo.length ? `<div><p class="eyebrow">Diplomacia</p><ul class="loglist">${diplo.map(l => `<li class="diplo">${esc(l.text)}</li>`).join('')}</ul></div>` : ''}
      <div><p class="eyebrow">Combates contra ti o tuyos (${myBattles.length})</p>${myBattles.length ? `<ul class="loglist">${myBattles.slice(0, 12).map(l => `<li class="battle">${esc(l.text)}</li>`).join('')}</ul>` : '<p class="sub">Frente tranquilo este mes.</p>'}</div>
      </div>
      <div class="foot"><button class="btn primary" data-m="ok">A trabajar</button></div>`);
    $('#modalCard').onclick = e => { if (e.target.closest('[data-m]')) closeModal(); };
    void prevTurn;
  }
  function showGameOver() {
    const o = G().over;
    const st = G().stats;
    const good = /victoria/.test(o.result);
    ui.modalClosable = false;
    openModal(`<div class="result ${good ? 'win' : o.result === 'tablas' ? '' : 'lose'}"><b>${esc(o.result.toUpperCase())}</b><p>${esc(o.text)}</p></div>
      <dl class="kv"><dt>Batallas ganadas</dt><dd>${st.won}</dd><dt>Ataques fallidos</dt><dd>${st.lost}</dd><dt>Regiones conquistadas</dt><dd>${st.captured}</dd>
      <dt>Divisiones enemigas destruidas</dt><dd>${st.destroyed}</dd><dt>Divisiones perdidas</dt><dd>${st.lostUnits}</dd></dl>
      <p class="sub">En la historia real, Alemania se rindió el 8 de mayo de 1945.</p>
      <div class="foot"><button class="btn" data-m="look">Ver el mapa</button><button class="btn primary" data-m="new">Nueva partida</button></div>`);
    $('#modalCard').onclick = e => {
      const m = e.target.closest('[data-m]'); if (!m) return;
      if (m.dataset.m === 'new') { clearSave(); showStart(); }
      else { ui.modalClosable = true; closeModal(); }
    };
  }

  // ---------- asesor ----------
  function advisorTips() {
    const p = P(), nat = Game.N(p), tips = [];
    if (G().over) return tips;
    if (!nat.focus && Game.focusList(p).some(f => Game.focusState(p, f).st === 'available')) tips.push({ cls: '', text: 'No tienes ningún foco nacional en marcha.', btn: 'Elegir', act: () => setTab('focus') });
    if (nat.pp >= UNIT.inf.pp && nat.mp >= UNIT.inf.mp) tips.push({ cls: '', text: `Tienes ${Math.floor(nat.pp)} de producción sin gastar.`, btn: 'Producir', act: () => setTab('build') });
    // mejor ataque disponible
    let best = null;
    const mine = {};
    for (const u of G().units) if (u.n === p && u.mv > 0) (mine[u.r] ||= []).push(u);
    for (const r in mine) for (const t of LAND[r]) {
      if (!Game.atWar(p, G().owner[t])) continue;
      if (!Game.unitsAt(t).length) { if (!best || best.p < 1.5) best = { from: r, to: t, p: 1.5 }; continue; }
      const o = Game.battleOdds(mine[r], t);
      if (o.p >= 0.62 && (!best || o.p > best.p)) best = { from: r, to: t, p: o.p };
    }
    if (best) tips.push({ cls: 'go', text: best.p > 1 ? `${REG[best.to].name} está vacía: ocúpala desde ${REG[best.from].name}.` : `Buena ocasión: atacar ${REG[best.to].name} desde ${REG[best.from].name} (${pct(best.p)}).`, btn: 'Ver', act: () => { select(best.from); centerOn(best.from); } });
    // región en peligro
    let worst = null;
    for (const r of RIDS) {
      if (G().owner[r] !== p) continue;
      let threat = 0;
      for (const nb of LAND[r]) if (Game.atWar(p, G().owner[nb])) for (const u of Game.unitsAt(nb)) threat += UNIT[u.t].atk * u.s / 100;
      if (!threat) continue;
      const def = Game.unitsAt(r).filter(u => Game.friendlyNations(u.n, p)).reduce((s, u) => s + UNIT[u.t].def * u.s / 100, 0) * Game.TERRAIN[REG[r].terrain].def * (1 + 0.25 * (G().fort[r] || 0));
      const risk = threat / Math.max(def, 0.5) * (1 + REG[r].vp * 0.3);
      if (threat > def * 1.1 && (!worst || risk > worst.risk)) worst = { r, risk };
    }
    if (worst) tips.push({ cls: 'warn', text: `${REG[worst.r].name} está en peligro: el enemigo es más fuerte allí. Refuérzala.`, btn: 'Ver', act: () => { select(worst.r); centerOn(worst.r); } });
    const nosup = G().units.filter(u => u.n === p && !Game.inSupply(p, u.r));
    if (nosup.length) tips.push({ cls: 'warn', text: `${nosup.length} divisiones sin suministro: pierden fuerza cada mes. Abre un camino hasta ellas.`, btn: 'Ver', act: () => { select(nosup[0].r); centerOn(nosup[0].r); } });
    if (!Game.faction(p)) tips.push({ cls: '', text: p === 'SOV' ? 'Estás en paz. Alemania atacará tarde o temprano: fortifica la frontera occidental.' : p === 'ITA' ? 'Estás en paz. El foco «Entrar en la guerra» te une al Eje cuando quieras.' : 'Estás en paz.', btn: 'Focos', act: () => setTab('focus') });
    return tips.slice(0, 3);
  }
  function renderAdvisor() {
    const box = $('#advisor');
    if (ui.hideAdvisor) { box.innerHTML = `<div class="adv-head"><span></span><button data-adv="show">Mostrar asesor</button></div>`; return; }
    const tips = advisorTips();
    box.innerHTML = tips.length ? `<div class="adv-head"><span>Asesor</span><button data-adv="hide">Ocultar</button></div>` +
      tips.map((t, i) => `<div class="tipcard ${t.cls}"><p>${esc(t.text)}</p><button class="btn small" data-tipi="${i}">${t.btn}</button></div>`).join('') : '';
    $('#btnEnd').classList.toggle('pulse', !G().units.some(u => u.n === P() && u.mv > 0));
    box.onclick = e => {
      const b = e.target.closest('[data-tipi]');
      if (b) tips[+b.dataset.tipi].act();
      const a = e.target.closest('[data-adv]');
      if (a) { ui.hideAdvisor = a.dataset.adv === 'hide'; renderAdvisor(); }
    };
  }

  // ---------- ayuda ----------
  $('#btnHelp').onclick = showHelp;
  function showHelp() {
    ui.modalClosable = true;
    const T = Game.TERRAIN;
    openModal(`<div><p class="eyebrow">Manual de campaña</p><h2 class="h">Cómo se juega</h2></div>
      <div class="rules">
      <p>Cada turno es <b>un mes</b>, de septiembre de 1939 a agosto de 1945. En tu turno das órdenes; al pulsar <b>Terminar turno</b> mueven las demás naciones y recibes un informe.</p>
      <h3>1 · Produce</h3><p>La <b>producción</b> sale de la industria de tus regiones. Con ella reclutas infantería, blindados y aviones (pestaña Producir). Los <b>reclutas</b> también hacen falta para reponer bajas.</p>
      <h3>2 · Mueve y ataca</h3><ul><li>Haz clic en una región tuya con tropas: quedan seleccionadas.</li>
      <li>Clic en una vecina <b style="color:var(--good)">verde</b>: mueves. Clic en una <b style="color:var(--bad)">roja</b>: ves tu % de victoria y decides si atacar. Puedes sumar tropas de varias regiones.</li>
      <li>Si no se han movido, tus tropas pueden viajar por <b>ferrocarril</b> a cualquier región tuya conectada, o cruzar por los <b>pasos marítimos</b> (líneas discontinuas).</li>
      <li>Como máximo ${Game.STACK} divisiones por región.</li></ul>
      <h3>3 · Elige focos nacionales</h3><p>Decisiones históricas que tardan unos meses: más industria, nuevas divisiones, alianzas, invasiones…</p>
      <h3>4 · Suministro y cercos</h3><p>Tus tropas necesitan un camino por territorio amigo hasta tu capital o un puerto. Sin suministro pierden fuerza. Si el defensor pierde y no tiene a dónde retirarse, queda <b>rodeado</b>.</p>
      <h3>5 · Victoria</h3><p>Un país se rinde si pierde su capital y buena parte de sus ciudades (puntos de victoria). Al final gana el bando con más puntos de victoria.</p>
      <h3>Unidades</h3><div class="tbl"><table><tr><th>Unidad</th><th class="n">Ataque</th><th class="n">Defensa</th><th class="n">Mueve</th><th class="n">Coste</th></tr>
      <tr><td>Infantería</td><td class="n">2</td><td class="n">3</td><td class="n">1</td><td class="n">${UNIT.inf.pp} + ${UNIT.inf.mp} rec.</td></tr>
      <tr><td>Blindados</td><td class="n">5</td><td class="n">3</td><td class="n">2</td><td class="n">${UNIT.arm.pp} + ${UNIT.arm.mp} rec.</td></tr></table></div>
      <h3>Terreno</h3><div class="tbl"><table><tr><th>Terreno</th><th class="n">Defensa</th><th class="n">Blindados al atacar</th></tr>
      ${Object.values(T).map(t => `<tr><td>${t.name}</td><td class="n">×${t.def}</td><td class="n">×${t.arm}</td></tr>`).join('')}</table></div>
      <h3>Otros factores</h3><ul><li>Fortificaciones: +25 % de defensa por nivel (Línea Maginot = 3).</li><li>Desembarcos: −60 % de ataque (−75 % contra Gran Bretaña) salvo con un foco que los prepare.</li>
      <li>Invierno ruso (dic.–feb.): −40 % de ataque contra la URSS y Finlandia.</li><li>Lejos de casa: −5 % de ataque por región de distancia de tu territorio.</li><li>Defender la patria: +15 % de defensa.</li></ul>
      </div><div class="foot"><button class="btn" data-m="tut">Repetir tutorial</button><button class="btn primary" data-m="ok">Entendido</button></div>`, true);
    $('#modalCard').onclick = e => {
      const m = e.target.closest('[data-m]'); if (!m) return;
      closeModal();
      if (m.dataset.m === 'tut') startTutorial();
    };
  }

  // ---------- menú ----------
  $('#btnMenu').onclick = () => {
    ui.modalClosable = true;
    openModal(`<div><p class="eyebrow">Menú</p><h2 class="h">Partida</h2></div>
      <p class="sub">La partida se guarda sola en este navegador al final de cada turno.</p>
      <div class="row"><button class="btn" data-m="save">Guardar ahora</button><button class="btn" data-m="load" ${hasSave() ? '' : 'disabled'}>Cargar lo guardado</button></div>
      <div class="row"><button class="btn danger" data-m="new">Abandonar y empezar otra</button></div>
      <div class="foot"><button class="btn primary" data-m="close">Volver al juego</button></div>`);
    $('#modalCard').onclick = e => {
      const m = e.target.closest('[data-m]'); if (!m) return;
      const a = m.dataset.m;
      if (a === 'save') { toast(autosave() ? 'Partida guardada.' : 'No se pudo guardar en este navegador.'); closeModal(); }
      if (a === 'load') { if (loadSave()) { closeModal(); startUI(); toast('Partida cargada.'); } }
      if (a === 'new') { showStart(); }
      if (a === 'close') closeModal();
    };
  };
  function autosave() { try { localStorage.setItem(SAVE_KEY, Game.save()); return true; } catch (e) { return false; } }
  function hasSave() { try { return !!localStorage.getItem(SAVE_KEY); } catch (e) { return false; } }
  function loadSave() { try { const s = localStorage.getItem(SAVE_KEY); if (!s) return false; Game.load(s); return true; } catch (e) { return false; } }
  function clearSave() { try { localStorage.removeItem(SAVE_KEY); } catch (e) { /* sin almacenamiento */ } }

  // ---------- pantalla inicial ----------
  function showStart() {
    ui.modalClosable = false;
    let pick = 'ENG', diff = 'normal', tut = true;
    const draw = () => {
      const pl = D.playable.find(x => x.code === pick);
      openModal(`<div><h1 class="title">Frentes <span>de</span> Acero</h1></div>
        <p class="lead">La Segunda Guerra Mundial en Europa, con reglas que se aprenden en cinco minutos. Mapa real de 1939, focos nacionales y eventos históricos.</p>
        <div class="howto"><div><b>1 turno = 1 mes</b>De septiembre de 1939 a agosto de 1945.</div><div><b>Produce</b>Fábricas y reclutas se convierten en divisiones.</div>
        <div><b>Ataca sin sorpresas</b>Antes de cada batalla ves tu probabilidad de ganar.</div><div><b>Decide como en la historia</b>Focos nacionales y eventos reales.</div></div>
        <div><p class="eyebrow">Elige tu nación</p><div class="picks">${D.playable.map(x => `<button class="pick ${x.code === pick ? 'on' : ''}" data-pick="${x.code}">
          <h4><i class="chip-sw" style="background:${color(x.code)}"></i>${esc(nname(x.code))}</h4><span class="stars">Dificultad ${'●'.repeat(x.stars)}${'○'.repeat(3 - x.stars)}</span><p>${esc(x.pitch)}</p></button>`).join('')}</div></div>
        <div class="goal"><b>Tu objetivo:</b> ${esc(pl.goal)}</div>
        <div class="row between"><div class="seg" id="diffSeg">${Object.entries(Game.DIFF).map(([k, v]) => `<button data-diff="${k}" class="${k === diff ? 'on' : ''}">${v.name}</button>`).join('')}</div>
        <label class="check"><input type="checkbox" id="tutChk" ${tut ? 'checked' : ''}> Tutorial guiado</label></div>
        <div class="foot">${hasSave() ? '<button class="btn" data-m="continue">Continuar partida guardada</button>' : ''}<button class="btn primary" data-m="start">Comenzar la guerra</button></div>`, true);
      $('#modalCard').onclick = e => {
        const pb = e.target.closest('[data-pick]'); if (pb) { pick = pb.dataset.pick; draw(); return; }
        const db = e.target.closest('[data-diff]'); if (db) { diff = db.dataset.diff; draw(); return; }
        const m = e.target.closest('[data-m]'); if (!m) return;
        if (m.dataset.m === 'continue' && loadSave()) { ui.modalClosable = true; closeModal(); startUI(); return; }
        if (m.dataset.m === 'start') {
          Game.newGame(pick, diff, Date.now());
          ui.modalClosable = true; closeModal(); startUI();
          autosave();
          if (tut) startTutorial(); else showIntro();
        }
      };
      $('#modalCard').onchange = e => { if (e.target.id === 'tutChk') tut = e.target.checked; };
    };
    draw();
  }
  function showIntro() {
    const pl = D.playable.find(x => x.code === P());
    ui.modalClosable = true;
    openModal(`<div><p class="eyebrow">1 de septiembre de 1939</p><h2 class="h">Comienza la guerra</h2></div>
      <p>Alemania invade Polonia. El Reino Unido y Francia le declaran la guerra.</p>
      ${pl ? `<div class="goal"><b>Tu objetivo:</b> ${esc(pl.goal)}</div>` : ''}
      <div class="foot"><button class="btn primary" data-m="ok">A las órdenes</button></div>`);
    $('#modalCard').onclick = e => { if (e.target.closest('[data-m]')) closeModal(); };
  }

  // ---------- tutorial ----------
  const TUT = [
    { sel: null, title: 'Bienvenido, comandante', text: () => `Diriges ${nname(P())}. ${D.playable.find(x => x.code === P()).goal} Este tutorial dura un minuto.` },
    { sel: '#tbRes', title: 'Tus recursos', text: () => 'Producción para fabricar, reclutas para formar y reponer divisiones, y aviación, que da ventaja en todas las batallas. El número verde es lo que ganas cada mes.' },
    { sel: '#mapWrap', title: 'El mapa', text: () => 'Cada color es un país. Las fichas son ejércitos: ⊠ infantería y ⬭ blindados, con su número. El punto verde indica que aún pueden moverse. Arrastra para moverte y usa la rueda o los botones para el zoom.' },
    { sel: '#tabs [data-tab="focus"]', tab: 'focus', title: 'Focos nacionales', text: () => 'Decisiones históricas que tardan unos meses. Empieza uno ahora: el asesor te avisará si se te olvida.' },
    { sel: '#tabs [data-tab="build"]', tab: 'build', title: 'Producir', text: () => 'Gasta tu producción en divisiones. Aparecen en la región que elijas y podrán moverse el mes siguiente.' },
    { sel: '#mapWrap', title: 'Mover y atacar', text: () => 'Haz clic en una región tuya con tropas. Las vecinas verdes son para moverte; las rojas muestran tu probabilidad de victoria. Nunca atacas a ciegas.' },
    { sel: '#advisor', title: 'El asesor', text: () => 'Aquí verás consejos cada mes: buenas ocasiones de ataque, regiones en peligro y recursos sin usar.' },
    { sel: '#btnEnd', title: 'Terminar el turno', text: () => 'Cuando acabes, pulsa aquí. Las demás naciones mueven y recibes un informe con lo que ha pasado, incluido lo que ocurrió en la historia real.' },
  ];
  function startTutorial() { ui.tut = 0; $('#tut').hidden = false; drawTut(); }
  function drawTut() {
    const step = TUT[ui.tut];
    if (!step) { $('#tut').hidden = true; ui.tut = -1; return; }
    if (step.tab) setTab(step.tab);
    const ring = $('#tutRing'), card = $('#tutCard');
    const target = step.sel && $(step.sel);
    const r = target && target.offsetParent !== null ? target.getBoundingClientRect() : null;
    if (r && r.width) Object.assign(ring.style, { display: 'block', left: r.left - 4 + 'px', top: r.top - 4 + 'px', width: r.width + 8 + 'px', height: r.height + 8 + 'px' });
    else Object.assign(ring.style, { display: 'block', left: innerWidth / 2 + 'px', top: innerHeight / 2 + 'px', width: '0px', height: '0px' });
    card.innerHTML = `<span class="stepn">${ui.tut + 1} / ${TUT.length}</span><h4>${esc(step.title)}</h4><p>${esc(step.text())}</p>
      <div class="row between"><button class="btn small ghost" data-t="skip">Saltar</button><button class="btn small primary" data-t="next">${ui.tut === TUT.length - 1 ? '¡A jugar!' : 'Siguiente'}</button></div>`;
    const cw = Math.min(340, innerWidth - 32), ch = card.offsetHeight || 180;
    let left, top;
    if (!r || !r.width) { left = (innerWidth - cw) / 2; top = (innerHeight - ch) / 2; }
    else if (r.width > innerWidth * 0.5 && r.height > innerHeight * 0.4) { left = r.left + 24; top = r.top + 24; }
    else { left = Math.min(Math.max(16, r.left), innerWidth - cw - 16); top = r.bottom + 14 + ch > innerHeight ? r.top - ch - 14 : r.bottom + 14; }
    card.style.left = Math.max(16, left) + 'px'; card.style.top = Math.max(16, top) + 'px';
    card.onclick = e => {
      const b = e.target.closest('[data-t]'); if (!b) return;
      if (b.dataset.t === 'skip') ui.tut = TUT.length; else ui.tut++;
      drawTut();
    };
  }
  window.addEventListener('resize', () => { if (ui.tut >= 0) drawTut(); });

  // ---------- tooltips ----------
  const tip = $('#tip');
  document.addEventListener('pointerover', e => {
    const t = e.target.closest && e.target.closest('[data-tip]');
    if (!t || e.pointerType === 'touch') { tip.hidden = true; return; }
    tip.textContent = t.dataset.tip; tip.hidden = false;
    const r = t.getBoundingClientRect();
    tip.style.left = Math.min(innerWidth - 290, Math.max(8, r.left)) + 'px';
    tip.style.top = (r.bottom + 8) + 'px';
  });

  // ---------- arranque ----------
  let built = false;
  function startUI() {
    if (!built) { buildMap(); built = true; }
    ui.sel = null; ui.selUnits = new Set(); ui.tab = 'region'; ui.confirmWar = null;
    paintRegions(); renderTop();
    setView(0, 0, M.W);
    homeView();
    renderHighlights(); renderCounters(); setTab('region'); renderAdvisor();
    if (G().over) showGameOver();
  }
  function boot() {
    buildMap(); built = true;
    Game.newGame('ENG', 'normal', 1);
    paintRegions(); renderTop(); setView(0, 0, M.W); renderCounters(); setTab('region'); renderAdvisor();
    showStart();
  }
  window.UI = { ui, select, endTurn, startUI, showStart, regionClick, setView };
  boot();
})();
