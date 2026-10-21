"""Imágenes del carrusel de Instagram a partir del borrador de texto.

El borrador de Instagram tiene este formato (ver agents/content.py):
    1/ Titular
    2/ Para quién: ...
    3/ Qué incluye:
    • ventaja
    ...
    Pie de foto: texto que va debajo de la publicación
Cada «N/» abre una diapositiva y las líneas siguientes se le suman. Se generan JPEG de 1080x1350
(formato vertical 4:5 que admite Instagram) sin depender de servicios externos."""
from __future__ import annotations

import io
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZE = (1080, 1350)
MARGIN = 96
BG, FG, ACCENT, MUTED = (250, 250, 247), (29, 29, 27), (197, 138, 26), (110, 110, 104)
_SLIDE = re.compile(r"^\s*(\d+)\s*/\s*(.*)$")
_CAPTION = re.compile(r"^\s*pie de foto\s*:\s*", re.I)
_FONTS = {
    False: ["C:/Windows/Fonts/segoeui.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
    True: ["C:/Windows/Fonts/segoeuib.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
}


def parse_carousel(body: str) -> tuple[list[str], str]:
    """Separa el borrador en diapositivas y pie de foto. Sin «N/», todo el texto es una diapositiva."""
    slides: list[list[str]] = []
    caption: list[str] = []
    in_caption = False
    for line in body.splitlines():
        if _CAPTION.match(line):
            in_caption = True
            caption.append(_CAPTION.sub("", line))
        elif in_caption:
            caption.append(line)
        elif m := _SLIDE.match(line):
            slides.append([m.group(2)])
        elif line.strip():
            if not slides:
                slides.append([])
            slides[-1].append(line.strip())
    texts = ["\n".join(s).strip() for s in slides if "".join(s).strip()][:10]
    cap = "\n".join(caption).strip()
    return texts, cap or body.strip()


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    for path in _FONTS[bold]:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        words, cur = para.split(), ""
        for w in words:
            test = f"{cur} {w}".strip()
            if draw.textlength(test, font=font) <= width or not cur:
                cur = test
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


def render_slide(text: str, n: int, total: int, footer: str = "") -> bytes:
    """Una diapositiva en JPEG. La primera va con letra más grande (portada)."""
    img = Image.new("RGB", SIZE, BG)
    draw = ImageDraw.Draw(img)
    width = SIZE[0] - 2 * MARGIN
    size = 76 if n == 1 else 58
    while True:
        font = _font(size, bold=(n == 1))
        lines = _wrap(draw, text, font, width)
        line_h = int(size * 1.3)
        if len(lines) * line_h <= SIZE[1] - 2 * MARGIN - 120 or size <= 30:
            break
        size -= 4
    draw.rectangle([MARGIN, MARGIN, MARGIN + 120, MARGIN + 10], fill=ACCENT)
    y = (SIZE[1] - len(lines) * line_h) // 2
    for line in lines:
        draw.text((MARGIN, y), line, font=font, fill=FG)
        y += line_h
    small = _font(32)
    draw.text((MARGIN, SIZE[1] - MARGIN - 32), f"{n}/{total}", font=small, fill=MUTED)
    if footer:
        fw = draw.textlength(footer, font=small)
        draw.text((SIZE[0] - MARGIN - fw, SIZE[1] - MARGIN - 32), footer, font=small, fill=MUTED)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()
