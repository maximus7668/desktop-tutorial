import { useCallback, useEffect, useMemo, useState } from 'react';
import { SPORTS } from './data/leagues';
import { dayKey, GENERATED_AT, MODE } from './data/source';
import { predict } from './model/predict';
import { readLocal, useDay, useSlip, useThemePref, writeLocal, type ThemePref } from './state';
import { dateTime } from './ui/format';
import { Forecasts, dayRange, useScored, type SportFilter } from './ui/Forecasts';
import { Icon, SportIcon, Wordmark } from './ui/icons';
import { MatchDetail } from './ui/MatchDetail';
import { Method } from './ui/Method';
import { Performance } from './ui/Performance';
import { Slip } from './ui/Slip';
import { Standings } from './ui/Standings';

type View = 'pronosticos' | 'combinada' | 'tablas' | 'rendimiento' | 'metodo';
const VIEWS: { id: View; name: string; icon: 'forecast' | 'slip' | 'table' | 'chart' | 'info' }[] = [
  { id: 'pronosticos', name: 'Pronósticos', icon: 'forecast' },
  { id: 'combinada', name: 'Combinada', icon: 'slip' },
  { id: 'tablas', name: 'Clasificaciones', icon: 'table' },
  { id: 'rendimiento', name: 'Rendimiento', icon: 'chart' },
  { id: 'metodo', name: 'Método', icon: 'info' },
];

function initialView(): View {
  try {
    const h = window.location.hash.replace('#', '') as View;
    if (VIEWS.some((v) => v.id === h)) return h;
  } catch {
    /* sin hash */
  }
  return 'pronosticos';
}

function initialDay(): string {
  const today = dayKey(new Date());
  const days = dayRange();
  if (days.includes(today)) return today;
  return days.find((d) => d > today) ?? days[days.length - 1] ?? today;
}

export function App() {
  const [view, setViewState] = useState<View>(initialView);
  const [day, setDay] = useState(initialDay);
  const [sport, setSportState] = useState<SportFilter>(() => readLocal<SportFilter>('sport', 'all'));
  const [nonce, setNonce] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const [theme, setTheme] = useThemePref();
  const data = useDay(day, nonce);
  const scored = useScored(data);
  const slip = useSlip();

  const setView = useCallback((v: View) => {
    setViewState(v);
    try {
      history.replaceState(null, '', `#${v}`);
    } catch {
      /* el visor puede bloquear el historial */
    }
    window.scrollTo({ top: 0 });
  }, []);
  const setSport = (s: SportFilter) => {
    setSportState(s);
    writeLocal('sport', s);
  };

  // En directo: refresco cada minuto mientras haya partidos por jugar o en juego hoy.
  useEffect(() => {
    if (MODE !== 'live' || day !== dayKey(new Date())) return;
    const t = setInterval(() => setNonce((n) => n + 1), 60_000);
    return () => clearInterval(t);
  }, [day]);

  const opened = useMemo(() => {
    if (!open) return null;
    const m = data.matches.find((x) => x.id === open);
    return m ? { m, p: predict(m, { tables: data.tables }) } : null;
  }, [open, data.matches, data.tables]);

  const live = scored.filter((s) => s.m.status === 'in').length;
  const counts = SPORTS.map((s) => ({ ...s, n: scored.filter((x) => x.m.sport === s.id).length }));
  const nextTheme: Record<ThemePref, ThemePref> = { system: 'dark', dark: 'light', light: 'system' };

  return (
    <div className="app">
      <header className="topbar">
        <button type="button" className="brand" onClick={() => setView('pronosticos')} aria-label="Delfos, ir a pronósticos">
          <Wordmark />
        </button>
        <div className="topbar-right">
          {MODE === 'snapshot' ? (
            <span className="data-chip" title="Esta versión lleva los datos incrustados">Datos del {GENERATED_AT ? dateTime(GENERATED_AT) : '—'}</span>
          ) : (
            <span className="data-chip is-live"><i className="live-dot" /> En directo{live ? ` · ${live} en juego` : ''}</span>
          )}
          {MODE === 'live' && (
            <button type="button" className="icon-btn" onClick={() => setTheme(nextTheme[theme])} aria-label={`Tema: ${theme === 'system' ? 'sistema' : theme === 'dark' ? 'oscuro' : 'claro'}`} title="Cambiar tema">
              <Icon name={theme === 'light' ? 'sun' : theme === 'dark' ? 'moon' : 'spark'} />
            </button>
          )}
          <button type="button" className={`icon-btn method-link ${view === 'metodo' ? 'is-on' : ''}`} onClick={() => setView('metodo')} aria-label="Cómo pronosticamos">
            <Icon name="info" />
          </button>
        </div>
      </header>

      <div className="layout">
        <aside className="rail-nav" aria-label="Secciones">
          <nav className="nav">
            {VIEWS.map((v) => (
              <button key={v.id} type="button" className={`nav-item ${view === v.id ? 'is-on' : ''}`} onClick={() => setView(v.id)} aria-current={view === v.id ? 'page' : undefined}>
                <Icon name={v.icon} />
                <span>{v.name}</span>
                {v.id === 'combinada' && slip.picks.length > 0 && <b className="badge">{slip.picks.length}</b>}
              </button>
            ))}
          </nav>
          <div className="nav-sports">
            <span className="eyebrow">Deportes del día</span>
            {counts.map((s) => (
              <button key={s.id} type="button" className={`nav-sport ${sport === s.id && view === 'pronosticos' ? 'is-on' : ''}`} onClick={() => { setSport(s.id); setView('pronosticos'); }}>
                <SportIcon sport={s.id} size={18} />
                <span>{s.name}</span>
                {s.id !== 'racing' && <small>{s.n}</small>}
              </button>
            ))}
          </div>
          <p className="nav-foot">+18 · Juega con responsabilidad. Datos: ESPN.</p>
        </aside>

        <main className="main" id="contenido">
          {view === 'pronosticos' && (
            <Forecasts day={day} setDay={setDay} sport={sport} setSport={setSport} data={data} onOpen={setOpen} onReload={() => setNonce((n) => n + 1)} />
          )}
          {view === 'combinada' && (
            <div className="view">
              <Slip scored={scored} />
            </div>
          )}
          {view === 'tablas' && <Standings />}
          {view === 'rendimiento' && <Performance />}
          {view === 'metodo' && <Method />}
        </main>

        <aside className="side" aria-label="Combinada">
          <Slip scored={scored} compact />
        </aside>
      </div>

      <nav className="tabbar" aria-label="Secciones">
        {VIEWS.filter((v) => v.id !== 'metodo').map((v) => (
          <button key={v.id} type="button" className={`tab ${view === v.id ? 'is-on' : ''}`} onClick={() => setView(v.id)} aria-current={view === v.id ? 'page' : undefined}>
            <span className="tab-icon">
              <Icon name={v.icon} size={22} />
              {v.id === 'combinada' && slip.picks.length > 0 && <b className="badge">{slip.picks.length}</b>}
            </span>
            <span>{v.id === 'tablas' ? 'Tablas' : v.name}</span>
          </button>
        ))}
      </nav>

      {opened && <MatchDetail m={opened.m} p={opened.p} tables={data.tables} onClose={() => setOpen(null)} />}
    </div>
  );
}
