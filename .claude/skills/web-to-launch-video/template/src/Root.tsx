import React from 'react';
import { Composition } from 'remotion';
import { LaunchVideo, totalFrames } from './LaunchVideo';

export const RemotionRoot: React.FC = () => (
  <>
    <Composition id="Launch16x9" component={LaunchVideo} durationInFrames={totalFrames()} fps={30} width={1920} height={1080} />
    <Composition id="Launch9x16" component={LaunchVideo} durationInFrames={totalFrames()} fps={30} width={1080} height={1920} />
  </>
);
