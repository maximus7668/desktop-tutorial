import React from 'react';
import { AbsoluteFill, Audio, Easing, interpolate, staticFile, useVideoConfig } from 'remotion';
import { linearTiming, TransitionSeries } from '@remotion/transitions';
import { fade } from '@remotion/transitions/fade';
import { slide } from '@remotion/transitions/slide';
import { fontFamily } from './fonts';
import { brand } from './brand';
import { Cta, FeatureScene, Hook, Reveal, SCENES, ScrollScene, TRANSITION } from './scenes';

const features = brand.copy.features.filter((f) => f.title.trim());

export function totalFrames() {
  const scenes = [SCENES.hook, SCENES.reveal, ...features.map(() => SCENES.feature), SCENES.scroll, SCENES.cta];
  return scenes.reduce((a, b) => a + b, 0) - TRANSITION * (scenes.length - 1);
}

const timing = linearTiming({ durationInFrames: TRANSITION, easing: Easing.bezier(0.4, 0, 0.2, 1) });

export const LaunchVideo: React.FC = () => {
  const { durationInFrames } = useVideoConfig();
  return (
    <AbsoluteFill style={{ fontFamily: `${fontFamily}, sans-serif`, backgroundColor: brand.colors.background }}>
      <TransitionSeries>
        <TransitionSeries.Sequence durationInFrames={SCENES.hook}>
          <Hook />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={fade()} timing={timing} />
        <TransitionSeries.Sequence durationInFrames={SCENES.reveal}>
          <Reveal />
        </TransitionSeries.Sequence>
        {features.flatMap((f, i) => [
          <TransitionSeries.Transition key={`t${i}`} presentation={slide({ direction: 'from-right' })} timing={timing} />,
          <TransitionSeries.Sequence key={`s${i}`} durationInFrames={SCENES.feature}>
            <FeatureScene feature={f} index={i} />
          </TransitionSeries.Sequence>,
        ])}
        <TransitionSeries.Transition presentation={fade()} timing={timing} />
        <TransitionSeries.Sequence durationInFrames={SCENES.scroll}>
          <ScrollScene />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={fade()} timing={timing} />
        <TransitionSeries.Sequence durationInFrames={SCENES.cta}>
          <Cta />
        </TransitionSeries.Sequence>
      </TransitionSeries>
      {brand.music ? (
        <Audio
          src={staticFile(brand.music)}
          volume={(f) =>
            interpolate(f, [0, 15, durationInFrames - 45, durationInFrames], [0, 0.8, 0.8, 0], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
            })
          }
        />
      ) : null}
    </AbsoluteFill>
  );
};
