---
name: web-to-launch-video
description: >
  Turns any website URL into a motion-graphics launch/promo video (MP4, 16:9 and/or 9:16).
  Captures the site with a headless browser (screenshots, logo, brand colors, copy), writes
  punchy launch copy, and renders an animated Remotion video: hook, product reveal, three
  feature beats, full-page scroll, and CTA. Use when the user asks for a launch video, promo
  video, product video, teaser, reel/TikTok or video ad made from a website or landing page.
---

# Web → Launch Video

Pipeline: **capture → write copy → preview → render → QA → deliver**. The Remotion project in
`template/` already encodes the motion rules from the `motion-design` skill (personality tokens,
ease-out entrances, staggered word reveals under 0.5s, primary/secondary/ambient layers, shadow
follow-through). Consult `motion-design` when you change any animation.

## 0. Inputs

Get from the request, or use the defaults without asking:

| Input | Default |
|---|---|
| URL | required |
| Format | both: `16x9` (1920×1080) and `9x16` (1080×1920) |
| Personality | infer from the site (see step 3) |
| Copy language | the site's language |
| Music | none; if the user supplies an MP3, use it |

## 1. Set up a working copy

Never render inside the skill folder. Copy the template to a work dir (scratchpad if one exists,
else `./launch-video-<domain>`):

```bash
SKILL_DIR=<path to this skill>   # e.g. .claude/skills/web-to-launch-video
WORK=<work dir>
cp -r "$SKILL_DIR/template" "$WORK" && cd "$WORK" && npm install --no-audit --no-fund
```

## 2. Capture the site

```bash
node scripts/capture.mjs <url>
```

This writes `src/brand.json` (draft) and `public/shots/`: `hero.png`, `section-N.png`, `full.png`,
`mobile-hero.png`, `mobile-full.png`, `logo.png` (if found). Then **look at the screenshots**
with the Read tool before going further, at least `hero.png` and `mobile-hero.png`.

- **Blank or unstyled pages** (Times New Roman, blue links), or a `WARNING: requests failed`
  line, mean the network blocked the site or its CDNs. That's common in sandboxed cloud
  sessions with a restricted network policy. Tell the user which hosts failed and that the
  environment's network access must allow them, or that they should run this locally. Don't
  render a video from broken screenshots.
- A cookie banner or popup covering the hero: the script clicks common "Accept" buttons. If
  one survives, add its button text to the `labels` regex in `dismissBanners` and re-run.
- `brand.json._raw` lists every heading, CTA and section found. Use it to choose the copy.

## 3. Write the copy and art-direct `src/brand.json`

The draft copy is raw scraped text. Rewrite it like a launch-video copywriter:

| Field | Rule |
|---|---|
| `name` | Brand name only ("Nimbus", not "Home \| Nimbus") |
| `domain` | Display URL, e.g. `nimbus.app` |
| `copy.hook` | ≤ 6 words. The promise, not the category. |
| `copy.tagline` | ≤ 8 words. Shown in the reveal and the CTA. |
| `copy.features[]` | Exactly 3 (min 1). `title` ≤ 4 words, `body` ≤ 8 words or `""`. `shot`: the `shots/*.png` that best shows that feature (look at them). |
| `copy.cta` | The site's real primary button text (`_raw.ctas[0]` usually) |
| `personality` | `premium` (elegant, minimal, luxury, editorial) · `corporate` (B2B, SaaS, finance, health) · `playful` (consumer, social, kids, creative) · `energetic` (gaming, sports, events, music) |
| `colors` | Check against the screenshots. `accent` must be the brand's highlight color, not a default link blue (`rgb(0, 0, 238)`). Fix by hand if wrong. |
| `logo` | Set to `null` if `logo.png` is wrong or unreadable; the brand name is shown instead. |
| `music` | Filename inside `public/` (e.g. `"music.mp3"`) or `null` |

Leave `shots`, `url`, `font` and `_raw` as they are.

## 4. Preview stills (fast, about 10s each)

```bash
npx remotion still src/index.ts Launch16x9 out/hook.png --frame=60 $(ls -d /opt/pw-browsers/chromium_headless_shell-*/chrome-linux/headless_shell 2>/dev/null | head -1 | sed 's/^/--browser-executable=/')
```

Check the hook (frame 60), the reveal (~200), a feature (~330) and the CTA (last ~30 frames).
Fix copy that wraps badly or overflows before the full render.

## 5. Render

```bash
bash scripts/render.sh both out     # or: 16x9 | 9x16
```

It takes about 2 minutes per format in a cloud container. The output is
`out/<domain>-16x9.mp4` / `-9x16.mp4`, about 25 seconds long at 30 fps. The script reuses a
preinstalled headless Chromium when one exists; otherwise Remotion downloads its own.

## 6. QA before delivering

```bash
ffmpeg -v error -y -i out/<file>.mp4 -vf "select='not(mod(n\,90))',scale=480:-1,tile=3x3" -frames:v 1 out/sheet.png
```

Read the contact sheet. Check for unreadable text, broken screenshots, a wrong accent color, text
overflow, and empty-looking scenes. Fix and re-render if needed.

## 7. Deliver

Send the MP4(s) with SendUserFile (`display: "render"`). Summarize the hook, the three features,
the personality you picked, and how to change them (edit `brand.json` and re-render).

## Customizing

- **Timing**: `SCENES` in `src/scenes.tsx` (frames at 30 fps; transitions overlap 15 frames).
- **Motion feel**: `TOKENS` in `src/brand.ts` (easing curves, entrance frames, stagger, offsets).
- **Brand font**: put the `.woff2` in `public/`, call `loadFont` with `staticFile()` in
  `src/fonts.ts`, and change `fontFamily`. By default the video uses Inter, bundled locally.
- **Live editing**: `npx remotion studio` opens an editor with a timeline when running locally.

Remotion is free for individuals and companies with up to 3 employees. Larger companies need a
Remotion company license (remotion.dev/license). Mention this if the user is clearly a larger
company.
