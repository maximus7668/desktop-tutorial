// Guion del anuncio del panel. Las duraciones (en segundos) van cuadradas con la locución (public/mezcla.wav):
// cada escena empieza en mitad de la pausa anterior a su frase.
// En los textos, lo que va entre *asteriscos* sale en azul.

export const FPS = 30;

export type Escena = {
  id: 'intro' | 'panel' | 'llamadas' | 'escuchar' | 'agenda' | 'urgente' | 'recepcion' | 'cierre';
  dur: number;
  texto: string; // texto en pantalla
  voz: string; // lo que dice la locución
};

export const ESCENAS: Escena[] = [
  { id: 'intro', dur: 2.565, texto: '¿Quién te ha llamado mientras *trabajabas*?', voz: '¿Quién te ha llamado mientras trabajabas?' },
  { id: 'panel', dur: 3.125, texto: 'Con el panel de *DEIKA*, lo ves todo desde el móvil.', voz: 'Con el panel de DEIKA, lo ves todo desde el móvil.' },
  { id: 'llamadas', dur: 3.425, texto: 'Cada llamada: quién era, qué quería y *un resumen*.', voz: 'Cada llamada: quién era, qué quería, y un resumen.' },
  { id: 'escuchar', dur: 2.335, texto: 'Y si quieres, *la escuchas* entera.', voz: 'Y si quieres, la escuchas entera.' },
  { id: 'agenda', dur: 2.75, texto: 'Las citas que da van *directas a tu agenda*.', voz: 'Las citas que da van directas a tu agenda.' },
  { id: 'urgente', dur: 2.635, texto: 'Si algo es *urgente*, te avisa al momento.', voz: 'Si algo es urgente, te avisa al momento.' },
  { id: 'recepcion', dur: 3.77, texto: '¿Cambias el horario? Lo tocas aquí y *ella ya lo sabe*.', voz: '¿Cambias el horario? Lo tocas aquí, y ella ya lo sabe.' },
  { id: 'cierre', dur: 4.395, texto: '', voz: 'DEIKA. Tu teléfono, siempre atendido.' },
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
