import { loadFont } from '@remotion/fonts';
import inter400 from '@fontsource/inter/files/inter-latin-400-normal.woff2';
import inter500 from '@fontsource/inter/files/inter-latin-500-normal.woff2';
import inter600 from '@fontsource/inter/files/inter-latin-600-normal.woff2';
import inter700 from '@fontsource/inter/files/inter-latin-700-normal.woff2';

// Bundled locally so rendering never depends on Google Fonts being reachable.
export const fontFamily = 'Inter';

for (const [weight, url] of [
  ['400', inter400],
  ['500', inter500],
  ['600', inter600],
  ['700', inter700],
] as const) {
  loadFont({ family: fontFamily, url, weight });
}
