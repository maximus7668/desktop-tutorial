import { Easing } from 'remotion';
import raw from './brand.json';

export type Feature = { title: string; body: string; shot: string };

export type Brand = {
  url: string;
  domain: string;
  name: string;
  logo: string | null;
  personality: Personality;
  colors: { background: string; text: string; accent: string };
  font: string;
  copy: { hook: string; tagline: string; features: Feature[]; cta: string };
  music: string | null;
  shots: { fullHeight: number; mobileFullHeight: number };
};

export const brand = raw as unknown as Brand;

// Motion tokens per personality archetype (see the motion-design skill).
// Frames are at 30fps; video beats run longer than UI micro-interactions.
export type Personality = 'premium' | 'corporate' | 'playful' | 'energetic';

type Tokens = {
  enter: (t: number) => number; // entrances: decelerate
  move: (t: number) => number; // on-screen moves: ease-in-out
  enterFrames: number;
  stagger: number; // frames between staggered items
  rise: number; // entrance offset in px
  startScale: number;
  textMood: 'calm' | 'bold';
};

const TOKENS: Record<Personality, Tokens> = {
  premium: {
    enter: Easing.bezier(0.16, 1, 0.3, 1),
    move: Easing.bezier(0.4, 0, 0.2, 1),
    enterFrames: 24,
    stagger: 4,
    rise: 28,
    startScale: 0.97,
    textMood: 'calm',
  },
  corporate: {
    enter: Easing.bezier(0.2, 0, 0, 1),
    move: Easing.bezier(0.2, 0, 0, 1),
    enterFrames: 18,
    stagger: 3,
    rise: 30,
    startScale: 0.95,
    textMood: 'calm',
  },
  playful: {
    enter: Easing.bezier(0.175, 0.885, 0.32, 1.275),
    move: Easing.bezier(0.45, 0, 0.55, 1),
    enterFrames: 16,
    stagger: 3,
    rise: 50,
    startScale: 0.8,
    textMood: 'bold',
  },
  energetic: {
    enter: Easing.bezier(0.16, 1, 0.3, 1),
    move: Easing.bezier(0.87, 0, 0.13, 1),
    enterFrames: 10,
    stagger: 2,
    rise: 80,
    startScale: 0.7,
    textMood: 'bold',
  },
};

export const motion = TOKENS[brand.personality] ?? TOKENS.premium;

// Relative luminance of an rgb()/hex color, 0 (black) .. 1 (white).
export function luminance(color: string): number {
  let r = 255, g = 255, b = 255;
  const m = color.match(/rgba?\(([^)]+)\)/);
  if (m) {
    [r, g, b] = m[1].split(',').map((v) => parseFloat(v));
  } else if (color.startsWith('#')) {
    const hex = color.length === 4 ? color.replace(/#(.)(.)(.)/, '#$1$1$2$2$3$3') : color;
    r = parseInt(hex.slice(1, 3), 16);
    g = parseInt(hex.slice(3, 5), 16);
    b = parseInt(hex.slice(5, 7), 16);
  }
  const lin = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

export const isDark = luminance(brand.colors.background) < 0.35;
// Use the site's text color only if it actually contrasts with the background.
export const ink =
  Math.abs(luminance(brand.colors.text) - luminance(brand.colors.background)) > 0.4
    ? brand.colors.text
    : isDark ? '#fff' : '#111';
export const mutedInk = isDark ? 'rgba(255,255,255,0.68)' : 'rgba(0,0,0,0.58)';
// Text on the accent button: pick black or white by contrast.
export const onAccent = luminance(brand.colors.accent) > 0.45 ? '#111' : '#fff';
