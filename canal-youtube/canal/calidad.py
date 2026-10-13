"""Control de calidad: lo que se puede medir se mide antes de que lo vea nadie."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from . import audio
from .graficos import _fuente
from .guion import Guion, Hallazgo, anteriores, revisar
from .config import GUIONES
from .visuales import Buscador, precargar_wikimedia, visuales_del_guion


def sondear(ruta: Path) -> dict:
    res = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(ruta)],
                         capture_output=True, text=True)
    d = json.loads(res.stdout or "{}")
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    a = next((s for s in d.get("streams", []) if s.get("codec_type") == "audio"), {})
    num, den = (v.get("r_frame_rate") or "0/1").split("/")
    return {"duracion": float(d.get("format", {}).get("duration", 0)), "ancho": v.get("width"), "alto": v.get("height"),
            "fps": round(float(num) / float(den or 1), 2), "audio": bool(a), "mb": round(int(d.get("format", {}).get("size", 0)) / 1e6, 1)}


def _detectar(ruta: Path, filtro: str, patron: str) -> list[tuple[float, float]]:
    res = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(ruta), *filtro.split(" "), "-f", "null", "-"],
                         capture_output=True, text=True)
    return [(float(a), float(b)) for a, b in re.findall(patron, res.stderr)]


def revisar_video(ruta: Path, tipo: str, cfg: dict) -> list[Hallazgo]:
    h: list[Hallazgo] = []
    s = sondear(ruta)
    w, alto = (cfg["largo"] if tipo == "largo" else cfg["short"])["resolucion"]
    if (s["ancho"], s["alto"]) != (w, alto):
        h.append(Hallazgo("error", f"{ruta.name}: {s['ancho']}×{s['alto']}, se esperaba {w}×{alto}"))
    if not s["audio"]:
        h.append(Hallazgo("error", f"{ruta.name}: no tiene audio"))
    if tipo == "short" and s["duracion"] > cfg["short"]["duracion_max_seg"]:
        h.append(Hallazgo("error", f"{ruta.name}: {s['duracion']:.0f} s; un Short no puede pasar de {cfg['short']['duracion_max_seg']} s"))
    if tipo == "largo" and s["duracion"] < 480:
        h.append(Hallazgo("aviso", f"{ruta.name}: {s['duracion'] / 60:.1f} min; desde 8 min se pueden poner anuncios a mitad"))
    son = audio.sonoridad(ruta)
    if son and not (-15.5 <= son["lufs"] <= -12.5):
        h.append(Hallazgo("aviso", f"{ruta.name}: volumen {son['lufs']:.1f} LUFS (objetivo -14)"))
    if son and son["pico_db"] > -0.5:
        h.append(Hallazgo("aviso", f"{ruta.name}: picos de {son['pico_db']:.1f} dBTP, puede saturar"))
    silencios = _detectar(ruta, "-af silencedetect=noise=-50dB:d=2.5 -vn",
                          r"silence_start: ([\d.]+)[\s\S]*?silence_end: ([\d.]+)")
    for a, b in silencios:
        if a > 1.0 and b < s["duracion"] - 2.5:
            h.append(Hallazgo("aviso", f"{ruta.name}: silencio de {b - a:.1f} s en {a:.0f} s"))
    negros = _detectar(ruta, "-vf blackdetect=d=0.7:pix_th=0.06 -an", r"black_start:([\d.]+) black_end:([\d.]+)")
    for a, b in negros:
        if a > 0.6 and b < s["duracion"] - 1.2:
            h.append(Hallazgo("aviso", f"{ruta.name}: pantalla negra {b - a:.1f} s en {a:.0f} s"))
    return h


def hoja_contactos(ruta: Path, salida: Path, columnas: int = 6, cada: float | None = None) -> Path:
    """Fotogramas repartidos por todo el vídeo, con su minuto, para revisar de un vistazo."""
    s = sondear(ruta)
    dur = s["duracion"]
    n = columnas * (4 if s["ancho"] > s["alto"] else 2)
    paso = cada or dur / (n + 1)
    tiempos = [paso * (i + 1) for i in range(int(min(n, dur / paso)))]
    vertical = s["alto"] > s["ancho"]
    tw, th = (200, 356) if vertical else (320, 180)
    filas = (len(tiempos) + columnas - 1) // columnas
    hoja = Image.new("RGB", (columnas * (tw + 8) + 8, filas * (th + 30) + 8), (24, 24, 28))
    f = _fuente("Montserrat-SemiBold.ttf", 16)
    d = ImageDraw.Draw(hoja)
    tmp = salida.with_suffix(".tmp.jpg")
    for i, t in enumerate(tiempos):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(ruta), "-frames:v", "1",
                        "-vf", f"scale={tw}:{th}", str(tmp)], check=True)
        x, y = 8 + (i % columnas) * (tw + 8), 8 + (i // columnas) * (th + 30)
        hoja.paste(Image.open(tmp), (x, y))
        d.text((x, y + th + 4), f"{int(t // 60)}:{int(t % 60):02d}", font=f, fill=(230, 230, 230))
    tmp.unlink(missing_ok=True)
    hoja.save(salida, quality=85)
    return salida


def hoja_visuales(g: Guion, cfg: dict, salida: Path, short: int | None = None) -> Path:
    """Antes de montar: qué imagen ha tocado a cada plano, con su id para fijarla o cambiarla."""
    vertical = short is not None
    tam = tuple(cfg["short" if vertical else "largo"]["resolucion"])
    precargar_wikimedia(visuales_del_guion(g), cfg)
    b = Buscador(cfg, tam, g.id)
    escenas = g.shorts[short].escenas if vertical else g.escenas
    por_id = {e.id: e for e in g.escenas}
    filas = []
    for e in escenas:
        for v in e.visuales:
            vv = por_id[v.de_escena].visuales[0] if v.de_escena else v
            r = b.conseguir(vv, duracion=4)
            filas.append((e, vv, r))
    tw, th = (180, 320) if vertical else (320, 180)
    columnas = 6 if vertical else 4
    alto_txt = 64
    n = len(filas)
    hoja = Image.new("RGB", (columnas * (tw + 10) + 10, ((n + columnas - 1) // columnas) * (th + alto_txt + 10) + 10),
                     (24, 24, 28))
    d = ImageDraw.Draw(hoja)
    f = _fuente("Montserrat-SemiBold.ttf", 14)
    for i, (e, v, r) in enumerate(filas):
        x, y = 10 + (i % columnas) * (tw + 10), 10 + (i // columnas) * (th + alto_txt + 10)
        if r.tipo == "video":
            cuadro = r.ruta.with_suffix(".vista.jpg")
            if not cuadro.exists():
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "1", "-i", str(r.ruta), "-frames:v", "1",
                                str(cuadro)], check=True)
            img = Image.open(cuadro)
        elif r.tipo == "animado":
            from .animados import Dibujante

            img = Dibujante(r.ruta).final()
        else:
            img = Image.open(r.ruta)
            if v.encuadre:
                x, y, w, hh = v.encuadre
                img = img.crop((int(x * img.width), int(y * img.height), int((x + w) * img.width), int((y + hh) * img.height)))
        img = img.convert("RGB")
        img.thumbnail((tw, th))
        hoja.paste(img, (x + (tw - img.width) // 2, y + (th - img.height) // 2))
        d.text((x, y + th + 4), f"{i + 1}. {e.id} · {v.tipo}", font=f, fill=(245, 197, 24))
        d.text((x, y + th + 22), (r.id if not r.generado else "rótulo")[:34], font=f, fill=(230, 230, 230))
        d.text((x, y + th + 40), (r.licencia or "")[:34], font=f, fill=(150, 150, 150))
    hoja.save(salida, quality=85)
    if b.avisos:
        salida.with_suffix(".avisos.txt").write_text("\n".join(b.avisos), encoding="utf-8")
    return salida


def informe(g: Guion, cfg: dict, carpeta: Path) -> tuple[Path, bool]:
    hallazgos, stats = revisar(g, cfg, anteriores(GUIONES))
    meta = json.loads((carpeta / "metadatos.json").read_text(encoding="utf-8"))
    secciones = [("Guion", hallazgos)]
    if meta.get("largo") and (carpeta / meta["largo"]["archivo"]).exists():
        hv = revisar_video(carpeta / meta["largo"]["archivo"], "largo", cfg)
        hv += [Hallazgo("aviso", a) for a in meta["largo"].get("avisos", [])]
        caps = meta["largo"]["capitulos"]
        segs = [_seg(c[0]) for c in caps] + [meta["largo"]["duracion_seg"]]
        for (t, c), a, b in zip(caps, segs, segs[1:]):
            if b - a < 10:
                hv.append(Hallazgo("aviso", f"capítulo «{c}» dura {b - a:.0f} s; YouTube exige 10 s por capítulo"))
        secciones.append(("Vídeo largo", hv))
        hoja_contactos(carpeta / meta["largo"]["archivo"], carpeta / "revision-largo.jpg")
    for sid, s in meta.get("shorts", {}).items():
        if (carpeta / s["archivo"]).exists():
            hs = revisar_video(carpeta / s["archivo"], "short", cfg) + [Hallazgo("aviso", a) for a in s.get("avisos", [])]
            secciones.append((f"Short {sid}", hs))
            hoja_contactos(carpeta / s["archivo"], carpeta / f"revision-{sid}.jpg", columnas=6)
    errores = sum(1 for _, hs in secciones for x in hs if x.nivel == "error")
    lineas = [f"# Control de calidad · {g.id}", "",
              f"**Estado:** {'❌ con errores, no se sube' if errores else '✅ listo para tu revisión'}", "",
              f"Palabras: {stats['palabras']} · duración estimada {stats['minutos_estimados']} min · "
              f"{stats['escenas']} escenas · {stats['capitulos']} capítulos · {stats['visuales']} visuales · "
              f"{stats['shorts']} shorts", ""]
    for titulo, hs in secciones:
        lineas.append(f"## {titulo}")
        if not hs:
            lineas.append("- ✅ Sin problemas")
        for x in hs:
            lineas.append(f"- {'❌' if x.nivel == 'error' else '⚠️'} {x.texto}")
        lineas.append("")
    lineas += [
        "## Antes de publicar (lo confirma una persona)", "",
        "- [ ] He visto el vídeo entero: los datos son correctos y están en las fuentes.",
        "- [ ] Cada imagen corresponde a lo que se cuenta; nada induce a error.",
        "- [ ] Título y miniatura cuentan lo que hay en el vídeo (sin promesas falsas).",
        f"- [ ] Contenido alterado o sintético realista: **{'sí' if g.sintetico_realista else 'no'}** (revisa que sea correcto).",
        "- [ ] No es contenido dirigido a niños.",
        "- [ ] La música es propia/generada o de la Biblioteca de audio de YouTube.",
    ]
    ruta = carpeta / "calidad.md"
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return ruta, errores == 0


def _seg(marca: str) -> float:
    partes = [int(p) for p in marca.split(":")]
    s = 0
    for p in partes:
        s = s * 60 + p
    return float(s)
