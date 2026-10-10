// Genera .cache/snapshot.ts: partidos de los últimos 8 días y los 7 siguientes,
// clasificaciones (actual y anterior), tenis, F1 y todos los logos como data
// URI en WebP. Lo usa la versión Artifact, que no puede pedir datos en directo.
import { mkdir, writeFile } from 'node:fs/promises';
import sharp from 'sharp';
import {
  parseF1, parseRankings, parseScoreboard, parseStandings, parseTennis, rankingsUrl, resizedLogo,
  scoreboardSeasonYear, scoreboardUrl, seasonName, standingsUrl,
} from '../src/data/espn';
import { LEAGUES, LEAGUE_BY_ID } from '../src/data/leagues';
import type { LeagueTable, Match } from '../src/data/types';

const PAST = Number(process.env.PAST_DAYS ?? 8);
const FUTURE = Number(process.env.FUTURE_DAYS ?? 7);

async function get(url: string, tries = 3): Promise<any> {
  for (let i = 0; i < tries; i++) {
    try {
      const r = await fetch(url, { headers: { 'accept-encoding': 'gzip' } });
      if (r.ok) return await r.json();
      if (r.status === 400 || r.status === 404) return null;
    } catch {
      /* reintento */
    }
    await new Promise((res) => setTimeout(res, 800 * (i + 1)));
  }
  return null;
}

async function pool<T, R>(items: T[], n: number, fn: (x: T) => Promise<R>): Promise<R[]> {
  const out: R[] = new Array(items.length);
  let i = 0;
  await Promise.all(Array.from({ length: Math.min(n, items.length) }, async () => {
    while (i < items.length) {
      const k = i++;
      out[k] = await fn(items[k]);
    }
  }));
  return out;
}

const ymd = (d: Date) => d.toISOString().slice(0, 10).replace(/-/g, '');

async function main() {
  const now = new Date();
  const days: string[] = [];
  for (let k = -PAST; k <= FUTURE; k++) days.push(ymd(new Date(now.getTime() + k * 86400_000)));

  const teamLeagues = LEAGUES.filter((l) => l.sport !== 'tennis' && l.sport !== 'racing');
  const years = new Map<string, number>();
  const jobs = teamLeagues.flatMap((l) => days.map((d) => ({ l, d })));
  console.log(`Marcadores: ${jobs.length} peticiones…`);
  const parts = await pool(jobs, 10, async ({ l, d }) => {
    const json = await get(scoreboardUrl(l.slug, d));
    if (!json) return [] as Match[];
    const y = scoreboardSeasonYear(json);
    if (y) years.set(l.id, y);
    return parseScoreboard(l, json);
  });
  const byId = new Map<string, Match>();
  for (const m of parts.flat()) byId.set(m.id, m);

  const rankings: Record<string, ReturnType<typeof parseRankings>> = {};
  for (const id of ['atp', 'wta']) {
    const l = LEAGUE_BY_ID[id];
    const [sb, rk] = await Promise.all([get(scoreboardUrl(l.slug)), get(rankingsUrl(l.slug))]);
    const ranks = rk ? parseRankings(rk) : [];
    rankings[id] = ranks.slice(0, 100);
    const ms = sb ? parseTennis(l, sb, ranks) : [];
    for (const m of ms) byId.set(m.id, m);
  }
  const lo = new Date(now.getTime() - (PAST + 1) * 86400_000).toISOString();
  const hi = new Date(now.getTime() + (FUTURE + 1) * 86400_000).toISOString();
  const matches = [...byId.values()].filter((m) => m.start >= lo && m.start <= hi).sort((a, b) => a.start.localeCompare(b.start));
  console.log(`Partidos: ${matches.length}`);

  console.log('Clasificaciones…');
  const tables: Record<string, LeagueTable> = {};
  await pool(teamLeagues, 6, async (l) => {
    const y = years.get(l.id) ?? scoreboardSeasonYear(await get(scoreboardUrl(l.slug)));
    const [cur, prev] = await Promise.all([get(standingsUrl(l.slug)), y ? get(standingsUrl(l.slug, y - 1)) : null]);
    tables[l.id] = {
      leagueId: l.id,
      season: cur ? seasonName(cur) : '',
      current: cur ? parseStandings(cur) : [],
      previous: prev ? parseStandings(prev) : [],
    };
  });

  console.log('Fórmula 1…');
  const [f1sb, f1st] = await Promise.all([get(scoreboardUrl('racing/f1')), get(standingsUrl('racing/f1'))]);
  const f1 = f1sb && f1st ? parseF1(f1sb, f1st) : null;

  // Logos
  const urls = new Set<string>();
  for (const l of LEAGUES) {
    if (l.logo) urls.add(l.logo);
    if (l.logoDark) urls.add(l.logoDark);
  }
  for (const m of matches) {
    if (m.home.team.logo) urls.add(m.home.team.logo);
    if (m.away.team.logo) urls.add(m.away.team.logo);
  }
  for (const t of Object.values(tables)) for (const r of t.current) if (r.logo) urls.add(r.logo);
  for (const d of f1?.drivers || []) if (d.flag) urls.add(d.flag);
  console.log(`Logos: ${urls.size}…`);
  const logos: Record<string, string> = {};
  let bytes = 0;
  await pool([...urls], 12, async (url) => {
    for (let i = 0; i < 3; i++) {
      try {
        const r = await fetch(resizedLogo(url, 128));
        if (!r.ok) break;
        const buf = Buffer.from(await r.arrayBuffer());
        const webp = await sharp(buf).resize(72, 72, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } }).webp({ quality: 82, alphaQuality: 90 }).toBuffer();
        logos[url] = `data:image/webp;base64,${webp.toString('base64')}`;
        bytes += webp.length;
        return;
      } catch {
        await new Promise((res) => setTimeout(res, 500));
      }
    }
  });
  console.log(`Logos embebidos: ${Object.keys(logos).length} (${Math.round(bytes / 1024)} KB)`);

  const data = { generatedAt: now.toISOString(), matches, tables, f1, rankings, logos };
  await mkdir(new URL('../.cache/', import.meta.url), { recursive: true });
  const json = JSON.stringify(data);
  await writeFile(new URL('../.cache/snapshot.ts', import.meta.url), `export default JSON.parse(${JSON.stringify(json)});\n`);
  await writeFile(new URL('../.cache/snapshot.json', import.meta.url), json);
  console.log(`Instantánea: ${Math.round(json.length / 1024)} KB`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
