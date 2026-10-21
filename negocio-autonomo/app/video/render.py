"""Montaje del vídeo vertical (1080x1920, 30 fps).

Composición (inspirada en el formato «demo arriba, presentador abajo», con mascota propia):
- Panel superior: tarjeta con banda de título y una imagen del segmento (captura, logo…) o, sin imagen,
  el título en grande.
- Panel inferior: la mascota «Deiki» (robot con los colores de DEIKA) que mueve la boca con el volumen
  de la voz, parpadea y se balancea.
- Entre ambos: subtítulos de 2-3 palabras sincronizados con la voz.
- Pie: aviso «Voz y personaje generados con IA» (TikTok y el AI Act piden etiquetar el contenido sintético).

Guion JSON: {"titulo": "...", "segmentos": [{"texto": "frase hablada", "panel": "TÍTULO", "imagen": "ruta|null"}]}"""
from __future__ import annotations

import json
import math
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import voice

W, H, FPS = 1080, 1920, 30
NIGHT, LIGHT, BLUE, ACCENT = (17, 22, 42), (246, 247, 251), (60, 91, 218), (143, 163, 250)
PURPLE_BG = (32, 26, 64)
FONT = Path(__file__).resolve().parents[1] / "integrations" / "fonts" / "Manrope.ttf"
TOP = (40, 130, W - 40, 900)      # panel superior
BOTTOM = (40, 1010, W - 40, 1790)  # panel inferior
SUB_Y = 955                        # centro vertical de los subtítulos


def _font(size: int, weight: str = "Bold") -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONT), size)
    f.set_variation_by_name(weight)
    return f


@dataclass
class Segment:
    text: str
    panel: str
    image: str | None
    start: float = 0.0
    end: float = 0.0


def _wrap(draw, text, font, width):
    lines, cur = [], ""
    for w in text.split():
        t = f"{cur} {w}".strip()
        if draw.textlength(t, font=font) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    return lines + ([cur] if cur else [])


def _background() -> Image.Image:
    bg = Image.new("RGB", (W, H), NIGHT)
    grad = Image.linear_gradient("L").resize((W, H))
    purple = Image.new("RGB", (W, H), PURPLE_BG)
    return Image.composite(purple, bg, grad)


def _card(box, fill) -> tuple[Image.Image, Image.Image]:
    x0, y0, x1, y1 = box
    card = Image.new("RGB", (x1 - x0, y1 - y0), fill)
    mask = Image.new("L", card.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, card.width - 1, card.height - 1], 36, fill=255)
    return card, mask


def _top_panel(seg: Segment) -> tuple[Image.Image, Image.Image]:
    card, mask = _card(TOP, LIGHT)
    d = ImageDraw.Draw(card)
    for i, c in enumerate(((236, 106, 94), (245, 191, 79), (98, 197, 84))):  # «ventana»
        d.ellipse([28 + i * 34, 24, 48 + i * 34, 44], fill=c)
    inner = (24, 70, card.width - 24, card.height - 24)
    if seg.image and Path(seg.image).exists():
        img = Image.open(seg.image).convert("RGB")
        iw, ih = inner[2] - inner[0], inner[3] - inner[1]
        img.thumbnail((iw, ih))
        card.paste(img, (inner[0] + (iw - img.width) // 2, inner[1] + (ih - img.height) // 2))
    else:
        d.rounded_rectangle(inner, 24, fill=NIGHT)
        f = _font(88, "ExtraBold")
        lines = _wrap(d, seg.panel, f, inner[2] - inner[0] - 80)
        y = (inner[1] + inner[3]) // 2 - len(lines) * 50
        for i, line in enumerate(lines):
            col = ACCENT if i == len(lines) - 1 else LIGHT
            d.text(((card.width - d.textlength(line, font=f)) // 2, y), line, font=f, fill=col)
            y += 100
    # Banda de título arriba (estilo «etiqueta»)
    bf = _font(40, "ExtraBold")
    label = seg.panel.upper()[:34]
    tw = d.textlength(label, font=bf)
    bx0 = (card.width - tw) // 2 - 30
    d.rounded_rectangle([bx0, 62, bx0 + tw + 60, 128], 14, fill=BLUE)
    d.text((bx0 + 30, 70), label, font=bf, fill=LIGHT)
    return card, mask


def _mascot(frame: int, level: float, blink: bool) -> Image.Image:
    """Deiki: cabeza azul redondeada con pantalla oscura, ojos de acento y boca que se abre con la voz."""
    img = Image.new("RGBA", (620, 700), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bob = int(math.sin(frame / FPS * 2.2) * 8)
    # Cuerpo
    d.rounded_rectangle([110, 470 + bob, 510, 690 + bob], 90, fill=BLUE)
    d.rounded_rectangle([260, 500 + bob, 360, 540 + bob], 20, fill=ACCENT)
    # Antena
    d.line([310, 40 + bob, 310, 95 + bob], fill=LIGHT, width=10)
    d.ellipse([290, 18 + bob, 330, 58 + bob], fill=ACCENT)
    # Cabeza y pantalla
    d.rounded_rectangle([90, 90 + bob, 530, 470 + bob], 110, fill=BLUE)
    d.rounded_rectangle([140, 150 + bob, 480, 420 + bob], 80, fill=NIGHT)
    # Ojos
    for cx in (240, 380):
        if blink:
            d.rounded_rectangle([cx - 34, 248 + bob, cx + 34, 258 + bob], 5, fill=ACCENT)
        else:
            d.ellipse([cx - 32, 220 + bob, cx + 32, 290 + bob], fill=ACCENT)
            d.ellipse([cx - 10, 236 + bob, cx + 10, 256 + bob], fill=LIGHT)
    # Boca
    open_h = int(6 + 52 * level)
    d.rounded_rectangle([270, 330 + bob - open_h // 2, 350, 330 + bob + open_h // 2], min(30, open_h // 2 + 3),
                        fill=LIGHT if level > 0.08 else ACCENT)
    return img


def _chunks(words: list[voice.Word], max_words: int = 3, max_chars: int = 20):
    out, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or len(" ".join(x.text for x in [*cur, w])) > max_chars
                    or cur[-1].text[-1:] in ".,;:?!"):
            out.append(cur)
            cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return [(" ".join(x.text for x in c), c[0].start, c[-1].end) for c in out]


def make_video(script: dict, out: Path, voice_name: str | None = None) -> dict:
    segs = [Segment(s["texto"], s.get("panel") or script.get("titulo", ""), s.get("imagen")) for s in script["segmentos"]]
    speech = voice.speak([s.text for s in segs], voice_name)
    # Tiempos de cada segmento a partir de sus palabras
    i = 0
    for s in segs:
        n = len(s.text.split())
        ws = speech.words[i:i + n]
        s.start, s.end = (ws[0].start, ws[-1].end) if ws else (0, 0)
        i += n
    chunks = _chunks(speech.words)
    levels = voice.loudness(speech, FPS)
    total = int(speech.duration * FPS) + FPS // 2

    base = _background()
    bottom, bmask = _card(BOTTOM, (27, 34, 70))
    ImageDraw.Draw(bottom).rectangle([0, bottom.height - 150, bottom.width, bottom.height], fill=(22, 28, 58))
    base.paste(bottom, BOTTOM[:2], bmask)
    bd = ImageDraw.Draw(base)
    foot = _font(30, "SemiBold")
    note = "Voz y personaje generados con IA"
    bd.text(((W - bd.textlength(note, font=foot)) // 2, 1830), note, font=foot, fill=(150, 156, 190))
    panels = {id(s): _top_panel(s) for s in segs}
    subfont = _font(64, "ExtraBold")
    blink_frames = {f for k in range(0, total, 97) for f in (k + 40, k + 41, k + 42)}

    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "voz.wav"
        speech.save(wav)
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
               "-i", "-", "-i", str(wav), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(out)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        for f in range(total):
            t = f / FPS
            seg = next((s for s in segs if s.start <= t < s.end + voice.PAUSE),
                       segs[-1] if t >= segs[-1].start else segs[0])
            frame = base.copy()
            card, mask = panels[id(seg)]
            frame.paste(card, TOP[:2], mask)
            lvl = levels[f] if f < len(levels) else 0.0
            m = _mascot(f, lvl, f in blink_frames)
            frame.paste(m, ((W - m.width) // 2, BOTTOM[1] + 60), m)
            sub = next((c for c in chunks if c[1] <= t < c[2] + 0.05), None)
            if sub:
                d = ImageDraw.Draw(frame)
                tw = d.textlength(sub[0], font=subfont)
                d.rounded_rectangle([(W - tw) // 2 - 28, SUB_Y - 46, (W + tw) // 2 + 28, SUB_Y + 46], 18, fill=BLUE)
                d.text(((W - tw) // 2, SUB_Y - 40), sub[0], font=subfont, fill=LIGHT)
            proc.stdin.write(frame.tobytes())
        proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError("ffmpeg no pudo crear el vídeo")
    return {"archivo": str(out), "segundos": round(speech.duration, 1), "fotogramas": total}


def make_video_from_file(path: Path, out: Path, voice_name: str | None = None) -> dict:
    return make_video(json.loads(Path(path).read_text(encoding="utf-8")), out, voice_name)
