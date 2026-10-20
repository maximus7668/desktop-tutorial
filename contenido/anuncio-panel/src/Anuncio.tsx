import React from 'react';
import { AbsoluteFill, Audio, Easing, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { loadFont } from '@remotion/fonts';
import cajas from './cajas.json';
import { ESCENAS, FPS, durDe, inicioDe, totalFrames } from './guion';

const FUENTE = 'Manrope';
for (const w of ['500', '600', '700', '800']) loadFont({ family: FUENTE, url: staticFile(`manrope-latin-${w}-normal.woff2`), weight: w });

const AZUL = '#3B5BDB';
const AZUL_CLARO = '#9DB0FF';
const TINTA = '#12162B';
const FONDO = '#F6F7FB';
const ROJO = '#E03131';

// Pantalla del móvil en píxeles CSS (390 de ancho, 44 de barra de estado + 844 de app).
const SW = 390;
const BARRA = 44;
const SH = BARRA + 844;
const ANCHO_PANTALLA = 600;
const K = ANCHO_PANTALLA / SW;
const BISEL = 16;
const MOVIL_X = (1080 - (ANCHO_PANTALLA + BISEL * 2)) / 2;
const MOVIL_Y = 430;
// Punto del lienzo donde se coloca lo que se amplía (debajo del texto).
const DIANA = { x: 540, y: 1200 };

// Punto de la app (coordenadas de la captura) → punto del lienzo, sin zoom.
const aLienzo = (x: number, y: number) => ({ x: MOVIL_X + BISEL + x * K, y: MOVIL_Y + BISEL + (BARRA + y) * K });
type Caja = { x: number; y: number; width: number; height: number };
const centro = (c: Caja) => aLienzo(c.x + c.width / 2, c.y + c.height / 2);

const f = (id: Parameters<typeof inicioDe>[0], seg = 0) => inicioDe(id) + Math.round(seg * FPS);
const suave = Easing.inOut(Easing.cubic);

// ---------- Cámara ----------
type Plano = { f: number; s: number; x: number; y: number };
const BASE = { s: 1, ...DIANA };
const zoom = (c: Caja, s: number) => ({ s, ...centro(c) });
const INTRO = { s: 1.25, x: 540, y: MOVIL_Y + BISEL + 355 * K };
const PLANOS: Plano[] = [
  { f: 0, ...INTRO },
  { f: f('intro', 2.6), ...INTRO },
  { f: f('panel', 0.4), ...BASE },
  { f: f('panel', 1.1), ...zoom(cajas.resumen, 1.42) },
  { f: f('llamadas'), ...zoom(cajas.resumen, 1.42) },
  { f: f('llamadas', 0.45), ...BASE },
  { f: f('llamadas', 1.45), ...BASE },
  { f: f('llamadas', 2.1), ...zoom(cajas.detalle, 1.4) },
  { f: f('escuchar'), ...zoom(cajas.detalle, 1.4) },
  { f: f('escuchar', 0.4), ...zoom({ x: 17, y: 470, width: 356, height: 250 }, 1.42) },
  { f: f('agenda'), ...zoom({ x: 17, y: 470, width: 356, height: 250 }, 1.42) },
  { f: f('agenda', 0.4), ...BASE },
  { f: f('agenda', 0.8), ...BASE },
  { f: f('agenda', 1.5), ...zoom(cajas.citaDeika, 1.6) },
  { f: f('urgente'), ...zoom(cajas.citaDeika, 1.6) },
  { f: f('urgente', 0.4), s: 1.22, x: 540, y: MOVIL_Y + BISEL + 300 * K },
  { f: f('recepcion'), s: 1.22, x: 540, y: MOVIL_Y + BISEL + 300 * K },
  { f: f('recepcion', 0.4), ...BASE },
  { f: f('recepcion', 1.4), ...BASE },
  { f: f('recepcion', 2.1), ...zoom(cajas.horarioEdit, 1.45) },
  { f: f('cierre'), ...zoom(cajas.horarioEdit, 1.45) },
];
const camara = (fr: number) => {
  let i = PLANOS.findIndex((p) => p.f > fr);
  if (i === -1) return PLANOS[PLANOS.length - 1];
  if (i === 0) return PLANOS[0];
  const a = PLANOS[i - 1];
  const b = PLANOS[i];
  const t = suave(Math.min(1, Math.max(0, (fr - a.f) / (b.f - a.f))));
  return { f: fr, s: a.s + (b.s - a.s) * t, x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t };
};

// ---------- Pantallas ----------
const PANTALLAS: { desde: number; img: string | 'bloqueo' }[] = [
  { desde: 0, img: 'bloqueo' },
  { desde: f('panel'), img: 'agenda.png' },
  { desde: f('llamadas'), img: 'llamadas.png' },
  { desde: f('llamadas', 1.25), img: 'llamada-abierta.png' },
  { desde: f('escuchar'), img: 'llamada-conversacion.png' },
  { desde: f('agenda'), img: 'agenda-citas.png' },
  { desde: f('urgente'), img: 'llamada-urgente.png' },
  { desde: f('recepcion'), img: 'recepcion.png' },
  { desde: f('recepcion', 1.15), img: 'recepcion-editar.png' },
];
const TOQUES = [
  { x: 195, y: 318, f: f('intro', 2.45), bloqueo: true },
  { x: cajas.filaLaura.x + 120, y: cajas.filaLaura.y + cajas.filaLaura.height / 2, f: f('llamadas', 1.0) },
  { x: 60, y: 511, f: f('escuchar', 0.35) },
  { x: cajas.editar.x + cajas.editar.width / 2, y: cajas.editar.y + cajas.editar.height / 2, f: f('recepcion', 0.9) },
];

const Toque: React.FC<{ x: number; y: number; desde: number }> = ({ x, y, desde }) => {
  const fr = useCurrentFrame() - desde;
  if (fr < 0 || fr > 18) return null;
  const r = interpolate(fr, [0, 18], [10, 46], { easing: Easing.out(Easing.quad) });
  const o = interpolate(fr, [0, 4, 18], [0, 0.55, 0], { extrapolateRight: 'clamp' });
  return <div style={{ position: 'absolute', left: x - r, top: y - r, width: r * 2, height: r * 2, borderRadius: '50%', background: TINTA, opacity: o }} />;
};

const BarraEstado: React.FC<{ claro?: boolean }> = ({ claro }) => {
  const c = claro ? '#fff' : TINTA;
  return (
    <div style={{ position: 'absolute', top: 0, left: 0, width: SW, height: BARRA, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '6px 28px 0 34px', boxSizing: 'border-box', color: c, fontWeight: 700, fontSize: 15 }}>
      <span>11:47</span>
      <div style={{ width: 110, height: 30, borderRadius: 20, background: '#000', position: 'absolute', left: SW / 2 - 55, top: 9 }} />
      <svg width="66" height="14" viewBox="0 0 66 14" fill={c}>
        <rect x="0" y="9" width="3" height="5" rx="1" /><rect x="5" y="6" width="3" height="8" rx="1" /><rect x="10" y="3" width="3" height="11" rx="1" /><rect x="15" y="0" width="3" height="14" rx="1" />
        <path d="M30 4a10 10 0 0 1 13 0l-1.6 1.7a7.6 7.6 0 0 0-9.8 0zM33 7.3a5.6 5.6 0 0 1 7 0l-1.7 1.8a3 3 0 0 0-3.6 0zM36.5 11l1.5 1.6-1.5 1.5-1.5-1.5z" />
        <rect x="46" y="1" width="18" height="11" rx="3" fill="none" stroke={c} strokeOpacity="0.5" /><rect x="48" y="3" width="13" height="7" rx="1.5" />
      </svg>
    </div>
  );
};

const Notificacion: React.FC<{ titulo: string; cuerpo: string; claro?: boolean }> = ({ titulo, cuerpo, claro }) => (
  <div style={{ background: claro ? 'rgba(250,250,252,0.97)' : 'rgba(255,255,255,0.86)', borderRadius: 22, padding: '11px 14px', display: 'flex', gap: 11, alignItems: 'center', boxShadow: claro ? '0 10px 30px rgba(18,22,43,0.22)' : 'none' }}>
    <div style={{ width: 38, height: 38, borderRadius: 10, background: '#fff', border: '1px solid #e6e8f0', display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 'none' }}>
      <Img src={staticFile('marca.png')} style={{ width: 28 }} />
    </div>
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#6b7085', fontWeight: 600 }}><span>DEIKA</span><span>ahora</span></div>
      <div style={{ fontSize: 15, fontWeight: 800, color: TINTA, marginTop: 1 }}>{titulo}</div>
      <div style={{ fontSize: 14, color: '#3b4054', lineHeight: 1.25, fontWeight: 500 }}>{cuerpo}</div>
    </div>
  </div>
);

const AVISOS_BLOQUEO = [
  { titulo: 'Nueva cita', cuerpo: 'Laura Pérez · Corte y color · jueves 22, 10:00' },
  { titulo: 'Llamada urgente', cuerpo: 'Raúl Castro · Le pica la cabeza tras el tinte' },
  { titulo: 'Nueva cita', cuerpo: 'Elena Moreno · Mechas · sábado 24, 11:00' },
  { titulo: 'Cita cambiada', cuerpo: 'Carmen López · ahora el sábado 24, 12:00' },
];

const Bloqueo: React.FC = () => {
  const fr = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill style={{ background: 'linear-gradient(165deg, #2a3570 0%, #161b3a 55%, #0d1024 100%)' }}>
      <div style={{ position: 'absolute', top: 92, width: SW, textAlign: 'center', color: '#fff' }}>
        <div style={{ fontSize: 18, fontWeight: 600, opacity: 0.85 }}>martes, 20 de octubre</div>
        <div style={{ fontSize: 88, fontWeight: 700, letterSpacing: -2, lineHeight: 1 }}>11:47</div>
      </div>
      <div style={{ position: 'absolute', top: 280, left: 12, width: SW - 24, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {AVISOS_BLOQUEO.map((a, i) => {
          const d = Math.round(0.25 * fps) + i * Math.round(0.42 * fps);
          const p = spring({ frame: fr - d, fps, config: { damping: 16, stiffness: 160 } });
          return (
            <div key={i} style={{ opacity: p, transform: `translateY(${(1 - p) * -24}px) scale(${0.96 + 0.04 * p})` }}>
              <Notificacion {...a} />
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

// Escuchar: el reproductor avanza y la conversación va apareciendo.
const Escucha: React.FC = () => {
  const ahora = useCurrentFrame();
  const fr = ahora - f('escuchar', 0.4);
  if (fr < -7 || ahora >= f('agenda')) return null;
  const p = interpolate(fr, [0, durDe('escuchar') - 12], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const revela = interpolate(p, [0, 1], [546, 776]);
  const xPomo = 166 + p * 100;
  return (
    <>
      <div style={{ position: 'absolute', left: 150, top: 500, width: 130, height: 22, background: '#f1f3f4' }} />
      <div style={{ position: 'absolute', left: 166, top: 509, width: 100, height: 4, borderRadius: 2, background: '#c0c2c3' }} />
      <div style={{ position: 'absolute', left: 166, top: 509, width: xPomo - 166, height: 4, borderRadius: 2, background: '#202124' }} />
      <div style={{ position: 'absolute', left: xPomo - 6, top: 505, width: 12, height: 12, borderRadius: 6, background: '#202124' }} />
      <div style={{ position: 'absolute', left: 18, top: revela, width: 354, height: Math.max(0, 776 - revela), background: '#fff' }} />
    </>
  );
};

const Pantalla: React.FC = () => {
  const fr = useCurrentFrame();
  const { fps } = useVideoConfig();
  const actual = [...PANTALLAS].reverse().findIndex((p) => p.desde <= fr);
  const idx = PANTALLAS.length - 1 - actual;
  const capas = PANTALLAS.map((p, i) => {
    if (i > idx || i < idx - 1) return null;
    const o = i === idx ? interpolate(fr, [p.desde, p.desde + 4], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }) : 1;
    return (
      <AbsoluteFill key={i} style={{ opacity: i === 0 ? 1 : o }}>
        {p.img === 'bloqueo' ? (
          <Bloqueo />
        ) : (
          <AbsoluteFill style={{ background: FONDO }}>
            <Img src={staticFile(p.img)} style={{ position: 'absolute', top: BARRA, left: 0, width: SW, height: 844 }} />
          </AbsoluteFill>
        )}
      </AbsoluteFill>
    );
  });
  const enBloqueo = PANTALLAS[idx].img === 'bloqueo';
  // Aviso de llamada urgente que baja desde arriba.
  const pb = spring({ frame: fr - f('urgente', 0.3), fps, config: { damping: 15, stiffness: 140 } });
  const anillo = interpolate(fr, [f('agenda', 1.2), f('agenda', 1.6)], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const anilloRojo = interpolate(fr, [f('urgente', 0.9), f('urgente', 1.3)], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  return (
    <AbsoluteFill style={{ background: FONDO, overflow: 'hidden', borderRadius: 54 }}>
      {capas}
      <BarraEstado claro={enBloqueo} />
      <div style={{ position: 'absolute', top: BARRA, left: 0, width: SW, height: 844 }}>
        <Escucha />
        {fr >= f('agenda') && fr < f('urgente') && (
          <div style={{ position: 'absolute', left: cajas.citaDeika.x - 3, top: cajas.citaDeika.y - 3, width: cajas.citaDeika.width + 6, height: cajas.citaDeika.height + 6, borderRadius: 20, border: `3px solid ${AZUL}`, opacity: anillo, boxShadow: `0 0 0 ${6 * anillo}px rgba(59,91,219,0.18)` }} />
        )}
        {fr >= f('urgente') && fr < f('recepcion') && (
          <div style={{ position: 'absolute', left: cajas.urgente.x - 3, top: cajas.urgente.y - 3, width: cajas.urgente.width + 6, height: cajas.urgente.height + 6, borderRadius: 20, border: `3px solid ${ROJO}`, opacity: anilloRojo, boxShadow: `0 0 0 ${6 * anilloRojo}px rgba(224,49,49,0.15)` }} />
        )}
        {TOQUES.filter((t) => !t.bloqueo).map((t, i) => <Toque key={i} x={t.x} y={t.y} desde={t.f} />)}
      </div>
      {TOQUES.filter((t) => t.bloqueo).map((t, i) => <Toque key={i} x={t.x} y={t.y} desde={t.f} />)}
      {fr >= f('urgente') && fr < f('recepcion') && (
        <div style={{ position: 'absolute', left: 8, width: SW - 16, top: 52 + (1 - pb) * -190 }}>
          <Notificacion claro titulo="Llamada urgente" cuerpo="Raúl Castro · Le pica la cabeza tras el tinte" />
        </div>
      )}
    </AbsoluteFill>
  );
};

const Movil: React.FC = () => {
  const fr = useCurrentFrame();
  const c = camara(fr);
  const tx = DIANA.x - c.s * c.x;
  const ty = DIANA.y - c.s * c.y;
  const sale = interpolate(fr, [f('cierre'), f('cierre', 0.45)], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.in(Easing.cubic) });
  const entra = interpolate(fr, [0, 14], [0, 1], { extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic) });
  if (sale >= 1) return null;
  return (
    <AbsoluteFill style={{ transformOrigin: '0 0', transform: `translate(${tx}px, ${ty + (1 - entra) * 160 + sale * 260}px) scale(${c.s})`, opacity: 1 - sale }}>
      <div style={{ position: 'absolute', left: MOVIL_X, top: MOVIL_Y, width: ANCHO_PANTALLA + BISEL * 2, height: SH * K + BISEL * 2, borderRadius: 54 * K + BISEL, background: '#0b0d18', boxShadow: '0 40px 90px rgba(18,22,43,0.35), inset 0 0 0 3px #2a2f45' }}>
        <div style={{ position: 'absolute', left: BISEL, top: BISEL, width: SW, height: SH, transformOrigin: '0 0', transform: `scale(${K})` }}>
          <Pantalla />
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ---------- Texto en pantalla ----------
const Texto: React.FC<{ texto: string; desde: number; dur: number; claro?: boolean }> = ({ texto, desde, dur, claro }) => {
  const fr = useCurrentFrame() - desde;
  if (fr < 0 || fr >= dur || !texto) return null;
  const sale = interpolate(fr, [dur - 6, dur], [1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  // Cada palabra lleva sus trozos en azul o no; así la puntuación va pegada a la palabra.
  let azul = false;
  const palabras = texto.split(' ').map((w) =>
    w.split(/(\*)/).flatMap((t) => {
      if (t === '*') { azul = !azul; return []; }
      return t ? [{ t, azul }] : [];
    }),
  );
  return (
    <div style={{ position: 'absolute', top: 128, left: 60, right: 60, textAlign: 'center', fontFamily: FUENTE, fontWeight: 800, fontSize: 70, lineHeight: 1.12, letterSpacing: -1.2, color: claro ? '#fff' : TINTA, opacity: sale }}>
      {palabras.map((trozos, i) => {
        const a = interpolate(fr, [i * 2, i * 2 + 8], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic) });
        return (
          <span key={i} style={{ display: 'inline-block', margin: '0 9px', opacity: a, transform: `translateY(${(1 - a) * 18}px)` }}>
            {trozos.map((p, j) => <span key={j} style={{ color: p.azul ? (claro ? AZUL_CLARO : AZUL) : undefined }}>{p.t}</span>)}
          </span>
        );
      })}
    </div>
  );
};

const Cierre: React.FC = () => {
  const fr = useCurrentFrame() - f('cierre', 0.25);
  const { fps } = useVideoConfig();
  if (fr < 0) return null;
  const a = spring({ frame: fr, fps, config: { damping: 14, stiffness: 120 } });
  const b = spring({ frame: fr - 8, fps, config: { damping: 14, stiffness: 120 } });
  const c = spring({ frame: fr - 16, fps, config: { damping: 14, stiffness: 120 } });
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', fontFamily: FUENTE, color: TINTA }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 26, opacity: a, transform: `scale(${0.85 + 0.15 * a})` }}>
        <Img src={staticFile('marca.png')} style={{ width: 150 }} />
        <span style={{ fontSize: 130, fontWeight: 800, color: AZUL, letterSpacing: 2 }}>DEIKA</span>
      </div>
      <div style={{ marginTop: 50, fontSize: 76, fontWeight: 800, textAlign: 'center', lineHeight: 1.1, letterSpacing: -1.2, opacity: b, transform: `translateY(${(1 - b) * 30}px)` }}>
        Tu teléfono,<br /><span style={{ color: AZUL }}>siempre atendido.</span>
      </div>
      <div style={{ marginTop: 64, background: AZUL, color: '#fff', fontSize: 50, fontWeight: 800, padding: '22px 56px', borderRadius: 999, opacity: c, transform: `scale(${0.9 + 0.1 * c})` }}>deika.eu</div>
    </AbsoluteFill>
  );
};

export const Anuncio: React.FC<{ voz?: string; musica?: string }> = ({ voz, musica }) => {
  const fr = useCurrentFrame();
  const oscuro = interpolate(fr, [f('panel') - 6, f('panel') + 6], [1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const verEjemplo = fr >= f('panel') && fr < f('cierre');
  return (
    <AbsoluteFill style={{ background: FONDO, fontFamily: FUENTE }}>
      <AbsoluteFill style={{ background: 'radial-gradient(circle at 20% 15%, rgba(59,91,219,0.10), transparent 45%), radial-gradient(circle at 85% 80%, rgba(59,91,219,0.08), transparent 40%)' }} />
      <AbsoluteFill style={{ background: `radial-gradient(circle at 50% 30%, #1d2550, ${TINTA} 65%)`, opacity: oscuro }} />
      <Movil />
      {/* El texto va encima de un degradado para que el móvil ampliado pase por debajo. */}
      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 520, background: `linear-gradient(${FONDO} 72%, rgba(246,247,251,0))`, opacity: 1 - oscuro }} />
      {ESCENAS.map((e) => <Texto key={e.id} texto={e.texto} desde={inicioDe(e.id)} dur={durDe(e.id)} claro={e.id === 'intro'} />)}
      {verEjemplo && (
        <div style={{ position: 'absolute', top: 52, left: 0, right: 0, display: 'flex', justifyContent: 'center' }}>
          <span style={{ background: 'rgba(18,22,43,0.66)', color: '#fff', fontSize: 24, fontWeight: 700, padding: '7px 18px', borderRadius: 999 }}>Panel con datos de ejemplo</span>
        </div>
      )}
      <Cierre />
      {voz && <Audio src={staticFile(voz)} />}
      {musica && <Audio src={staticFile(musica)} volume={0.22} />}
    </AbsoluteFill>
  );
};

export { totalFrames };
