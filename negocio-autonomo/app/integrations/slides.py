"""Imágenes del carrusel de Instagram a partir del borrador de texto.

El borrador de Instagram tiene este formato (ver agents/content.py):
    1/ Titular
    2/ Para quién: ...
    3/ Qué incluye:
    • ventaja
    ...
    Pie de foto: texto que va debajo de la publicación
Cada «N/» abre una diapositiva y las líneas siguientes se le suman. Se generan JPEG de 1080x1350
(formato vertical 4:5 que admite Instagram) sin depender de servicios externos.

Estilo de la marca (DEIKA): portada en azul noche, diapositivas intermedias claras y cierre en azul;
marca arriba a la izquierda, número arriba a la derecha, titular grande en Manrope con la última
palabra en color de acento y una línea de apoyo debajo. Fuente: Manrope (SIL OFL, fonts/OFL.txt)."""
from __future__ import annotations

import io
import os
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZE = (1080, 1350)
MARGIN = 96
_SLIDE = re.compile(r"^\s*(\d+)\s*/\s*(.*)$")
_CAPTION = re.compile(r"^\s*pie de foto\s*:\s*", re.IGNORECASE)
_MANROPE = Path(__file__).with_name("fonts") / "Manrope.ttf"
_FALLBACK = {
    "Regular": ["C:/Windows/Fonts/segoeui.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
    "Bold": ["C:/Windows/Fonts/segoeuib.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
}
# fondo, marca, titular, acento, apoyo, pie
THEMES = {
    "dark": ("#11162A", "#FFFFFF", "#F6F7FB", "#8FA3FA", "#D3D6E2", "#7C8095"),
    "light": ("#F6F7FB", "#3C5BDA", "#11162A", "#3C5BDA", "#2E3247", "#7C8095"),
    "blue": ("#3C5BDA", "#FFFFFF", "#FFFFFF", "#FFFFFF", "#E1E6FF", "#C9D2FF"),
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


def split_slide(text: str) -> tuple[str, str]:
    """Titular y línea de apoyo: la primera línea es el titular y el resto el apoyo; si la primera línea
    es «Algo: más texto», el titular es «Algo.» y el resto pasa al apoyo."""
    first, _, rest = text.partition("\n")
    head, sep, tail = first.partition(":")
    if sep and head.strip() and len(head) <= 40:
        first, rest = head, "\n".join(x for x in (tail.strip(), rest.strip()) if x)
    first = first.strip().rstrip(".:")
    if not rest and len(first) > 45:
        # Titular muy largo: se parte por « con » o por la última coma para que respire.
        for sep in (" con ", ", "):
            if sep in first:
                first, rest = first.split(sep, 1) if sep == " con " else first.rsplit(sep, 1)
                rest = (sep.strip(" ,") + " " + rest).strip() if sep == " con " else rest
                break
    rest = rest.strip()
    rest = rest[:1].upper() + rest[1:]
    return (first + "." if first and first[-1].isalnum() else first), rest


def _font(size: int, weight: str = "Regular") -> ImageFont.FreeTypeFont:
    if _MANROPE.exists():
        f = ImageFont.truetype(str(_MANROPE), size)
        f.set_variation_by_name(weight)
        return f
    for path in _FALLBACK["Bold" if weight in ("Bold", "ExtraBold", "SemiBold") else "Regular"]:
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


def _brand(footer: str) -> str:
    name = os.environ.get("BRAND_NAME", "").strip()
    return name or (footer.split(".")[0].upper() if footer else "")


def render_slide(text: str, n: int, total: int, footer: str = "") -> bytes:
    """Una diapositiva en JPEG: portada oscura, intermedias claras y la última en azul."""
    theme = "dark" if n == 1 else "blue" if n == total and total > 1 else "light"
    bg, brand_c, head_c, accent_c, sub_c, foot_c = THEMES[theme]
    img = Image.new("RGB", SIZE, bg)
    draw = ImageDraw.Draw(img)
    width = SIZE[0] - 2 * MARGIN
    head, sub = split_slide(text)

    small = _font(34, "Bold")
    draw.text((MARGIN, 116), _brand(footer), font=small, fill=brand_c)
    page = f"{n}/{total}"
    draw.text((SIZE[0] - MARGIN - draw.textlength(page, font=small), 116), page, font=small,
              fill=head_c if theme == "light" else brand_c)

    # Titular y apoyo: se reduce la letra hasta que el bloque cabe entre la cabecera y el pie.
    hsize, ssize = 112, 46
    while True:
        hf, sf = _font(hsize, "ExtraBold"), _font(ssize, "Regular")
        hlines = _wrap(draw, head, hf, width)
        slines = _wrap(draw, sub, sf, width) if sub else []
        hstep, sstep = int(hsize * 1.06), int(ssize * 1.38)
        block = len(hlines) * hstep + (40 + len(slines) * sstep if slines else 0)
        if block <= 820 or hsize <= 48:
            break
        hsize, ssize = hsize - 6, max(30, ssize - 2)
    y = max(260, (SIZE[1] - block) // 2 - 40)
    last_word_line = len(hlines) - 1
    for i, line in enumerate(hlines):
        x = MARGIN
        if i == last_word_line and " " in line.rstrip("."):
            # La última palabra del titular va en color de acento (sin el punto final).
            body, word = line.rstrip(".").rsplit(" ", 1)
            draw.text((x, y), body + " ", font=hf, fill=head_c)
            x += draw.textlength(body + " ", font=hf)
            draw.text((x, y), word, font=hf, fill=accent_c)
            x += draw.textlength(word, font=hf)
            if line.endswith("."):
                draw.text((x, y), ".", font=hf, fill=head_c)
        elif i == last_word_line:
            draw.text((x, y), line.rstrip("."), font=hf, fill=accent_c)
            if line.endswith("."):
                draw.text((x + draw.textlength(line.rstrip("."), font=hf), y), ".", font=hf, fill=head_c)
        else:
            draw.text((x, y), line, font=hf, fill=head_c)
        y += hstep
    if slines:
        y += 40
        for line in slines:
            draw.text((MARGIN, y), line, font=sf, fill=sub_c)
            y += sstep

    foot = _font(30, "SemiBold")
    bottom = footer if theme == "blue" else "Desliza →"
    if bottom:
        draw.text((MARGIN, SIZE[1] - MARGIN - 50), bottom, font=foot, fill=foot_c)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92)
    return buf.getvalue()
