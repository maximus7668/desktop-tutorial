"""Rótulos generados con la estética del canal: titulares, cifras y citas."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .config import CACHE, fuente


SEGURO = 0.08  # fracción de cada lado que el movimiento de cámara puede dejar fuera


def rgb(hexa: str) -> tuple[int, int, int]:
    h = hexa.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _fuente(nombre: str, tam: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(fuente(nombre)), tam)


def envolver(texto: str, f: ImageFont.FreeTypeFont, ancho: int) -> list[str]:
    lineas, actual = [], ""
    for palabra in texto.split():
        prueba = f"{actual} {palabra}".strip()
        if f.getlength(prueba) <= ancho or not actual:
            actual = prueba
        else:
            lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas


def ajustar(texto: str, nombre: str, ancho: int, alto: int, maximo: int, minimo: int = 24,
            interlineado: float = 1.08) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    """Mayor tamaño de letra con el que el texto cabe en la caja."""
    tam = maximo
    while tam > minimo:
        f = _fuente(nombre, tam)
        lineas = envolver(texto, f, ancho)
        alto_linea = int(tam * interlineado)
        if len(lineas) * alto_linea <= alto and all(f.getlength(l) <= ancho for l in lineas):
            return f, lineas, alto_linea
        tam = int(tam * 0.92)
    f = _fuente(nombre, minimo)
    return f, envolver(texto, f, ancho), int(minimo * interlineado)


def fondo(ancho: int, alto: int, estilo: dict, semilla: int = 0) -> Image.Image:
    """Fondo oscuro con luz suave y grano, para que los rótulos no parezcan una diapositiva."""
    rng = np.random.default_rng(semilla)
    base = np.array(rgb(estilo["color_fondo"]), dtype=np.float32)
    acento = np.array(rgb(estilo["color_acento"]), dtype=np.float32)
    yy, xx = np.mgrid[0:alto, 0:ancho].astype(np.float32)
    cx, cy = ancho * rng.uniform(0.25, 0.75), alto * rng.uniform(0.2, 0.5)
    d = np.sqrt(((xx - cx) / ancho) ** 2 + ((yy - cy) / alto) ** 2)
    luz = np.clip(1 - d * 1.6, 0, 1) ** 2
    img = base[None, None, :] * (0.7 + 0.6 * luz[..., None]) + acento[None, None, :] * 0.10 * luz[..., None]
    vineta = np.clip(1 - (((xx / ancho - 0.5) ** 2 + (yy / alto - 0.5) ** 2) * 1.3), 0.35, 1)
    img *= vineta[..., None]
    img += rng.normal(0, 5, size=(alto, ancho, 1))
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")


def bloque(lineas: list[str], f: ImageFont.FreeTypeFont, color: tuple, interlineado: float = 1.1,
           alinear: str = "centro", sombra: int = 10, borde: int = 0, color_borde=(0, 0, 0),
           colores: list[tuple] | None = None) -> Image.Image:
    """Texto en una capa RGBA recortada a lo que ocupa de verdad (sin sorpresas de métricas)."""
    asc, desc = f.getmetrics()
    paso = int(f.size * interlineado)
    pad = sombra * 3 + borde + 4
    ancho = int(max(f.getlength(l) for l in lineas)) + 2 * pad
    alto = paso * (len(lineas) - 1) + asc + desc + 2 * pad
    texto = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    d = ImageDraw.Draw(texto)
    for i, l in enumerate(lineas):
        y = pad + asc + i * paso
        if alinear == "centro":
            x, ancla = ancho / 2, "ms"
        else:
            x, ancla = pad, "ls"
        d.text((x, y), l, font=f, fill=(colores[i] if colores else color), anchor=ancla,
               stroke_width=borde, stroke_fill=color_borde)
    if sombra:
        mascara = texto.getchannel("A").filter(ImageFilter.GaussianBlur(sombra))
        capa = Image.new("RGBA", texto.size, (0, 0, 0, 0))
        capa.paste((0, 0, 0, 255), (sombra // 3, sombra // 2), mascara.point(lambda v: int(v * 0.85)))
        texto = Image.alpha_composite(capa, texto)
    caja = texto.getchannel("A").getbbox() or (0, 0, 1, 1)
    return texto.crop(caja)


def _pegar(lienzo: Image.Image, capa: Image.Image, x: float, y: float) -> None:
    lienzo.paste(capa, (int(x), int(y)), capa)


def _apilar(lienzo: Image.Image, piezas: list[tuple[Image.Image, float]], centro_y: float, x: float | None = None) -> None:
    """Coloca capas una debajo de otra (con su separación) centradas en vertical."""
    total = sum(c.height for c, _ in piezas) + sum(g for _, g in piezas[:-1])
    y = centro_y - total / 2
    for c, gap in piezas:
        _pegar(lienzo, c, (lienzo.width - c.width) / 2 if x is None else x, y)
        y += c.height + gap


def _barra(ancho: int, alto: int, color: tuple) -> Image.Image:
    return Image.new("RGBA", (ancho, alto), (*color, 255))


def tarjeta(texto: str, sub: str | None, tam: tuple[int, int], estilo: dict, semilla: int = 0) -> Image.Image:
    W, H = tam
    img = fondo(W, H, estilo, semilla).convert("RGBA")
    vertical = H > W
    margen = int(W * (0.10 if vertical else 0.14)) + int(W * SEGURO)
    f, lineas, _ = ajustar(texto.upper(), estilo["fuente_titulos"], W - 2 * margen,
                           int(H * (0.30 if vertical else 0.46)), maximo=int(H * (0.10 if vertical else 0.16)),
                           interlineado=1.12)
    titulo = bloque(lineas, f, rgb(estilo["color_texto"]), 1.12)
    piezas = [(titulo, H * 0.03)]
    piezas.append((_barra(int(W * 0.08), max(4, int(H * 0.007)), rgb(estilo["color_acento"])), H * 0.03))
    if sub:
        fs = _fuente(estilo["fuente_texto"], max(24, int(f.size * 0.34)))
        piezas.append((bloque(envolver(sub, fs, W - 2 * margen), fs, rgb(estilo["color_acento"]), 1.25, sombra=6), 0))
    _apilar(img, piezas, H * (0.38 if vertical else 0.5))
    return img.convert("RGB")


def dato(cifra: str, sub: str | None, tam: tuple[int, int], estilo: dict, semilla: int = 0) -> Image.Image:
    W, H = tam
    img = fondo(W, H, estilo, semilla + 7).convert("RGBA")
    vertical = H > W
    margen = int(W * 0.08) + int(W * SEGURO)
    f, lineas, _ = ajustar(cifra.upper(), estilo["fuente_titulos"], W - 2 * margen,
                           int(H * (0.24 if vertical else 0.40)), maximo=int(H * (0.15 if vertical else 0.30)),
                           interlineado=1.02)
    piezas = [(bloque(lineas, f, rgb(estilo["color_acento"]), 1.02), H * 0.035)]
    if sub:
        fs = _fuente(estilo["fuente_texto"], max(24, int(min(f.size * (0.28 if vertical else 0.2), H * 0.05))))
        piezas.append((bloque(envolver(sub.upper(), fs, W - 2 * margen), fs, rgb(estilo["color_texto"]), 1.25, sombra=6), 0))
    _apilar(img, piezas, H * (0.38 if vertical else 0.5))
    return img.convert("RGB")


def cita(texto: str, autor: str | None, tam: tuple[int, int], estilo: dict, semilla: int = 0) -> Image.Image:
    W, H = tam
    img = fondo(W, H, estilo, semilla + 13).convert("RGBA")
    vertical = H > W
    margen = int(W * (0.10 if vertical else 0.16)) + int(W * SEGURO)
    f, lineas, _ = ajustar(f"«{texto}»", "Montserrat-SemiBold.ttf", W - 2 * margen,
                           int(H * (0.40 if vertical else 0.46)), maximo=int(H * (0.065 if vertical else 0.08)),
                           interlineado=1.3)
    comillas = bloque(["“"], _fuente(estilo["fuente_titulos"], int(f.size * 2.6)), rgb(estilo["color_acento"]), sombra=0)
    piezas = [(comillas, H * 0.02), (bloque(lineas, f, rgb(estilo["color_texto"]), 1.3, alinear="izq"), H * 0.03)]
    if autor:
        fa = _fuente(estilo["fuente_texto"], int(f.size * 0.7))
        piezas.append((bloque([f"— {autor}"], fa, rgb(estilo["color_acento"]), alinear="izq", sombra=6), 0))
    _apilar(img, piezas, H * (0.38 if vertical else 0.5), x=margen)
    return img.convert("RGB")


def generar(tipo: str, valor: str, extra: str | None, tam: tuple[int, int], estilo: dict) -> Path:
    """Crea (o reutiliza) el PNG de un rótulo y devuelve su ruta."""
    clave = hashlib.sha256(f"{tipo}|{valor}|{extra}|{tam}|{sorted(estilo.items())}".encode()).hexdigest()[:20]
    ruta = CACHE / "graficos" / f"{tipo}-{clave}.png"
    if ruta.exists():
        return ruta
    semilla = int(clave[:6], 16)
    grande = (int(tam[0] * 1.2), int(tam[1] * 1.2))  # margen para el movimiento de cámara
    hacer = {"tarjeta": tarjeta, "dato": dato, "cita": cita}[tipo]
    img = hacer(valor, extra, grande, estilo, semilla)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    img.save(ruta, optimize=True)
    return ruta
