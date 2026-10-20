// Guion del anuncio del panel. Las duraciones (en segundos) se ajustan a la locución cuando esté grabada.
// En los textos, lo que va entre *asteriscos* sale en azul.

export const FPS = 30;

export type Escena = {
  id: 'intro' | 'panel' | 'llamadas' | 'escuchar' | 'agenda' | 'urgente' | 'recepcion' | 'cierre';
  dur: number;
  texto: string; // texto en pantalla
  voz: string; // lo que dice la locución
};

export const ESCENAS: Escena[] = [
  { id: 'intro', dur: 3.0, texto: '¿Quién te ha llamado mientras *trabajabas*?', voz: '¿Quién te ha llamado mientras trabajabas?' },
  { id: 'panel', dur: 3.4, texto: 'Con el panel de *DEIKA*, lo ves todo desde el móvil.', voz: 'Con el panel de DEIKA, lo ves todo desde el móvil.' },
  { id: 'llamadas', dur: 4.0, texto: 'Cada llamada: quién era, qué quería y *un resumen*.', voz: 'Cada llamada: quién era, qué quería, y un resumen.' },
  { id: 'escuchar', dur: 2.8, texto: 'Y si quieres, *la escuchas* entera.', voz: 'Y si quieres, la escuchas entera.' },
  { id: 'agenda', dur: 3.2, texto: 'Las citas que da van *directas a tu agenda*.', voz: 'Las citas que da van directas a tu agenda.' },
  { id: 'urgente', dur: 3.2, texto: 'Si algo es *urgente*, te avisa al momento.', voz: 'Si algo es urgente, te avisa al momento.' },
  { id: 'recepcion', dur: 4.0, texto: '¿Cambias el horario? Lo tocas aquí y *ella ya lo sabe*.', voz: '¿Cambias el horario? Lo tocas aquí, y ella ya lo sabe.' },
  { id: 'cierre', dur: 3.2, texto: '', voz: 'DEIKA. Tu teléfono, siempre atendido.' },
];

export const inicioDe = (id: Escena['id']) => {
  let t = 0;
  for (const e of ESCENAS) {
    if (e.id === id) return Math.round(t * FPS);
    t += e.dur;
  }
  throw new Error(id);
};
export const durDe = (id: Escena['id']) => Math.round(ESCENAS.find((e) => e.id === id)!.dur * FPS);
export const totalFrames = () => Math.round(ESCENAS.reduce((s, e) => s + e.dur, 0) * FPS);
