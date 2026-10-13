"""Convierte cada recurso en un clip de duración exacta: imágenes con movimiento de cámara
(Ken Burns suave, sin temblores) y vídeos recortados al formato del vídeo final."""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from .audio import ffmpeg
from .config import CACHE

MOVIMIENTOS = ("zoom_in", "izq", "zoom_out", "der")
LIENZO = 1.18  # el lienzo es un 18 % mayor que el encuadre: margen para moverse


def _abrir(ruta: Path) -> np.ndarray:
    img = ImageOps.exif_transpose(Image.open(ruta)).convert("RGB")
    return np.asarray(img)


def _cubrir(img: np.ndarray, w: int, h: int) -> np.ndarray:
    ih, iw = img.shape[:2]
    s = max(w / iw, h / ih)
    nw, nh = max(w, round(iw * s)), max(h, round(ih * s))
    interp = cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC
    r = cv2.resize(img, (nw, nh), interpolation=interp)
    x, y = (nw - w) // 2, (nh - h) // 2
    return r[y:y + h, x:x + w]


def _contener(img: np.ndarray, w: int, h: int) -> np.ndarray:
    ih, iw = img.shape[:2]
    s = min(w / iw, h / ih)
    interp = cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC
    return cv2.resize(img, (max(1, round(iw * s)), max(1, round(ih * s))), interpolation=interp)


def lienzo(img: np.ndarray, w: int, h: int) -> np.ndarray:
    """Encaja la imagen en un lienzo w×h. Si la forma no encaja (retrato en horizontal o al
    revés) se pone entera sobre una copia desenfocada de sí misma, en vez de recortarla."""
    ih, iw = img.shape[:2]
    rel = (iw / ih) / (w / h)
    if 0.78 <= rel <= 1.28:
        return _cubrir(img, w, h)
    fondo = _cubrir(img, w // 4, h // 4)
    fondo = cv2.GaussianBlur(fondo, (0, 0), 9)
    fondo = cv2.resize(fondo, (w, h), interpolation=cv2.INTER_LINEAR)
    fondo = (fondo.astype(np.float32) * 0.45).astype(np.uint8)
    frente = _contener(img, int(w * 0.96), int(h * 0.94))
    fh, fw = frente.shape[:2]
    x, y = (w - fw) // 2, (h - fh) // 2
    sombra = np.zeros((h, w), np.float32)
    sombra[y + 10:y + fh + 10, x + 6:x + fw + 6] = 1
    sombra = cv2.GaussianBlur(sombra, (0, 0), 18)[..., None]
    fondo = (fondo * (1 - 0.6 * sombra)).astype(np.uint8)
    fondo[y:y + fh, x:x + fw] = frente
    return fondo


def _trayectoria(mov: str, n: int, wc: int, hc: int, w: int, h: int, rng: np.random.Generator):
    """Ventana de cámara (x, y, ancho, alto) sobre el lienzo para cada fotograma."""
    t = np.linspace(0, 1, max(n, 1))
    zmax = LIENZO
    fx, fy = rng.uniform(0.42, 0.58), rng.uniform(0.40, 0.55)  # punto de interés aproximado
    if mov in ("zoom_in", "zoom_out", "fijo"):
        z = 1.0 + (zmax - 1.0) * (t if mov == "zoom_in" else 1 - t)
        if mov == "fijo":
            z = np.full_like(t, 1.0 + (zmax - 1.0) * 0.4)
        ww, wh = wc / z, hc / z
        x = (wc - ww) * fx
        y = (hc - wh) * fy
    else:
        z = np.full_like(t, zmax * 0.97)
        ww, wh = wc / z, hc / z
        rango_x, rango_y = wc - ww, hc - wh
        if mov in ("izq", "der"):
            p = t if mov == "der" else 1 - t
            x, y = rango_x * p, np.full_like(t, rango_y * fy)
        else:
            p = t if mov == "abajo" else 1 - t
            x, y = np.full_like(t, rango_x * fx), rango_y * p
    return x, y, ww, wh


def _codificador(salida: Path, w: int, h: int, fps: int) -> subprocess.Popen:
    return subprocess.Popen(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{w}x{h}", "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
         "-pix_fmt", "yuv420p", "-r", str(fps), str(salida)],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def _recortar(img: np.ndarray, encuadre: list[float] | None) -> np.ndarray:
    """Detalle de una imagen grande (grabados, mapas antiguos): x, y, ancho, alto entre 0 y 1."""
    if not encuadre:
        return img
    ih, iw = img.shape[:2]
    x, y, w, h = encuadre
    x0, y0 = int(x * iw), int(y * ih)
    x1, y1 = max(x0 + 8, int((x + w) * iw)), max(y0 + 8, int((y + h) * ih))
    return img[y0:min(ih, y1), x0:min(iw, x1)]


def _fundido(cuadro: np.ndarray, i: int, n: int, fps: int, entrada: float, salida_fundido: float) -> np.ndarray:
    tiempo, restante = i / fps, (n - 1 - i) / fps
    factor = 1.0
    if entrada and tiempo < entrada:
        factor = tiempo / entrada
    if salida_fundido and restante < salida_fundido:
        factor = min(factor, restante / salida_fundido)
    return cuadro if factor >= 1.0 else (cuadro.astype(np.float32) * factor).astype(np.uint8)


def clip_animado(ruta_spec: Path, salida: Path, n: int, tam: tuple[int, int], fps: int,
                 entrada: float = 0.0, salida_fundido: float = 0.0) -> Path:
    from .animados import Dibujante

    w, h = tam
    d = Dibujante(ruta_spec)
    proc = _codificador(salida, w, h, fps)
    try:
        for i in range(n):
            t = i / fps
            cuadro = d.cuadro(t)
            # tras dibujarse, un acercamiento muy lento para que no parezca una imagen fija
            z = 1.0 + 0.035 * max(0.0, t - 1.5) / max(1.0, n / fps - 1.5)
            if z > 1.0:
                m = cv2.getRotationMatrix2D((w / 2, h / 2), 0, z)
                cuadro = cv2.warpAffine(cuadro, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            proc.stdin.write(_fundido(cuadro, i, n, fps, entrada, salida_fundido).tobytes())
        proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError(proc.stderr.read().decode()[-800:])
    finally:
        if proc.poll() is None:
            proc.kill()
    return salida


def clip_imagen(ruta: Path, salida: Path, n: int, tam: tuple[int, int], fps: int, mov: str | None,
                indice: int = 0, entrada: float = 0.0, salida_fundido: float = 0.0,
                encuadre: list[float] | None = None) -> Path:
    w, h = tam
    semilla = int(hashlib.sha1(f"{ruta}{indice}".encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(semilla)
    mov = mov or MOVIMIENTOS[indice % len(MOVIMIENTOS)]
    wc, hc = int(w * LIENZO), int(h * LIENZO)
    base = lienzo(_recortar(_abrir(ruta), encuadre), wc, hc)
    xs, ys, ww, wh = _trayectoria(mov, n, wc, hc, w, h, rng)
    ww = np.broadcast_to(ww, (n,)) if np.ndim(ww) == 0 else ww
    wh = np.broadcast_to(wh, (n,)) if np.ndim(wh) == 0 else wh
    xs = np.broadcast_to(xs, (n,)) if np.ndim(xs) == 0 else xs
    ys = np.broadcast_to(ys, (n,)) if np.ndim(ys) == 0 else ys
    proc = _codificador(salida, w, h, fps)
    try:
        for i in range(n):
            sx, sy = ww[i] / w, wh[i] / h
            m = np.array([[sx, 0, xs[i]], [0, sy, ys[i]]], dtype=np.float64)
            cuadro = cv2.warpAffine(base, m, (w, h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                                    borderMode=cv2.BORDER_REFLECT)
            proc.stdin.write(_fundido(cuadro, i, n, fps, entrada, salida_fundido).tobytes())
        proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError(proc.stderr.read().decode()[-800:])
    finally:
        if proc.poll() is None:
            proc.kill()
    return salida


def clip_video(ruta: Path, salida: Path, n: int, tam: tuple[int, int], fps: int, duracion_fuente: float,
               indice: int = 0, entrada: float = 0.0, salida_fundido: float = 0.0) -> Path:
    w, h = tam
    necesaria = n / fps
    rng = np.random.default_rng(int(hashlib.sha1(f"{ruta}{indice}".encode()).hexdigest()[:8], 16))
    inicio = 0.0
    if duracion_fuente > necesaria + 1.0:
        margen = duracion_fuente - necesaria
        inicio = float(rng.uniform(min(0.6, margen), max(min(0.6, margen), margen * 0.7)))
    filtros = [f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos", f"crop={w}:{h}",
               f"fps={fps}", "setsar=1"]
    if entrada:
        filtros.append(f"fade=t=in:st=0:d={entrada}")
    if salida_fundido:
        filtros.append(f"fade=t=out:st={max(0.0, necesaria - salida_fundido):.3f}:d={salida_fundido}")
    bucle = ["-stream_loop", "-1"] if duracion_fuente and duracion_fuente < necesaria + inicio else []
    ffmpeg("-ss", f"{inicio:.3f}", *bucle, "-i", str(ruta), "-vf", ",".join(filtros) + ",format=yuv420p",
           "-frames:v", str(n), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-r", str(fps),
           str(salida))
    return salida


def duracion_video(ruta: Path) -> float:
    res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(ruta)],
                         capture_output=True, text=True)
    try:
        return float(res.stdout.strip())
    except ValueError:
        return 0.0


def clip(recurso, n: int, tam: tuple[int, int], fps: int, mov: str | None, indice: int,
         entrada: float = 0.0, salida_fundido: float = 0.0, encuadre: list[float] | None = None) -> Path:
    """Clip en caché: si nada cambia, no se vuelve a renderizar."""
    firma = (f"{recurso.ruta}|{n}|{tam}|{fps}|{mov}|{indice % 4 if not mov else ''}|{entrada}|{salida_fundido}|"
             f"{encuadre}|v3")
    h = hashlib.sha1(firma.encode()).hexdigest()[:20]
    destino = CACHE / "clips" / f"{h}.mp4"
    if destino.exists() and destino.stat().st_size > 0:
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.stem + ".tmp.mp4")
    if recurso.tipo == "video":
        dur = recurso.duracion or duracion_video(recurso.ruta)
        clip_video(recurso.ruta, tmp, n, tam, fps, dur, indice, entrada, salida_fundido)
    elif recurso.tipo == "animado":
        clip_animado(recurso.ruta, tmp, n, tam, fps, entrada, salida_fundido)
    else:
        clip_imagen(recurso.ruta, tmp, n, tam, fps, mov, indice, entrada, salida_fundido, encuadre)
    tmp.rename(destino)
    return destino
