"""Planos animados generados: gráficos de datos (barras, línea, cronología) y mapas con rutas.

Se dibujan fotograma a fotograma con OpenCV (líneas y rellenos suavizados) y el texto con PIL.
Los mapas usan Natural Earth (dominio público), que se descarga la primera vez.
"""
from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import requests
from PIL import Image

from .config import CACHE
from .graficos import _fuente, bloque, envolver, fondo, rgb

NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/{}.geojson"
ANIM = 1.4  # segundos que tarda en dibujarse un gráfico
VERSION = 2  # súbela al cambiar el dibujo: invalida los planos animados en caché


# ------------------------------------------------------------------ utilidades

def _suave(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def _np(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("RGB")).copy()


def _capa(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("RGBA")).astype(np.float32)


def pegar(dst: np.ndarray, capa: np.ndarray, x: int, y: int, alfa: float = 1.0) -> None:
    """Mezcla una capa RGBA (float32) sobre dst (uint8 RGB) en (x, y), recortando bordes."""
    if alfa <= 0:
        return
    h, w = capa.shape[:2]
    H, W = dst.shape[:2]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x0 >= x1 or y0 >= y1:
        return
    c = capa[y0 - y:y1 - y, x0 - x:x1 - x]
    a = (c[..., 3:4] / 255.0) * alfa
    zona = dst[y0:y1, x0:x1].astype(np.float32)
    dst[y0:y1, x0:x1] = (zona * (1 - a) + c[..., :3] * a).astype(np.uint8)


def _texto(t: str, nombre: str, tam: int, color, sombra: int = 6, borde: int = 0) -> np.ndarray:
    return _capa(bloque([t], _fuente(nombre, tam), color, sombra=sombra, borde=borde, alinear="izq"))


def _num(v: float, unidad: str = "") -> str:
    if abs(v) >= 100 or float(v).is_integer():
        s = f"{v:,.0f}".replace(",", ".")
    else:
        s = f"{v:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
    unidad = (unidad or "").strip()
    if not unidad:
        return s
    return s + unidad if unidad.startswith("%") else f"{s} {unidad}"


def _cabecera(img: np.ndarray, titulo: str, sub: str | None, estilo: dict) -> int:
    """Título arriba a la izquierda; devuelve la y donde empieza el contenido."""
    H, W = img.shape[:2]
    vertical = H > W
    x = int(W * (0.08 if vertical else 0.07))
    y = int(H * (0.10 if vertical else 0.08))
    if titulo:
        tam = int(W * (0.075 if vertical else 0.042))
        lineas = envolver(titulo.upper(), _fuente(estilo["fuente_titulos"], tam), int(W * 0.84))
        capa = _capa(bloque(lineas, _fuente(estilo["fuente_titulos"], tam), rgb(estilo["color_texto"]), 1.08, alinear="izq"))
        pegar(img, capa, x, y)
        y += capa.shape[0] + int(H * 0.012)
    if sub:
        capa = _texto(sub, "Montserrat-SemiBold.ttf", int(W * (0.034 if vertical else 0.019)), rgb(estilo["color_acento"]))
        pegar(img, capa, x, y)
        y += capa.shape[0]
    return y + int(H * 0.04)


def _nota(img: np.ndarray, nota: str | None, estilo: dict) -> None:
    if not nota:
        return
    H, W = img.shape[:2]
    capa = _texto(nota, "Montserrat-SemiBold.ttf", int(min(W, H) * 0.022), (150, 150, 155), sombra=3)
    pegar(img, capa, int(W * 0.07), int(H * 0.93) - capa.shape[0])


# ------------------------------------------------------------------ gráficos

def _barras(base: np.ndarray, spec: dict, estilo: dict, t: float, y0: int) -> np.ndarray:
    img = base.copy()
    H, W = img.shape[:2]
    datos = spec["datos"]
    vertical = H > W
    acento, gris = rgb(estilo["color_acento"]), (110, 114, 124)
    destacar = set(spec.get("destacar") or [])
    x0, x1 = int(W * 0.09), int(W * 0.91)
    suelo = int(H * (0.60 if vertical else 0.80))
    techo = y0 + int(H * 0.08)
    n = len(datos)
    hueco = (x1 - x0) / n
    ancho = hueco * 0.62
    maximo = max(v for _, v in datos) or 1
    k = 1.4 if vertical else 1.0
    f_val = int(min(W, H) * (0.05 if n <= 6 else 0.036) * k)
    f_eti = int(min(W, H) * (0.035 if n <= 6 else 0.026) * k)
    cv2.line(img, (x0, suelo), (x1, suelo), (90, 94, 102), 2, cv2.LINE_AA)
    for i, (etiqueta, v) in enumerate(datos):
        p = _suave((t - i * 0.08) / ANIM)
        alto = (suelo - techo) * (v / maximo) * p
        cx = x0 + hueco * (i + 0.5)
        color = acento if (not destacar or etiqueta in destacar) else gris
        if alto > 1:
            cv2.rectangle(img, (int(cx - ancho / 2), int(suelo - alto)), (int(cx + ancho / 2), suelo), color, -1, cv2.LINE_AA)
        if p > 0.85:
            val = _texto(_num(v, spec.get("unidad") or ""), "Montserrat-ExtraBold.ttf", f_val, rgb(estilo["color_texto"]))
            pegar(img, val, int(cx - val.shape[1] / 2), int(suelo - alto - val.shape[0] - 6), (p - 0.85) / 0.15)
        eti = _texto(str(etiqueta), "Montserrat-SemiBold.ttf", f_eti, (200, 200, 205), sombra=3)
        pegar(img, eti, int(cx - eti.shape[1] / 2), suelo + 12, min(1.0, t / 0.4))
    return img


def _linea(base: np.ndarray, spec: dict, estilo: dict, t: float, y0: int) -> np.ndarray:
    img = base.copy()
    H, W = img.shape[:2]
    datos = spec["datos"]
    vertical = H > W
    acento = rgb(estilo["color_acento"])
    x0, x1 = int(W * 0.10), int(W * 0.90)
    suelo = int(H * (0.60 if vertical else 0.80))
    techo = y0 + int(H * 0.08)
    vals = [v for _, v in datos]
    lo, hi = min(0.0, min(vals)), max(vals) or 1
    pts = np.array([(x0 + (x1 - x0) * i / max(1, len(datos) - 1), suelo - (suelo - techo) * (v - lo) / (hi - lo))
                    for i, v in enumerate(vals)], dtype=np.float32)
    cv2.line(img, (x0, suelo), (x1, suelo), (90, 94, 102), 2, cv2.LINE_AA)
    p = _suave(t / (ANIM * 1.3))
    segs = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    total = segs.sum() or 1
    hasta = total * p
    dibujados = [pts[0]]
    acum = 0.0
    for a, b, s in zip(pts[:-1], pts[1:], segs):
        if acum + s <= hasta:
            dibujados.append(b)
        else:
            dibujados.append(a + (b - a) * max(0.0, (hasta - acum) / s))
            break
        acum += s
    poli = np.array(dibujados, dtype=np.float32)
    if len(poli) >= 2:
        relleno = np.vstack([poli, [[poli[-1][0], suelo], [poli[0][0], suelo]]]).astype(np.int32)
        capa = img.copy()
        cv2.fillPoly(capa, [relleno], acento, cv2.LINE_AA)
        img = cv2.addWeighted(capa, 0.18, img, 0.82, 0)
        cv2.polylines(img, [poli.astype(np.int32)], False, acento, max(4, W // 320), cv2.LINE_AA)
        cabeza = tuple(int(c) for c in poli[-1])
        cv2.circle(img, cabeza, max(8, W // 180), acento, -1, cv2.LINE_AA)
    k = 1.4 if vertical else 1.0
    f_eti = int(min(W, H) * 0.028 * k)
    pasos = max(1, len(datos) // (4 if vertical else 7))
    for i, (etiqueta, v) in enumerate(datos):
        if i % pasos and i != len(datos) - 1:
            continue
        eti = _texto(str(etiqueta), "Montserrat-SemiBold.ttf", f_eti, (200, 200, 205), sombra=3)
        pegar(img, eti, int(pts[i][0] - eti.shape[1] / 2), suelo + 12, min(1.0, t / 0.4))
    for i in {0, len(datos) - 1, int(np.argmax(vals))}:
        if p >= (i / max(1, len(datos) - 1)) * 0.98:
            val = _texto(_num(vals[i], spec.get("unidad") or ""), "Montserrat-ExtraBold.ttf", int(min(W, H) * 0.04 * k),
                         rgb(estilo["color_texto"]))
            pegar(img, val, int(pts[i][0] - val.shape[1] / 2), int(pts[i][1] - val.shape[0] - 14))
    return img


def _cronologia(base: np.ndarray, spec: dict, estilo: dict, t: float, y0: int) -> np.ndarray:
    img = base.copy()
    H, W = img.shape[:2]
    datos = spec["datos"]
    vertical = H > W
    acento = rgb(estilo["color_acento"])
    n = len(datos)
    p = _suave(t / (ANIM * 1.2))
    if vertical:
        xe = int(W * 0.18)
        ya, yb = y0 + int(H * 0.03), int(H * 0.54)
        cv2.line(img, (xe, ya), (xe, int(ya + (yb - ya) * p)), (120, 124, 132), 3, cv2.LINE_AA)
        for i, (anio, texto) in enumerate(datos):
            y = int(ya + (yb - ya) * (i / max(1, n - 1)))
            q = _suave((t - 0.25 - i * 0.22) / 0.5)
            if q <= 0:
                continue
            cv2.circle(img, (xe, y), int(14 * q) + 1, acento, -1, cv2.LINE_AA)
            a = _texto(str(anio), estilo["fuente_titulos"], int(W * 0.095), acento)
            pegar(img, a, xe + 34, y - a.shape[0] // 2 - 22, q)
            fs = _fuente("Montserrat-SemiBold.ttf", int(W * 0.05))
            b = _capa(bloque(envolver(texto, fs, int(W * 0.66)), fs, (235, 235, 240), 1.15, alinear="izq", sombra=4))
            pegar(img, b, xe + 34, y + a.shape[0] // 2 - 14, q)
        return img
    ye = int(H * 0.56)
    xa, xb = int(W * 0.08), int(W * 0.92)
    cv2.line(img, (xa, ye), (int(xa + (xb - xa) * p), ye), (120, 124, 132), 3, cv2.LINE_AA)
    for i, (anio, texto) in enumerate(datos):
        x = int(xa + (xb - xa) * ((i + 0.5) / n))
        q = _suave((t - 0.2 - i * 0.22) / 0.5)
        if q <= 0:
            continue
        cv2.circle(img, (x, ye), int(13 * q) + 1, acento, -1, cv2.LINE_AA)
        arriba = i % 2 == 0
        a = _texto(str(anio), estilo["fuente_titulos"], int(H * 0.075), acento)
        fs = _fuente("Montserrat-SemiBold.ttf", int(H * 0.03))
        b = _capa(bloque(envolver(texto, fs, int((xb - xa) / n * 1.7)), fs, (235, 235, 240), 1.15, sombra=4))
        if arriba:
            pegar(img, b, x - b.shape[1] // 2, ye - 30 - b.shape[0], q)
            pegar(img, a, x - a.shape[1] // 2, ye - 40 - b.shape[0] - a.shape[0], q)
        else:
            pegar(img, a, x - a.shape[1] // 2, ye + 30, q)
            pegar(img, b, x - b.shape[1] // 2, ye + 36 + a.shape[0], q)
    return img


# ------------------------------------------------------------------ mapas

@lru_cache(maxsize=4)
def _geo(nombre: str) -> dict:
    ruta = CACHE / "mapas" / f"{nombre}.geojson"
    if not ruta.exists():
        ruta.parent.mkdir(parents=True, exist_ok=True)
        r = requests.get(NE.format(nombre), timeout=120)
        r.raise_for_status()
        ruta.write_bytes(r.content)
    return json.loads(ruta.read_text(encoding="utf-8"))


def _anillos(geom: dict) -> list[list]:
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    if geom["type"] == "MultiPolygon":
        return geom["coordinates"]
    return []


def _merc(lon, lat):
    lat = np.clip(lat, -80, 84)
    return np.radians(lon), np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))


class _Proyeccion:
    def __init__(self, zona, W, H):
        lon0, lat0, lon1, lat1 = zona
        x0, y0 = _merc(np.array(lon0), np.array(lat0))
        x1, y1 = _merc(np.array(lon1), np.array(lat1))
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        ancho, alto = (x1 - x0), (y1 - y0)
        if ancho / alto < W / H:
            ancho = alto * W / H
        else:
            alto = ancho * H / W
        self.esc = W / ancho
        self.x0, self.y1 = cx - ancho / 2, cy + alto / 2

    def __call__(self, lon, lat):
        x, y = _merc(np.asarray(lon, dtype=np.float64), np.asarray(lat, dtype=np.float64))
        return np.stack([(x - self.x0) * self.esc, (self.y1 - y) * self.esc], axis=-1)


def _zona(spec: dict, W: int, H: int) -> list[float]:
    if spec.get("zona"):
        return spec["zona"]
    lons = [p["lon"] for p in spec["puntos"]]
    lats = [p["lat"] for p in spec["puntos"]]
    lon0, lon1, lat0, lat1 = min(lons), max(lons), min(lats), max(lats)
    margen_lon = max(8.0, (lon1 - lon0) * 0.25)
    margen_lat = max(6.0, (lat1 - lat0) * 0.25)
    return [lon0 - margen_lon, lat0 - margen_lat, lon1 + margen_lon, lat1 + margen_lat]


def _desenrollar(puntos: list[dict]) -> list[float]:
    """Longitudes continuas para que una ruta cruce el Pacífico por el camino corto."""
    res, prev = [], None
    for p in puntos:
        lon = p["lon"]
        if prev is not None:
            while lon - prev > 180:
                lon -= 360
            while lon - prev < -180:
                lon += 360
        res.append(lon)
        prev = lon
    return res


def mapa_base(spec: dict, tam: tuple[int, int], estilo: dict) -> tuple[np.ndarray, _Proyeccion]:
    W, H = tam
    lons = _desenrollar(spec["puntos"]) if spec.get("puntos") else []
    spec_z = dict(spec)
    if lons:
        spec_z["puntos"] = [{**p, "lon": l} for p, l in zip(spec["puntos"], lons)]
    zona = _zona(spec_z, W, H)
    proy = _Proyeccion(zona, W, H)
    oceano = np.array(rgb(estilo["color_fondo"]), dtype=np.float32) * 0.8 + np.array([6, 14, 28], dtype=np.float32)
    img = np.empty((H, W, 3), np.uint8)
    img[:] = np.clip(oceano, 0, 255).astype(np.uint8)
    tierra, borde = (46, 50, 60), (70, 75, 86)
    for desfase in (-360, 0, 360):
        for poli in (_geo("ne_50m_land")["features"]):
            for anillos in _anillos(poli["geometry"]):
                for k, anillo in enumerate(anillos):
                    c = np.array(anillo, dtype=np.float64)
                    if c[:, 0].max() + desfase < zona[0] - 30 or c[:, 0].min() + desfase > zona[2] + 30:
                        continue
                    pts = proy(c[:, 0] + desfase, c[:, 1]).astype(np.int32)
                    cv2.fillPoly(img, [pts], tierra if k == 0 else tuple(int(v) for v in oceano), cv2.LINE_AA)
        resaltar = set(spec.get("resaltar") or [])
        acento = np.array(rgb(estilo["color_acento"]), dtype=np.float32)
        for pais in _geo("ne_110m_admin_0_countries")["features"]:
            iso = pais["properties"].get("ADM0_A3")
            for anillos in _anillos(pais["geometry"]):
                c = np.array(anillos[0], dtype=np.float64)
                if c[:, 0].max() + desfase < zona[0] - 30 or c[:, 0].min() + desfase > zona[2] + 30:
                    continue
                pts = proy(c[:, 0] + desfase, c[:, 1]).astype(np.int32)
                if iso in resaltar:
                    capa = img.copy()
                    cv2.fillPoly(capa, [pts], tuple(int(v) for v in acento), cv2.LINE_AA)
                    img = cv2.addWeighted(capa, 0.35, img, 0.65, 0)
                    cv2.polylines(img, [pts], True, tuple(int(v) for v in acento), 2, cv2.LINE_AA)
                else:
                    cv2.polylines(img, [pts], True, borde, 1, cv2.LINE_AA)
    # retícula muy tenue cada 10 grados
    reticula = img.copy()
    for lon in range(int(zona[0] // 10 * 10), int(zona[2]) + 11, 10):
        a, b = proy([lon, lon], [-80, 84])
        cv2.line(reticula, tuple(a.astype(int)), tuple(b.astype(int)), (120, 130, 150), 1, cv2.LINE_AA)
    for lat in range(-80, 81, 10):
        a, b = proy([zona[0] - 40, zona[2] + 40], [lat, lat])
        cv2.line(reticula, tuple(a.astype(int)), tuple(b.astype(int)), (120, 130, 150), 1, cv2.LINE_AA)
    img = cv2.addWeighted(reticula, 0.06, img, 0.94, 0)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    vineta = np.clip(1 - (((xx / W - 0.5) ** 2 + (yy / H - 0.5) ** 2) * 1.2), 0.45, 1)
    return (img * vineta[..., None]).astype(np.uint8), proy


def _arco(a: np.ndarray, b: np.ndarray, n: int = 48) -> np.ndarray:
    medio = (a + b) / 2
    d = b - a
    normal = np.array([-d[1], d[0]]) * 0.18
    ctrl = medio + normal
    t = np.linspace(0, 1, n)[:, None]
    return (1 - t) ** 2 * a + 2 * (1 - t) * t * ctrl + t ** 2 * b


def _mapa(base: np.ndarray, proy: _Proyeccion, spec: dict, estilo: dict, t: float, y0: int = 0) -> np.ndarray:
    img = base.copy()
    H, W = img.shape[:2]
    acento = rgb(estilo["color_acento"])
    puntos = spec.get("puntos") or []
    lons = _desenrollar(puntos)
    xy = [proy(l, p["lat"]) for l, p in zip(lons, puntos)]
    n = len(puntos)
    dur_ruta = max(1.2, 0.9 * (n - 1))
    if spec.get("ruta") and n >= 2:
        tramos = [_arco(xy[i], xy[i + 1]) for i in range(n - 1)]
        p = _suave((t - 0.4) / dur_ruta) * (n - 1)
        for i, tramo in enumerate(tramos):
            if p <= i:
                break
            frac = min(1.0, p - i)
            k = max(2, int(len(tramo) * frac))
            cv2.polylines(img, [tramo[:k].astype(np.int32)], False, acento, max(4, W // 330), cv2.LINE_AA)
            if frac < 1.0:
                cabeza = tuple(int(v) for v in tramo[k - 1])
                cv2.circle(img, cabeza, max(9, W // 160), (255, 255, 255), -1, cv2.LINE_AA)
    fs = int(min(W, H) * (0.05 if H > W else 0.034))
    for i, (p, c) in enumerate(zip(puntos, xy)):
        aparece = 0.2 + (i * dur_ruta / max(1, n - 1) if spec.get("ruta") and n > 1 else i * 0.25)
        q = _suave((t - aparece) / 0.45)
        if q <= 0:
            continue
        centro = tuple(int(v) for v in c)
        anillo = int(10 + 26 * min(1.0, (t - aparece) / 0.8))
        if t - aparece < 0.8:
            capa = img.copy()
            cv2.circle(capa, centro, anillo, acento, 3, cv2.LINE_AA)
            img = cv2.addWeighted(capa, 1 - min(1.0, (t - aparece) / 0.8), img, min(1.0, (t - aparece) / 0.8), 0)
        cv2.circle(img, centro, int(max(7, W // 190) * q) + 1, acento, -1, cv2.LINE_AA)
        cv2.circle(img, centro, int(max(7, W // 190) * q) + 1, (20, 20, 20), 2, cv2.LINE_AA)
        eti = _texto(p.get("n", ""), "Montserrat-ExtraBold.ttf", fs, (255, 255, 255), sombra=5, borde=2)
        lado = p.get("pos") or ("izq" if c[0] > W * 0.8 else "der")
        if lado == "izq":
            x, y = int(c[0] - eti.shape[1] - 18), int(c[1] - eti.shape[0] / 2)
        elif lado == "arriba":
            x, y = int(c[0] - eti.shape[1] / 2), int(c[1] - eti.shape[0] - 16)
        elif lado == "abajo":
            x, y = int(c[0] - eti.shape[1] / 2), int(c[1] + 16)
        else:
            x, y = int(c[0] + 18), int(c[1] - eti.shape[0] / 2)
        # que la etiqueta no se salga del cuadro ni pise el título
        margen = int(min(W, H) * 0.03)
        x = max(margen, min(x, W - eti.shape[1] - margen))
        y = max(y0, min(y, H - eti.shape[0] - margen))
        pegar(img, eti, x, y, q)
    return img


# ------------------------------------------------------------------ interfaz

def spec_de(v) -> dict:
    """Lo que hace falta para dibujar un visual animado (y su huella para la caché)."""
    if v.tipo == "grafico":
        return {"tipo": "grafico", "titulo": v.grafico, "forma": v.forma or "barras",
                "datos": [[str(a), b if (v.forma == "cronologia") else float(b)] for a, b in v.datos or []],
                "unidad": v.unidad, "sub": v.sub,
                "nota": v.nota, "destacar": v.destacar}
    return {"tipo": "mapa", "titulo": v.mapa, "sub": v.sub, "nota": v.nota, "ruta": bool(v.ruta), "zona": v.zona,
            "resaltar": v.resaltar, "puntos": [p.model_dump(exclude_none=True) for p in v.puntos or []]}


def guardar_spec(v, tam, estilo) -> Path:
    spec = spec_de(v)
    h = hashlib.sha256(json.dumps([spec, tam, sorted(estilo.items()), VERSION], sort_keys=True, default=str).encode()).hexdigest()[:20]
    ruta = CACHE / "animados" / f"{spec['tipo']}-{h}.json"
    if not ruta.exists():
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps({"spec": spec, "tam": list(tam), "estilo": estilo}, ensure_ascii=False), encoding="utf-8")
    return ruta


class Dibujante:
    def __init__(self, ruta_spec: Path):
        d = json.loads(Path(ruta_spec).read_text(encoding="utf-8"))
        self.spec, self.estilo = d["spec"], d["estilo"]
        self.W, self.H = d["tam"]
        if self.spec["tipo"] == "mapa":
            self.base, self.proy = mapa_base(self.spec, (self.W, self.H), self.estilo)
            self.y0 = _cabecera(self.base, self.spec.get("titulo") or "", self.spec.get("sub"), self.estilo)
            _nota(self.base, self.spec.get("nota") or "Mapa: Natural Earth", self.estilo)
        else:
            semilla = int(hashlib.sha1(json.dumps(self.spec).encode()).hexdigest()[:6], 16)
            self.base = _np(fondo(self.W, self.H, self.estilo, semilla))
            self.y0 = _cabecera(self.base, self.spec.get("titulo") or "", self.spec.get("sub"), self.estilo)
            _nota(self.base, self.spec.get("nota"), self.estilo)

    def cuadro(self, t: float) -> np.ndarray:
        if self.spec["tipo"] == "mapa":
            return _mapa(self.base, self.proy, self.spec, self.estilo, t, self.y0)
        forma = self.spec.get("forma", "barras")
        hacer = {"barras": _barras, "linea": _linea, "cronologia": _cronologia}[forma]
        return hacer(self.base, self.spec, self.estilo, t, self.y0)

    def final(self) -> Image.Image:
        return Image.fromarray(self.cuadro(30.0))
