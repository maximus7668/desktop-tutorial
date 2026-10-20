import React from 'react';
import { Composition } from 'remotion';
import { Anuncio, totalFrames } from './Anuncio';

export const RemotionRoot: React.FC = () => (
  <Composition id="AnuncioPanel" component={Anuncio} durationInFrames={totalFrames()} fps={30} width={1080} height={1920} defaultProps={{}} />
);
