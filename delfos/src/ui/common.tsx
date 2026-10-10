import { useState, type ReactNode } from 'react';
import { logoSrc } from '../data/source';
import type { League, Match, Team } from '../data/types';
import type { Confidence, Prediction } from '../model/predict';
import { railColors } from './colors';
import { outcomeCode, pctNum, statusText } from './format';
import { useIsDark } from '../state';
import { Icon } from './icons';

export function TeamLogo({ team, size = 28, flag = false }: { team: Pick<Team, 'logo' | 'abbr' | 'name' | 'color'>; size?: number; flag?: boolean }) {
  const [broken, setBroken] = useState(false);
  const src = logoSrc(team.logo, size > 40 ? 128 : 72);
  const style = { width: size, height: size };
  if (!src || broken) {
    return (
      <span className="logo-fallback" style={{ ...style, background: team.color || 'var(--sunken)', fontSize: size * 0.34 }} aria-hidden="true">
        {(team.abbr || team.name || '?').slice(0, 3)}
      </span>
    );
  }
  return (
    <span className={flag ? 'logo-plate flag' : 'logo-plate'} style={style}>
      <img src={src} alt="" width={size} height={size} loading="lazy" decoding="async" onError={() => setBroken(true)} />
    </span>
  );
}

export function LeagueLogo({ league, size = 22 }: { league: League; size?: number }) {
  const dark = useIsDark();
  const [broken, setBroken] = useState(false);
  const url = dark && league.logoDark ? league.logoDark : league.logo;
  const src = logoSrc(url, 72);
  if (!src || broken) {
    return <span className="league-fallback" style={{ width: size, height: size, fontSize: size * 0.36 }}>{league.short.slice(0, 3)}</span>;
  }
  return <img className="league-logo" src={src} alt="" width={size} height={size} onError={() => setBroken(true)} />;
}

export function ProbRail({ m, p, size = 'md', labels = true }: { m: Match; p: Prediction; size?: 'md' | 'lg'; labels?: boolean }) {
  const dark = useIsDark();
  const c = railColors(m.home.team, m.away.team, dark);
  const parts = p.threeWay
    ? [
        { k: 'home' as const, v: p.pHome, color: c.home },
        { k: 'draw' as const, v: p.pDraw, color: 'var(--draw)' },
        { k: 'away' as const, v: p.pAway, color: c.away },
      ]
    : [
        { k: 'home' as const, v: p.pHome, color: c.home },
        { k: 'away' as const, v: p.pAway, color: c.away },
      ];
  return (
    <div className={`rail rail-${size}`} role="img" aria-label={parts.map((x) => `${outcomeCode(x.k, p.threeWay)} ${pctNum(x.v)} %`).join(', ')}>
      <div className="rail-bar">
        {parts.map((x) => (
          <span key={x.k} className={`rail-seg ${p.pick === x.k ? 'is-pick' : ''}`} style={{ flexGrow: Math.max(x.v, 0.015), background: x.color }} />
        ))}
      </div>
      {labels && (
        <div className="rail-labels">
          {parts.map((x) => (
            <span key={x.k} className={`rail-label ${p.pick === x.k ? 'is-pick' : ''}`} style={{ flexGrow: Math.max(x.v, 0.2) }}>
              <i className="rail-key" style={{ background: x.color }} />
              <b>{outcomeCode(x.k, p.threeWay)}</b> {pctNum(x.v)}%
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

const CONF_TEXT: Record<Confidence, string> = { alta: 'Confianza alta', media: 'Confianza media', baja: 'Confianza baja' };

export function ConfidenceBadge({ c, short = false }: { c: Confidence; short?: boolean }) {
  return (
    <span className={`conf conf-${c}`} title={CONF_TEXT[c]}>
      <span className="conf-bars" aria-hidden="true">
        <i /><i /><i />
      </span>
      {short ? c.charAt(0).toUpperCase() + c.slice(1) : CONF_TEXT[c]}
    </span>
  );
}

export function FormChips({ form }: { form?: string }) {
  if (!form) return null;
  const map: Record<string, string> = { W: 'G', D: 'E', L: 'P' };
  return (
    <span className="form" aria-label={`Últimos partidos: ${form}`}>
      {form.toUpperCase().replace(/[^WDL]/g, '').split('').map((c, i) => (
        <i key={i} className={`form-${c}`}>{map[c]}</i>
      ))}
    </span>
  );
}

export function StatusPill({ m }: { m: Match }) {
  const s = statusText(m);
  return <span className={`status status-${s.kind}`}>{s.kind === 'live' && <i className="live-dot" />}{s.text}</span>;
}

export function HitMark({ ok }: { ok: boolean | undefined }) {
  if (ok === undefined) return null;
  return (
    <span className={`hit ${ok ? 'hit-ok' : 'hit-ko'}`} title={ok ? 'Pronóstico acertado' : 'Pronóstico fallado'}>
      <Icon name={ok ? 'check' : 'x'} size={14} />
      {ok ? 'Acierto' : 'Fallo'}
    </span>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <svg width="56" height="56" viewBox="0 0 48 48" aria-hidden="true">
        <circle cx="24" cy="24" r="16" fill="none" stroke="currentColor" strokeOpacity=".25" strokeWidth="3" />
        <path d="M24 16.5l7 12.6H17z" fill="none" stroke="currentColor" strokeOpacity=".45" strokeWidth="2.6" strokeLinejoin="round" />
      </svg>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
    </div>
  );
}
