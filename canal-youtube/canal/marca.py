"""Imagen del canal: avatar (800×800) y banner (2560×1440, con la zona segura para móvil)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .config import SALIDA
from .graficos import _fuente, ajustar, bloque, envolver, fondo, rgb

LEMA = "Cómo se ganó y se perdió el dinero en el mundo hispano"


def _iniciales(nombre: str) -> str:
    palabras = [p for p in nombre.replace(".", " ").split() if p[:1].isalpha()]
    return "".join(p[0] for p in palabras[:2]).upper() or nombre[:1].upper()


def avatar(cfg: dict, ruta: Path) -> Path:
    est = cfg["estilo"]
    N = 800
    img = fondo(N, N, est, 3).convert("RGBA")
    oro = rgb(est["color_acento"])
    capa = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    # moneda: dos aros dorados, como un real de a ocho estilizado
    d.ellipse([90, 90, N - 90, N - 90], outline=(*oro, 255), width=22)
    d.ellipse([140, 140, N - 140, N - 140], outline=(*oro, 140), width=6)
    img = Image.alpha_composite(img, capa)
    t = _iniciales(cfg["canal"]["nombre"])
    f, lineas, _ = ajustar(t, est["fuente_titulos"], 420, 360, maximo=340)
    b = bloque(lineas, f, oro, sombra=14)
    img.paste(b, ((N - b.width) // 2, (N - b.height) // 2 + 6), b)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(ruta, quality=95)
    return ruta


def banner(cfg: dict, ruta: Path) -> Path:
    est = cfg["estilo"]
    W, H = 2560, 1440
    img = fondo(W, H, est, 11).convert("RGBA")
    oro = rgb(est["color_acento"])
    # textura: rejilla de mapa muy tenue
    capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    for x in range(0, W, 80):
        d.line([(x, 0), (x, H)], fill=(255, 255, 255, 10), width=1)
    for y in range(0, H, 80):
        d.line([(0, y), (W, y)], fill=(255, 255, 255, 10), width=1)
    img = Image.alpha_composite(img, capa)
    # zona segura (se ve en todos los dispositivos): 1546×423 en el centro
    sx, sy, sw, sh = (W - 1546) // 2, (H - 423) // 2, 1546, 423
    f, lineas, _ = ajustar(cfg["canal"]["nombre"].upper(), est["fuente_titulos"], sw, int(sh * 0.62), maximo=230)
    titulo = bloque(lineas, f, rgb(est["color_texto"]), sombra=16)
    fs = _fuente("Montserrat-SemiBold.ttf", 46)
    lema = bloque(envolver(LEMA, fs, sw), fs, oro, sombra=8)
    total = titulo.height + 24 + lema.height
    y = sy + (sh - total) // 2
    img.paste(titulo, ((W - titulo.width) // 2, y), titulo)
    d = ImageDraw.Draw(img)
    d.rectangle([W // 2 - 70, y + titulo.height + 4, W // 2 + 70, y + titulo.height + 12], fill=(*oro, 255))
    img.paste(lema, ((W - lema.width) // 2, y + titulo.height + 24), lema)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(ruta, quality=92)
    return ruta


def crear(cfg: dict) -> list[Path]:
    carpeta = SALIDA / "marca"
    return [avatar(cfg, carpeta / "avatar.jpg"), banner(cfg, carpeta / "banner.jpg")]
