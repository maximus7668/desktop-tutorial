// Convierte dist-artifact/index.html (Vite, un solo archivo) en el fragmento
// que espera el visor de Artifacts: <title>, fuentes, <style>, el contenedor,
// React desde cdnjs y el código de la app como script clásico.
import { mkdir, readFile, writeFile } from 'node:fs/promises';

const REACT = 'https://cdnjs.cloudflare.com/ajax/libs/react/18.3.1/umd/react.production.min.js';
const REACT_DOM = 'https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.3.1/umd/react-dom.production.min.js';
const FONTS = 'https://fonts.googleapis.com/css2?family=Big+Shoulders+Display:wght@700;800&family=Onest:wght@400;500;600;700&display=swap';

async function main() {
  const html = await readFile(new URL('../dist-artifact/index.html', import.meta.url), 'utf8');
  const styles = [...html.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map((m) => m[1]).join('\n');
  const scripts = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map((m) => m[1]).filter((s) => s.trim());
  if (!styles || scripts.length !== 1) throw new Error(`Salida inesperada: ${scripts.length} scripts`);
  const js = scripts[0].replace(/<\/script/gi, '<\\/script').replace(/<!--/g, '<\\!--');
  const out = [
    '<title>Delfos</title>',
    '<meta name="description" content="Pronósticos deportivos con datos para fútbol, NBA, NFL, MLB, NHL, tenis y Fórmula 1.">',
    '<link rel="preconnect" href="https://fonts.googleapis.com">',
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
    `<link rel="stylesheet" href="${FONTS}">`,
    `<style>${styles}</style>`,
    '<div id="root"></div>',
    `<script src="${REACT}"></script>`,
    `<script src="${REACT_DOM}"></script>`,
    `<script>${js}</script>`,
    '',
  ].join('\n');
  await mkdir(new URL('../dist-artifact/', import.meta.url), { recursive: true });
  await writeFile(new URL('../dist-artifact/delfos.html', import.meta.url), out);
  console.log(`dist-artifact/delfos.html: ${Math.round(out.length / 1024)} KB`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
