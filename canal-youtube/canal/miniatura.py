"""Tres miniaturas por vídeo (para «Probar y comparar» de YouTube Studio), 1280×720."""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from .graficos import _fuente, ajustar, bloque, rgb
from .visuales import Buscador

TAM = (1280, 720)


def _fondo(g, cfg) -> Image.Image:
    b = Buscador(cfg, (1920, 1080), g.id)
    r = b.conseguir(g.miniatura.visual)
    if r.tipo == "video":
        cuadro = r.ruta.with_suffix(".miniatura.jpg")
        if not cuadro.exists():
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "2", "-i", str(r.ruta), "-frames:v", "1",
                            str(cuadro)], check=True)
        img = Image.open(cuadro)
    else:
        img = Image.open(r.ruta)
    img = ImageOps.exif_transpose(img).convert("RGB")
    img = ImageOps.fit(img, TAM, Image.LANCZOS, centering=(0.5, 0.42))
    img = ImageEnhance.Contrast(img).enhance(1.18)
    img = ImageEnhance.Color(img).enhance(1.15)
    return img.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=2))


def _degradado(img: Image.Image, lado: str, fuerza: float = 0.82) -> Image.Image:
    w, h = img.size
    if lado in ("izq", "der"):
        x = np.linspace(1, 0, w) if lado == "izq" else np.linspace(0, 1, w)
        m = np.clip((x - 0.25) / 0.75, 0, 1) ** 1.3
        mascara = np.tile(m, (h, 1))
    else:
        y = np.linspace(0, 1, h)
        mascara = np.tile((np.clip((y - 0.35) / 0.65, 0, 1) ** 1.2)[:, None], (1, w))
    arr = np.asarray(img).astype(np.float32)
    arr *= (1 - fuerza * mascara)[..., None]
    return Image.fromarray(arr.clip(0, 255).astype(np.uint8))


def _titular(texto: str, cfg: dict, ancho: int, alto: int) -> Image.Image:
    est = cfg["estilo"]
    f, lineas, _ = ajustar(texto.upper(), est["fuente_titulos"], ancho, alto, maximo=int(alto * 0.62),
                           minimo=60, interlineado=1.02)
    blanco, acento = rgb(est["color_texto"]), rgb(est["color_acento"])
    colores = [acento if i == len(lineas) - 1 else blanco for i in range(len(lineas))] if len(lineas) > 1 else [acento]
    return bloque(lineas, f, blanco, 1.02, alinear="izq", sombra=12, borde=max(4, f.size // 16), colores=colores)


def _etiqueta(texto: str, cfg: dict) -> Image.Image:
    est = cfg["estilo"]
    f = _fuente(est["fuente_titulos"], 54)
    t = bloque([texto.upper()], f, rgb(est["color_fondo"]), sombra=0)
    caja = Image.new("RGBA", (t.width + 36, t.height + 26), (*rgb(est["color_acento"]), 255))
    caja.paste(t, (18, 13), t)
    return caja


def crear(g, cfg: dict, carpeta: Path) -> list[Path]:
    base = _fondo(g, cfg)
    texto = g.miniatura.texto
    rutas = []
    w, h = TAM
    variantes = [("izq", (60, None)), ("der", (None, None)), ("abajo", (60, None))]
    for n, (lado, _) in enumerate(variantes, 1):
        img = _degradado(base, lado).convert("RGBA")
        if lado == "abajo":
            t = _titular(texto, cfg, int(w * 0.9), int(h * 0.36))
            img.paste(t, ((w - t.width) // 2, h - t.height - 34), t)
        else:
            t = _titular(texto, cfg, int(w * 0.5), int(h * 0.74))
            x = 54 if lado == "izq" else w - t.width - 54
            img.paste(t, (x, (h - t.height) // 2 + 10), t)
        if g.miniatura.texto_secundario:
            e = _etiqueta(g.miniatura.texto_secundario, cfg)
            ex = 40 if lado != "izq" else w - e.width - 40
            img.paste(e, (ex, 36), e)
        ruta = carpeta / f"miniatura-{n}.jpg"
        img.convert("RGB").save(ruta, quality=90, optimize=True)
        rutas.append(ruta)
    # cómo se ven en el móvil (320 px de ancho): si no se lee aquí, no sirve
    vista = Image.new("RGB", (3 * 320 + 40, 180 + 20), (245, 245, 245))
    for i, r in enumerate(rutas):
        vista.paste(Image.open(r).resize((320, 180), Image.LANCZOS), (10 + i * 330, 10))
    vista.save(carpeta / "miniaturas-en-movil.jpg", quality=88)
    return rutas
