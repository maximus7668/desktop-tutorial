import type { SportId } from '../data/types';

interface P {
  size?: number;
  className?: string;
}

const base = (size: number) => ({
  width: size,
  height: size,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.7,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true,
});

export function SportIcon({ sport, size = 20, className }: P & { sport: SportId | 'all' }) {
  const s = base(size);
  switch (sport) {
    case 'soccer':
      return (
        <svg {...s} className={className}>
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7.6l3.2 2.3-1.2 3.8h-4l-1.2-3.8z" />
          <path d="M12 3v4.6M15.2 9.9l4.4-1.4M14 13.7l2.7 3.7M10 13.7l-2.7 3.7M8.8 9.9L4.4 8.5" />
        </svg>
      );
    case 'basketball':
      return (
        <svg {...s} className={className}>
          <circle cx="12" cy="12" r="9" />
          <path d="M3 12h18M12 3v18" />
          <path d="M5.6 5.6c3 2.8 3 10 0 12.8M18.4 5.6c-3 2.8-3 10 0 12.8" />
        </svg>
      );
    case 'football':
      return (
        <svg {...s} className={className}>
          <path d="M4.5 19.5c-1.6-5.2.6-11.5 6-14 3.2-1.4 6.4-1.3 9 0 1.6 5.2-.6 11.5-6 14-3.2 1.4-6.4 1.3-9 0z" />
          <path d="M9 15l6-6M10.5 10.5l1.4 1.4M12.1 8.9l1.4 1.4M8.9 12.1l1.4 1.4" />
        </svg>
      );
    case 'baseball':
      return (
        <svg {...s} className={className}>
          <circle cx="12" cy="12" r="9" />
          <path d="M6.2 5.2c2.4 3.9 2.4 9.7 0 13.6M17.8 5.2c-2.4 3.9-2.4 9.7 0 13.6" />
        </svg>
      );
    case 'hockey':
      return (
        <svg {...s} className={className}>
          <path d="M14 3l-5.2 13.4c-.3.8-1 1.3-1.9 1.3H3.5v2.8h4.6c1.9 0 3.5-1.1 4.2-2.9L17 4" />
          <ellipse cx="17.5" cy="19.2" rx="3" ry="1.3" />
        </svg>
      );
    case 'tennis':
      return (
        <svg {...s} className={className}>
          <circle cx="12" cy="12" r="9" />
          <path d="M5.6 5.6a9 9 0 0 1 0 12.8M18.4 5.6a9 9 0 0 0 0 12.8" />
        </svg>
      );
    case 'racing':
      return (
        <svg {...s} className={className}>
          <path d="M5 21V4" />
          <path d="M5 4h14v9H5" />
          <path d="M5 4h3.5v3H5zM12 4h3.5v3H12zM8.5 7H12v3H8.5zM15.5 7H19v3h-3.5zM5 10h3.5v3H5zM12 10h3.5v3H12z" fill="currentColor" stroke="none" />
        </svg>
      );
    default:
      return (
        <svg {...s} className={className}>
          <rect x="4" y="4" width="6.5" height="6.5" rx="1.6" />
          <rect x="13.5" y="4" width="6.5" height="6.5" rx="1.6" />
          <rect x="4" y="13.5" width="6.5" height="6.5" rx="1.6" />
          <rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.6" />
        </svg>
      );
  }
}

type IconName =
  | 'forecast' | 'slip' | 'table' | 'chart' | 'info' | 'close' | 'plus' | 'check' | 'x' | 'sun' | 'moon'
  | 'spark' | 'trash' | 'chevron' | 'pin' | 'tv' | 'bolt' | 'refresh' | 'wand';

export function Icon({ name, size = 20, className }: P & { name: IconName }) {
  const s = base(size);
  switch (name) {
    case 'forecast':
      return (<svg {...s} className={className}><path d="M12 4.5l7.5 13.5h-15z" /><circle cx="12" cy="13.5" r="1.6" fill="currentColor" stroke="none" /></svg>);
    case 'slip':
      return (<svg {...s} className={className}><path d="M6 3h12v18l-3-2-3 2-3-2-3 2z" /><path d="M9 8h6M9 12h6" /></svg>);
    case 'table':
      return (<svg {...s} className={className}><rect x="3.5" y="4.5" width="17" height="15" rx="2" /><path d="M3.5 9.5h17M3.5 14.5h17M9 4.5v15" /></svg>);
    case 'chart':
      return (<svg {...s} className={className}><path d="M4 20V4M4 20h16" /><path d="M7.5 15l3.5-4 3 2.5L19 7" /></svg>);
    case 'info':
      return (<svg {...s} className={className}><circle cx="12" cy="12" r="9" /><path d="M12 11v5.5M12 7.6v.1" /></svg>);
    case 'close':
      return (<svg {...s} className={className}><path d="M6 6l12 12M18 6L6 18" /></svg>);
    case 'plus':
      return (<svg {...s} className={className}><path d="M12 5v14M5 12h14" /></svg>);
    case 'check':
      return (<svg {...s} className={className}><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>);
    case 'x':
      return (<svg {...s} className={className}><path d="M7 7l10 10M17 7L7 17" /></svg>);
    case 'sun':
      return (<svg {...s} className={className}><circle cx="12" cy="12" r="4" /><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4" /></svg>);
    case 'moon':
      return (<svg {...s} className={className}><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" /></svg>);
    case 'spark':
      return (<svg {...s} className={className}><path d="M12 3l1.9 5.6L19.5 10l-5.6 1.9L12 17.5l-1.9-5.6L4.5 10l5.6-1.4z" /></svg>);
    case 'trash':
      return (<svg {...s} className={className}><path d="M4.5 7h15M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13" /></svg>);
    case 'chevron':
      return (<svg {...s} className={className}><path d="M9 6l6 6-6 6" /></svg>);
    case 'pin':
      return (<svg {...s} className={className}><path d="M12 21s-6.5-6.2-6.5-11a6.5 6.5 0 0 1 13 0c0 4.8-6.5 11-6.5 11z" /><circle cx="12" cy="10" r="2.3" /></svg>);
    case 'tv':
      return (<svg {...s} className={className}><rect x="3" y="5.5" width="18" height="12" rx="2" /><path d="M8 21h8" /></svg>);
    case 'bolt':
      return (<svg {...s} className={className}><path d="M13 3L5 13.5h6L10 21l8-10.5h-6z" /></svg>);
    case 'refresh':
      return (<svg {...s} className={className}><path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3M19.5 4v4.5H15" /></svg>);
    case 'wand':
      return (<svg {...s} className={className}><path d="M4 20L15 9M14 4.5v2M19.5 10h-2M17.9 6.1l-1.4 1.4M11 7l1 1M17 13l1 1" /></svg>);
  }
}

/** Marca de Delfos: la Δ de Δελφοί dentro de un anillo de probabilidad. */
export function LogoMark({ size = 36, className }: P) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" className={className} aria-hidden="true">
      <rect width="48" height="48" rx="13" fill="var(--brand-deep)" />
      <circle cx="24" cy="24" r="14.5" fill="none" stroke="#FFFFFF" strokeOpacity="0.22" strokeWidth="4" />
      <circle cx="24" cy="24" r="14.5" fill="none" stroke="var(--gold-fill)" strokeWidth="4" strokeLinecap="round" strokeDasharray="56.5 91.1" transform="rotate(-90 24 24)" />
      <path d="M24 16.2l7.6 13.6H16.4z" fill="none" stroke="#FFFFFF" strokeWidth="3.1" strokeLinejoin="round" />
    </svg>
  );
}

export function Wordmark() {
  return (
    <span className="wordmark">
      <LogoMark size={34} />
      <span className="wordmark-text">
        <span className="wordmark-name">Delfos</span>
        <span className="wordmark-tag">Pronósticos con datos</span>
      </span>
    </span>
  );
}
