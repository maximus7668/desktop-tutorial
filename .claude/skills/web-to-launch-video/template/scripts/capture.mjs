// Captures a website for the launch video: screenshots (desktop + mobile),
// logo, brand colors, and copy. Writes src/brand.json and public/shots/*.png.
// Usage: node scripts/capture.mjs <url>
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

const url = process.argv[2];
if (!url) {
  console.error('Usage: node scripts/capture.mjs <url>');
  process.exit(1);
}

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const shotsDir = path.join(root, 'public', 'shots');
fs.rmSync(shotsDir, { recursive: true, force: true });
fs.mkdirSync(shotsDir, { recursive: true });

async function launch() {
  try {
    return await chromium.launch();
  } catch (err) {
    // Fall back to any preinstalled Playwright Chromium (e.g. cloud containers).
    const base = process.env.PLAYWRIGHT_BROWSERS_PATH || '/opt/pw-browsers';
    const dir = fs.existsSync(base) ? fs.readdirSync(base).find((d) => /^chromium-\d+$/.test(d)) : null;
    if (!dir) throw err;
    return chromium.launch({ executablePath: path.join(base, dir, 'chrome-linux', 'chrome') });
  }
}

async function dismissBanners(page) {
  const labels = /^(accept|accept all|aceptar|aceptar todo|aceptar todas|agree|i agree|got it|allow all|ok|entendido|accepter|akzeptieren)$/i;
  for (const btn of await page.locator('button, a[role="button"]').all()) {
    try {
      const text = (await btn.innerText({ timeout: 200 })).trim();
      if (labels.test(text) && (await btn.isVisible())) {
        await btn.click({ timeout: 1000 });
        await page.waitForTimeout(400);
        return;
      }
    } catch {}
  }
}

// Hosts whose requests failed (blocked network, CDN down). Reported at the end
// because a page without its CSS/fonts produces unusable screenshots.
const failedHosts = new Map();

async function preparePage(context) {
  const page = await context.newPage();
  page.on('requestfailed', (req) => {
    if (!['stylesheet', 'font', 'script', 'image', 'document'].includes(req.resourceType())) return;
    const host = new URL(req.url()).hostname;
    failedHosts.set(host, (failedHosts.get(host) || 0) + 1);
  });
  await page.goto(url, { waitUntil: 'networkidle', timeout: 45000 }).catch(() => {});
  await page.waitForTimeout(1500);
  await dismissBanners(page);
  // Trigger lazy-loaded content, then return to top.
  await page.evaluate(async () => {
    for (let y = 0; y < document.body.scrollHeight; y += 600) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 120));
    }
    window.scrollTo(0, 0);
  });
  await page.waitForTimeout(800);
  return page;
}

const browser = await launch();

// ---- Desktop pass: copy, colors, logo, screenshots ----
const desktop = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await preparePage(desktop);

const info = await page.evaluate(() => {
  const clean = (s) => {
    const t = (s || '').replace(/\s+/g, ' ').trim();
    // Animated headings often render their text twice ("FooFoo").
    const half = t.length / 2;
    return t.length % 2 === 0 && t.slice(0, half) === t.slice(half) ? t.slice(0, half) : t;
  };
  const meta = (sel) => clean(document.querySelector(sel)?.getAttribute('content'));
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none';
  };
  const isColor = (c) => c && c !== 'transparent' && !/rgba\(.*,\s*0\)$/.test(c);

  const h1 = [...document.querySelectorAll('h1')].find(visible);
  const headings = [...document.querySelectorAll('h2, h3')]
    .filter(visible)
    .map((h, i) => {
      h.setAttribute('data-lv-heading', String(i));
      let body = '';
      let n = h.nextElementSibling;
      for (let k = 0; n && k < 4 && !body; k++, n = n.nextElementSibling) {
        if (/^(P|DIV|SPAN)$/.test(n.tagName)) body = clean(n.innerText).slice(0, 160);
      }
      if (!body) body = clean(h.parentElement?.querySelector('p')?.innerText).slice(0, 160);
      return { id: i, title: clean(h.innerText), body, top: h.getBoundingClientRect().top + scrollY };
    })
    .filter((h) => h.title.length >= 3 && h.title.length <= 80);

  // Accent color: first visible filled button-like element.
  let accent = null;
  let primaryCta = '';
  for (const el of document.querySelectorAll('a, button')) {
    if (!visible(el)) continue;
    const bg = getComputedStyle(el).backgroundColor;
    if (isColor(bg) && !/rgb\((255, 255, 255|0, 0, 0)\)/.test(bg)) {
      accent = bg;
      primaryCta = clean(el.innerText);
      break;
    }
  }
  const linkColor = getComputedStyle(document.querySelector('a') || document.body).color;

  let pageBg = getComputedStyle(document.body).backgroundColor;
  if (!isColor(pageBg)) pageBg = getComputedStyle(document.documentElement).backgroundColor;
  if (!isColor(pageBg)) pageBg = 'rgb(255, 255, 255)';

  const ctas = [...document.querySelectorAll('a, button')]
    .filter((el) => visible(el) && el.getBoundingClientRect().top < innerHeight * 1.2)
    .map((el) => clean(el.innerText))
    .filter((t) => t.length >= 2 && t.length <= 28 && !/^skip to/i.test(t));

  const logoEl =
    document.querySelector('header [class*="logo" i] img, header [class*="logo" i] svg, header img[alt*="logo" i], header a[href="/"] img, header a[href="/"] svg') ||
    document.querySelector('[class*="logo" i] img, [class*="logo" i] svg, img[alt*="logo" i], a[href="/"] svg, a[href="/"] img');
  if (logoEl && visible(logoEl)) logoEl.setAttribute('data-lv-logo', '1');

  return {
    title: clean(document.title),
    siteName: meta('meta[property="og:site_name"]'),
    description: meta('meta[name="description"]') || meta('meta[property="og:description"]'),
    h1: clean(h1?.innerText),
    headings,
    ctas: [...new Set([primaryCta, ...ctas].filter(Boolean))].slice(0, 8),
    colors: {
      background: pageBg,
      text: getComputedStyle(h1 || document.body).color,
      accent: accent || linkColor,
    },
    font: getComputedStyle(h1 || document.body).fontFamily,
    pageHeight: document.body.scrollHeight,
  };
});

await page.screenshot({ path: path.join(shotsDir, 'hero.png') });

let hasLogo = false;
try {
  const logo = page.locator('[data-lv-logo]').first();
  if (await logo.count()) {
    await logo.screenshot({ path: path.join(shotsDir, 'logo.png'), omitBackground: true });
    hasLogo = true;
  }
} catch {}

// Section screenshots for up to 6 headings that are spread down the page.
const sections = [];
let lastTop = -Infinity;
for (const h of info.headings) {
  if (sections.length >= 6) break;
  if (h.top < 500 || h.top - lastTop < 500) continue;
  lastTop = h.top;
  await page.evaluate((top) => window.scrollTo(0, Math.max(0, top - 120)), h.top);
  await page.waitForTimeout(500);
  const file = `section-${sections.length + 1}.png`;
  await page.screenshot({ path: path.join(shotsDir, file) });
  sections.push({ ...h, shot: `shots/${file}` });
}

await page.evaluate(() => window.scrollTo(0, 0));
await page.waitForTimeout(300);
await page.screenshot({
  path: path.join(shotsDir, 'full.png'),
  fullPage: true,
  clip: { x: 0, y: 0, width: 1440, height: Math.min(info.pageHeight, 7000) },
});

// ---- Mobile pass ----
const mobile = await browser.newContext({
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 2,
  isMobile: true,
  hasTouch: true,
});
const mpage = await preparePage(mobile);
await mpage.screenshot({ path: path.join(shotsDir, 'mobile-hero.png') });
const mHeight = await mpage.evaluate(() => document.body.scrollHeight);
await mpage.screenshot({
  path: path.join(shotsDir, 'mobile-full.png'),
  fullPage: true,
  clip: { x: 0, y: 0, width: 390, height: Math.min(mHeight, 5000) },
});

await browser.close();

// ---- Draft brand.json (Claude rewrites the copy before rendering) ----
const host = new URL(url).hostname.replace(/^www\./, '');
const titleParts = info.title.split(/\s+[|\-–—:·\\]\s+/).map((t) => t.trim()).filter(Boolean);
const stem = host.split('.')[0].toLowerCase();
const name =
  info.siteName ||
  titleParts.find((t) => t.toLowerCase().replace(/[^a-z0-9]/g, '').includes(stem)) ||
  titleParts[0] ||
  host;
const features = sections.slice(0, 3).map((s) => ({ title: s.title, body: s.body, shot: s.shot }));
while (features.length < 3) features.push({ title: '', body: '', shot: 'shots/hero.png' });

const brand = {
  url,
  domain: host,
  name,
  logo: hasLogo ? 'shots/logo.png' : null,
  personality: 'premium',
  colors: info.colors,
  font: info.font,
  copy: {
    hook: info.h1 || info.title,
    tagline: info.description,
    features,
    cta: info.ctas[0] || 'Get started',
  },
  music: null,
  shots: { fullHeight: Math.min(info.pageHeight, 7000), mobileFullHeight: Math.min(mHeight, 5000) },
  _raw: { title: info.title, h1: info.h1, description: info.description, ctas: info.ctas, headings: info.headings.map((h) => h.title).slice(0, 15), sections },
};

fs.writeFileSync(path.join(root, 'src', 'brand.json'), JSON.stringify(brand, null, 2));
console.log(JSON.stringify(brand, null, 2));
if (failedHosts.size) {
  console.warn('\nWARNING: requests failed for these hosts (blocked network?). Check the screenshots for missing styles:');
  for (const [h, n] of failedHosts) console.warn(`  ${h} (${n})`);
}
console.log(`\nScreenshots in ${shotsDir}: ${fs.readdirSync(shotsDir).join(', ')}`);
