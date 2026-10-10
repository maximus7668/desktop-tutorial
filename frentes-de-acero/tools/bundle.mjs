// Junta index.html, CSS y JS en un único archivo HTML (para jugar sin servidor o publicarlo).
// Uso: node bundle.mjs [salida.html] [--fragment]   (--fragment: sin <html>/<head>/<body>, para insertarlo en otra página)
import { readFileSync, writeFileSync } from 'fs';
const root = new URL('../', import.meta.url);
const read = p => readFileSync(new URL(p, root), 'utf8');
let html = read('index.html');
html = html.replace('<link rel="stylesheet" href="css/style.css">', () => '<style>\n' + read('css/style.css') + '</style>');
html = html.replace(/<script src="(js\/[\w.-]+)"><\/script>/g, (_, src) => '<script>\n' + read(src).replace(/<\/script/g, '<\\/script') + '\n</script>');
const out = process.argv[2] || new URL('frentes-de-acero.html', root);
if (process.argv.includes('--fragment')) {
  html = html.replace(/<!doctype html>\s*<html[^>]*>\s*<head>/i, '').replace(/<meta[^>]*>\s*/g, '')
    .replace(/<\/head>\s*<body>/i, '').replace(/<\/body>\s*<\/html>\s*$/i, '');
}
writeFileSync(out, html);
console.log('OK', out.toString(), Math.round(html.length / 1024) + ' KB');
