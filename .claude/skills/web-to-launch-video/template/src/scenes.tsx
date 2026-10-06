import React from 'react';
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { brand, ink, motion, mutedInk, onAccent, Feature } from './brand';
import { Background, BrowserFrame, PhoneFrame, shadowFor, useEnter, useIsVertical, WordReveal } from './components';

// Scene lengths in frames (30fps). Transitions overlap 15 frames between scenes.
export const SCENES = { hook: 105, reveal: 150, feature: 96, scroll: 135, cta: 150 };
export const TRANSITION = 15;

const Logo: React.FC<{ height: number }> = ({ height }) =>
  brand.logo ? (
    <Img src={staticFile(brand.logo)} style={{ height, objectFit: 'contain' }} />
  ) : (
    <div style={{ fontSize: height * 0.8, fontWeight: 700, color: ink, letterSpacing: '-0.02em' }}>{brand.name}</div>
  );

// 1. Hook — brand mark, then the headline word by word.
export const Hook: React.FC = () => {
  const vertical = useIsVertical();
  const { width } = useVideoConfig();
  const logoIn = useEnter(0);
  const lineIn = useEnter(28, 30);
  return (
    <AbsoluteFill>
      <Background />
      <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center', padding: width * 0.08, gap: width * 0.03 }}>
        <div style={{ opacity: logoIn, transform: `translateY(${(1 - logoIn) * motion.rise}px)` }}>
          <Logo height={vertical ? 70 : 64} />
        </div>
        <WordReveal text={brand.copy.hook} delay={10} size={vertical ? 92 : 104} color={ink} />
        <div
          style={{
            width: width * 0.12 * lineIn,
            height: 6,
            borderRadius: 3,
            background: brand.colors.accent,
          }}
        />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// 2. Reveal — the product appears, then a slow push-in while the tagline lands.
export const Reveal: React.FC = () => {
  const frame = useCurrentFrame();
  const vertical = useIsVertical();
  const { width, height, durationInFrames } = useVideoConfig();
  const p = useEnter(4, motion.enterFrames + 8);
  const shadow = useEnter(10, motion.enterFrames + 8);
  const tag = useEnter(26);
  const push = interpolate(frame, [0, durationInFrames], [1, 1.06], { easing: motion.move });
  const scale = (motion.startScale + (1 - motion.startScale) * p) * push;

  const device = vertical ? (
    <PhoneFrame src="shots/mobile-hero.png" width={width * 0.62} />
  ) : (
    <BrowserFrame src="shots/hero.png" width={width * 0.7} height={width * 0.7 * (900 / 1440) + width * 0.021} />
  );

  return (
    <AbsoluteFill>
      <Background />
      <AbsoluteFill
        style={{
          justifyContent: 'center',
          alignItems: 'center',
          flexDirection: 'column',
          gap: height * 0.04,
          paddingTop: vertical ? height * 0.06 : height * 0.04,
        }}
      >
        <div
          style={{
            opacity: tag,
            transform: `translateY(${(1 - tag) * motion.rise * 0.6}px)`,
            color: mutedInk,
            fontSize: vertical ? 40 : 38,
            fontWeight: 500,
            maxWidth: width * 0.8,
            textAlign: 'center',
            lineHeight: 1.3,
          }}
        >
          {brand.copy.tagline}
        </div>
        <div
          style={{
            transform: `translateY(${(1 - p) * motion.rise * 3}px) scale(${scale})`,
            opacity: interpolate(p, [0, 0.3], [0, 1], { extrapolateRight: 'clamp' }),
            boxShadow: shadowFor(shadow),
            borderRadius: vertical ? width * 0.1 : 16,
          }}
        >
          {device}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// 3. Feature — numbered claim + the section of the site that backs it.
export const FeatureScene: React.FC<{ feature: Feature; index: number }> = ({ feature, index }) => {
  const frame = useCurrentFrame();
  const vertical = useIsVertical();
  const { width, height, durationInFrames } = useVideoConfig();
  const num = useEnter(0);
  const body = useEnter(14);
  const frameIn = useEnter(6, motion.enterFrames + 6);
  const shadow = useEnter(12, motion.enterFrames + 6);
  const drift = interpolate(frame, [0, durationInFrames], [0, -20], { easing: motion.move });

  const frameW = vertical ? width * 0.86 : width * 0.52;
  const frameH = frameW * (900 / 1440) + frameW * 0.03;

  const text = (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24, width: vertical ? width * 0.84 : width * 0.34 }}>
      <div
        style={{
          opacity: num,
          transform: `translateY(${(1 - num) * motion.rise}px)`,
          color: brand.colors.accent,
          fontSize: 34,
          fontWeight: 700,
          letterSpacing: '0.08em',
        }}
      >
        {String(index + 1).padStart(2, '0')}
      </div>
      <WordReveal text={feature.title} delay={4} size={vertical ? 74 : 68} color={ink} align={vertical ? 'center' : 'left'} />
      {feature.body ? (
        <div
          style={{
            opacity: body,
            transform: `translateY(${(1 - body) * motion.rise * 0.6}px)`,
            color: mutedInk,
            fontSize: vertical ? 38 : 32,
            lineHeight: 1.4,
            textAlign: vertical ? 'center' : 'left',
          }}
        >
          {feature.body}
        </div>
      ) : null}
    </div>
  );

  return (
    <AbsoluteFill>
      <Background drift={1.5} />
      <AbsoluteFill
        style={{
          flexDirection: vertical ? 'column' : 'row',
          justifyContent: 'center',
          alignItems: 'center',
          gap: vertical ? height * 0.05 : width * 0.05,
          alignContent: 'center',
          textAlign: vertical ? 'center' : 'left',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: vertical ? 'center' : 'flex-start' }}>{text}</div>
        <div
          style={{
            transform: `translateX(${vertical ? 0 : (1 - frameIn) * motion.rise * 4 + drift}px) translateY(${vertical ? (1 - frameIn) * motion.rise * 3 : 0}px) scale(${motion.startScale + (1 - motion.startScale) * frameIn})`,
            opacity: interpolate(frameIn, [0, 0.3], [0, 1], { extrapolateRight: 'clamp' }),
            boxShadow: shadowFor(shadow),
            borderRadius: 16,
          }}
        >
          <BrowserFrame src={feature.shot} width={frameW} height={frameH} />
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// 4. Scroll — the whole page glides past inside the device.
export const ScrollScene: React.FC = () => {
  const frame = useCurrentFrame();
  const vertical = useIsVertical();
  const { width, height, durationInFrames } = useVideoConfig();
  const p = useEnter(0);
  const label = useEnter(8);

  const viewW = vertical ? width * 0.62 : width * 0.72;
  const viewH = vertical ? viewW * (844 / 390) : viewW * (900 / 1440);
  const imgH = vertical
    ? brand.shots.mobileFullHeight * (viewW / 390)
    : brand.shots.fullHeight * (viewW / 1440);
  const travel = Math.max(0, imgH - viewH);
  const y = interpolate(frame, [12, durationInFrames - 10], [0, -travel], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: motion.move,
  });

  const page = (
    <Img
      src={staticFile(vertical ? 'shots/mobile-full.png' : 'shots/full.png')}
      style={{ width: '100%', display: 'block', transform: `translateY(${y}px)` }}
    />
  );

  return (
    <AbsoluteFill>
      <Background />
      <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center', flexDirection: 'column', gap: height * 0.035 }}>
        <div
          style={{
            opacity: label,
            transform: `translateY(${(1 - label) * motion.rise * 0.6}px)`,
            color: mutedInk,
            fontSize: vertical ? 40 : 34,
            fontWeight: 600,
            letterSpacing: '0.04em',
          }}
        >
          {brand.domain}
        </div>
        <div
          style={{
            transform: `scale(${motion.startScale + (1 - motion.startScale) * p})`,
            boxShadow: shadowFor(p),
            borderRadius: vertical ? viewW * 0.16 : 16,
          }}
        >
          {vertical ? (
            <PhoneFrame width={viewW}>{page}</PhoneFrame>
          ) : (
            <BrowserFrame width={viewW} height={viewH + viewW * 0.03}>
              {page}
            </BrowserFrame>
          )}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// 5. CTA — logo, promise, button with a gentle breathing pulse, URL.
export const Cta: React.FC = () => {
  const frame = useCurrentFrame();
  const vertical = useIsVertical();
  const { width } = useVideoConfig();
  const logoIn = useEnter(0);
  const btnIn = useEnter(22);
  const urlIn = useEnter(34);
  const pulse = frame > 40 ? 1 + Math.sin(((frame - 40) / 30) * Math.PI * 0.8) * 0.025 : 1;
  const btnScale = (motion.startScale + (1 - motion.startScale) * btnIn) * pulse;

  return (
    <AbsoluteFill>
      <Background drift={0.6} />
      <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center', gap: 48, padding: width * 0.08 }}>
        <div style={{ opacity: logoIn, transform: `scale(${motion.startScale + (1 - motion.startScale) * logoIn})` }}>
          <Logo height={vertical ? 96 : 84} />
        </div>
        <WordReveal text={brand.copy.tagline} delay={8} size={vertical ? 64 : 60} color={ink} weight={600} />
        <div
          style={{
            opacity: btnIn,
            transform: `translateY(${(1 - btnIn) * motion.rise}px) scale(${btnScale})`,
            background: brand.colors.accent,
            color: onAccent,
            fontSize: vertical ? 44 : 40,
            fontWeight: 700,
            padding: '26px 64px',
            borderRadius: 999,
            boxShadow: `0 20px 60px ${brand.colors.accent}`.replace(/rgb\(([^)]+)\)$/, 'rgba($1, 0.35)'),
          }}
        >
          {brand.copy.cta}
        </div>
        <div style={{ opacity: urlIn, color: mutedInk, fontSize: vertical ? 38 : 32, fontWeight: 500 }}>{brand.domain}</div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
