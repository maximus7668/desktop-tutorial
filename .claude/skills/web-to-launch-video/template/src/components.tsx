import React from 'react';
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { brand, isDark, motion } from './brand';

// 0..1 entrance progress starting at `delay` frames, using the personality's easing.
export function useEnter(delay = 0, frames = motion.enterFrames) {
  const frame = useCurrentFrame();
  return interpolate(frame, [delay, delay + frames], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: motion.enter,
  });
}

export function useIsVertical() {
  const { width, height } = useVideoConfig();
  return height > width;
}

// Ambient layer: brand background with two slow-drifting accent glows.
export const Background: React.FC<{ drift?: number }> = ({ drift = 1 }) => {
  const frame = useCurrentFrame();
  const t = frame / 30;
  const a = Math.sin(t * 0.35) * 6 * drift;
  const b = Math.cos(t * 0.28) * 6 * drift;
  const glow = isDark ? 0.35 : 0.18;
  return (
    <AbsoluteFill style={{ backgroundColor: brand.colors.background, overflow: 'hidden' }}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(circle at ${30 + a}% ${25 + b}%, ${brand.colors.accent} 0%, transparent 45%)`,
          opacity: glow,
          filter: 'blur(40px)',
        }}
      />
      <AbsoluteFill
        style={{
          background: `radial-gradient(circle at ${75 - b}% ${80 - a}%, ${brand.colors.accent} 0%, transparent 40%)`,
          opacity: glow * 0.7,
          filter: 'blur(60px)',
        }}
      />
    </AbsoluteFill>
  );
};

// Headline revealed word by word from below a mask. Total stagger stays < ~0.5s.
export const WordReveal: React.FC<{
  text: string;
  delay?: number;
  size: number;
  color: string;
  weight?: number;
  align?: 'left' | 'center';
}> = ({ text, delay = 0, size, color, weight = 700, align = 'center' }) => {
  const frame = useCurrentFrame();
  const words = text.split(' ').filter(Boolean);
  const stagger = Math.min(motion.stagger, 15 / Math.max(words.length, 1));
  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        justifyContent: align === 'center' ? 'center' : 'flex-start',
        columnGap: size * 0.28,
        rowGap: size * 0.05,
        fontSize: size,
        fontWeight: weight,
        lineHeight: 1.08,
        letterSpacing: '-0.025em',
        color,
        textAlign: align,
      }}
    >
      {words.map((w, i) => {
        const p = interpolate(frame, [delay + i * stagger, delay + i * stagger + motion.enterFrames], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
          easing: motion.enter,
        });
        return (
          <span key={i} style={{ display: 'inline-block', overflow: 'hidden', paddingBottom: size * 0.08 }}>
            <span
              style={{
                display: 'inline-block',
                transform: `translateY(${(1 - p) * 105}%)`,
                opacity: interpolate(p, [0, 0.4], [0, 1], { extrapolateRight: 'clamp' }),
              }}
            >
              {w}
            </span>
          </span>
        );
      })}
    </div>
  );
};

// Desktop browser chrome around a screenshot. `children` overrides the image (for scrolling).
export const BrowserFrame: React.FC<{
  src?: string;
  width: number;
  height: number;
  children?: React.ReactNode;
}> = ({ src, width, height, children }) => {
  const bar = Math.round(width * 0.03);
  const dot = bar * 0.32;
  return (
    <div
      style={{
        width,
        height,
        borderRadius: bar * 0.45,
        overflow: 'hidden',
        background: isDark ? '#1c1c1f' : '#ffffff',
        border: `1px solid ${isDark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.08)'}`,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div
        style={{
          height: bar,
          flexShrink: 0,
          display: 'flex',
          alignItems: 'center',
          gap: dot * 0.7,
          padding: `0 ${bar * 0.5}px`,
          background: isDark ? '#2a2a2e' : '#f1f1f3',
        }}
      >
        {['#ff5f57', '#febc2e', '#28c840'].map((c) => (
          <div key={c} style={{ width: dot, height: dot, borderRadius: '50%', background: c }} />
        ))}
        <div
          style={{
            marginLeft: bar * 0.4,
            flex: 1,
            maxWidth: width * 0.45,
            height: bar * 0.58,
            borderRadius: bar,
            background: isDark ? '#1c1c1f' : '#ffffff',
            color: isDark ? '#aaa' : '#666',
            fontSize: bar * 0.3,
            display: 'flex',
            alignItems: 'center',
            paddingLeft: bar * 0.4,
          }}
        >
          {brand.domain}
        </div>
      </div>
      <div style={{ flex: 1, overflow: 'hidden', position: 'relative' }}>
        {children ?? <Img src={staticFile(src!)} style={{ width: '100%', display: 'block' }} />}
      </div>
    </div>
  );
};

// Phone bezel around a mobile screenshot.
export const PhoneFrame: React.FC<{ src?: string; width: number; children?: React.ReactNode }> = ({
  src,
  width,
  children,
}) => {
  const height = width * (844 / 390);
  const pad = width * 0.035;
  return (
    <div
      style={{
        width: width + pad * 2,
        height: height + pad * 2,
        padding: pad,
        borderRadius: width * 0.16,
        background: '#0b0b0c',
        boxSizing: 'border-box',
      }}
    >
      <div style={{ width, height, borderRadius: width * 0.13, overflow: 'hidden', position: 'relative', background: '#fff' }}>
        {children ?? <Img src={staticFile(src!)} style={{ width: '100%', display: 'block' }} />}
      </div>
    </div>
  );
};

// Soft drop shadow that lands a few frames after its element (follow-through).
export function shadowFor(progress: number) {
  const s = interpolate(progress, [0, 1], [0, 1], { extrapolateRight: 'clamp' });
  const alpha = isDark ? 0.55 : 0.22;
  return `0 ${40 * s}px ${90 * s}px rgba(0,0,0,${alpha * s})`;
}
