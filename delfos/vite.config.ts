/// <reference types="vitest" />
import { defineConfig } from 'vite';
import { viteSingleFile } from 'vite-plugin-singlefile';
import { fileURLToPath } from 'node:url';
import { existsSync } from 'node:fs';

// Dos salidas:
//  - web (por defecto): SPA que lee los datos de ESPN en directo.
//  - artifact: un solo HTML con una instantánea de datos y logos embebidos,
//    React desde cdnjs (globales UMD), para publicarlo como Artifact.
export default defineConfig(({ mode }) => {
  const artifact = mode === 'artifact';
  const snapshotFile = fileURLToPath(new URL('./.cache/snapshot.ts', import.meta.url));
  if (artifact && !existsSync(snapshotFile)) {
    throw new Error('Falta .cache/snapshot.ts: ejecuta primero "npm run snapshot"');
  }
  return {
    base: './',
    esbuild: {
      jsx: 'transform',
      jsxFactory: 'React.createElement',
      jsxFragment: 'React.Fragment',
      jsxInject: `import React from 'react'`,
    },
    resolve: {
      alias: {
        '@snapshot': artifact ? snapshotFile : fileURLToPath(new URL('./src/data/snapshot.empty.ts', import.meta.url)),
      },
    },
    define: { __ARTIFACT__: JSON.stringify(artifact) },
    plugins: artifact ? [viteSingleFile({ removeViteModuleLoader: true })] : [],
    build: artifact
      ? {
          outDir: 'dist-artifact',
          modulePreload: false,
          rollupOptions: {
            external: ['react', 'react-dom', 'react-dom/client'],
            output: {
              format: 'iife',
              globals: { react: 'React', 'react-dom': 'ReactDOM', 'react-dom/client': 'ReactDOM' },
            },
          },
        }
      : { outDir: 'dist' },
    test: { environment: 'node' },
  };
});
