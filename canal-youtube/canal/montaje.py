"""Monta el vídeo largo (16:9) y los Shorts (9:16) a partir de un guion."""
from __future__ import annotations

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import audio, metadatos, miniatura, movimiento, musica, registro, sfx, subtitulos
from .config import FUENTES, SALIDA
from .guion import Escena, Guion, Visual
from .subtitulos import Palabra
from .texto import tokenizar
from .visuales import Buscador, precargar_wikimedia, visuales_del_guion
from .voz import Narrador

ENTRADA = 0.35   # silencio antes de la primera palabra
COLA = 1.8       # silencio al final (la música se despide)
PLANO_MIN = 1.1  # segundos


@dataclass
class Linea:
    """Resultado de locutar una lista de escenas."""
    audio: np.ndarray
    palabras: list[Palabra]
    tramos: list[tuple[float, float]]  # tramo de pantalla de cada escena (incluye la pausa siguiente)
    duracion: float


@dataclass
class Plano:
    escena: int
    visual: Visual
    ini: float
    fin: float
    fundido_entrada: float = 0.0
    fundido_salida: float = 0.0


@dataclass
class Pieza:
    """Un vídeo producido (largo o short) y lo necesario para describirlo."""
    tipo: str
    ruta: Path
    duracion: float
    palabras: list[Palabra]
    tramos: list[tuple[float, float]]
    recursos: list = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def locutar(escenas: list[Escena], narrador: Narrador, cfg: dict, capitulos: bool) -> Linea:
    vcfg = cfg["voz"]
    partes = [audio.silencio(ENTRADA)]
    t = ENTRADA
    palabras: list[Palabra] = []
    inicios, pausas = [], []
    textos = [e.narracion for e in escenas]
    for i, e in enumerate(escenas):
        tokens = tokenizar(e.narracion, narrador.normalizar, vcfg.get("pronunciacion"))
        contexto = (" ".join(textos[max(0, i - 2):i]), " ".join(textos[i + 1:i + 2]))
        loc = narrador.locutar(tokens, contexto)
        inicios.append(t)
        for tok, (a, b) in zip(tokens, loc.tiempos):
            palabras.append(Palabra(tok.texto, t + a, t + b, tok.fin_frase, i))
        partes.append(loc.audio)
        t += len(loc.audio) / audio.SR
        if i + 1 < len(escenas):
            pausa = vcfg["pausa_entre_capitulos"] if (capitulos and escenas[i + 1].capitulo) else vcfg["pausa_entre_escenas"]
            partes.append(audio.silencio(pausa))
            pausas.append(pausa)
            t += pausa
    partes.append(audio.silencio(COLA))
    t += COLA
    # la imagen cambia un poco antes de que entre la voz de la escena siguiente (corte más natural)
    cortes = [0.0] + [inicios[i] - min(0.3, pausas[i - 1] * 0.5) for i in range(1, len(escenas))]
    tramos = [(cortes[i], cortes[i + 1] if i + 1 < len(cortes) else t) for i in range(len(escenas))]
    return Linea(np.concatenate(partes), palabras, tramos, t)


def planificar(escenas: list[Escena], tramos, capitulos: bool, avisos: list[str]) -> list[Plano]:
    planos: list[Plano] = []
    for i, (e, (a, b)) in enumerate(zip(escenas, tramos)):
        visuales = list(e.visuales)
        while len(visuales) > 1 and (b - a) / len(visuales) < PLANO_MIN:
            quitado = visuales.pop()
            avisos.append(f"escena {e.id}: muy corta para {len(visuales) + 1} visuales; quito «{quitado.valor}»")
        total = sum(v.peso for v in visuales)
        t = a
        for v in visuales:
            d = (b - a) * v.peso / total
            planos.append(Plano(i, v, t, t + d))
            t += d
    if planos:
        planos[0].fundido_entrada = 0.4
        planos[-1].fundido_salida = 0.9
    if capitulos:
        for j in range(1, len(planos)):
            if planos[j].escena != planos[j - 1].escena and escenas[planos[j].escena].capitulo:
                planos[j].fundido_entrada = 0.25
                planos[j - 1].fundido_salida = 0.25
    return planos


def _render_planos(planos: list[Plano], buscador: Buscador, tam, fps: int, resolver=None) -> list[Path]:
    trabajos = []
    for k, p in enumerate(planos):
        v = resolver(p.visual) if resolver else p.visual
        n = round(p.fin * fps) - round(p.ini * fps)
        recurso = buscador.conseguir(v, duracion=n / fps)
        if (k + 1) % 20 == 0:
            print(f"  visuales conseguidos: {k + 1}/{len(planos)}", flush=True)
        trabajos.append((recurso, n, v.mov, k, p.fundido_entrada, p.fundido_salida, v.encuadre))
    hechos = []

    def hacer(a):
        r = movimiento.clip(a[0], a[1], tam, fps, a[2], a[3], a[4], a[5], a[6])
        hechos.append(1)
        if len(hechos) % 10 == 0 or len(hechos) == len(trabajos):
            print(f"  planos montados: {len(hechos)}/{len(trabajos)}", flush=True)
        return r

    with ThreadPoolExecutor(max_workers=3) as ex:
        return list(ex.map(hacer, trabajos))


def _filtro_estilo(cfg: dict, ass: Path) -> str:
    est = cfg["estilo"]
    f = ["eq=contrast=1.04:saturation=1.06"]
    if est.get("vineta"):
        f.append("vignette=angle=PI/6")
    if est.get("grano"):
        f.append(f"noise=alls={int(est['grano'])}:allf=t")
    f.append(f"subtitles=filename={ass}:fontsdir={FUENTES}")
    return ",".join(f)


def _componer(clips: list[Path], mezcla: Path, ass: Path, salida: Path, cfg: dict, fps: int) -> None:
    lista = salida.with_suffix(".txt")
    lista.write_text("".join(f"file '{c}'\n" for c in clips), encoding="utf-8")
    audio.ffmpeg("-f", "concat", "-safe", "0", "-i", str(lista), "-i", str(mezcla),
                 "-filter_complex", f"[0:v]{_filtro_estilo(cfg, ass)},format=yuv420p[v]",
                 "-map", "[v]", "-map", "1:a", "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                 "-profile:v", "high", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart",
                 "-shortest", str(salida))
    lista.unlink(missing_ok=True)


def producir_largo(g: Guion, cfg: dict, narrador: Narrador, carpeta: Path) -> Pieza:
    tam = tuple(cfg["largo"]["resolucion"])
    fps = int(cfg["largo"]["fps"])
    avisos: list[str] = []
    linea = locutar(g.escenas, narrador, cfg, capitulos=True)
    if cfg["estilo"].get("sfx_transiciones", True):
        cambios = [linea.tramos[i][0] for i, e in enumerate(g.escenas) if e.capitulo and i > 0]
        efectos = sfx.pista(len(linea.audio) / audio.SR, cambios)
        n = min(len(efectos), len(linea.audio))
        linea.audio[:n] += efectos[:n] * 0.32
    voz = audio.escribir(carpeta / "trabajo" / "voz.wav", linea.audio)
    pista = musica.elegir(linea.duracion, cfg["estilo"]["animo_musica"], g.id)
    mezcla = audio.mezclar(voz, carpeta / "trabajo" / "mezcla.wav", pista, cfg["estilo"]["musica_db"])

    buscador = Buscador(cfg, tam, g.id)
    planos = planificar(g.escenas, linea.tramos, True, avisos)
    clips = _render_planos(planos, buscador, tam, fps)

    rotulos = []
    for i, e in enumerate(g.escenas):
        if e.texto_pantalla:
            a, b = linea.tramos[i]
            rotulos.append((a + 0.2, min(b - 0.1, a + 3.4), e.texto_pantalla))
    caps = metadatos.capitulos(g, linea.tramos)
    cartelas = [(t, n + 1, titulo) for n, (t, titulo) in enumerate(caps) if n > 0]
    subs = linea.palabras if cfg["largo"]["subtitulos_quemados"] else None
    ass = carpeta / "trabajo" / "largo.ass"
    ass.write_text(subtitulos.ass_largo(*tam, cfg["estilo"], rotulos, cartelas, subs), encoding="utf-8")
    salida = carpeta / "largo.mp4"
    _componer(clips, mezcla, ass, salida, cfg, fps)
    (carpeta / "largo.srt").write_text(subtitulos.srt(linea.palabras), encoding="utf-8")
    (carpeta / "linea-largo.json").write_text(json.dumps({
        "duracion": linea.duracion,
        "palabras": [{"texto": p.texto, "ini": round(p.ini, 2), "fin": round(p.fin, 2), "escena": g.escenas[p.escena].id}
                     for p in linea.palabras]}, ensure_ascii=False), encoding="utf-8")
    buscador.guardar_usados(g.id)
    return Pieza("largo", salida, linea.duracion, linea.palabras, linea.tramos, buscador.recursos,
                 avisos + buscador.avisos)


def producir_short(g: Guion, indice: int, cfg: dict, narrador: Narrador, carpeta: Path) -> Pieza:
    s = g.shorts[indice]
    tam = tuple(cfg["short"]["resolucion"])
    fps = int(cfg["short"]["fps"])
    avisos: list[str] = []
    linea = locutar(s.escenas, narrador, cfg, capitulos=False)
    voz = audio.escribir(carpeta / "trabajo" / f"{s.id}-voz.wav", linea.audio)
    pista = musica.elegir(linea.duracion, cfg["estilo"]["animo_musica"], f"{g.id}-{s.id}")
    mezcla = audio.mezclar(voz, carpeta / "trabajo" / f"{s.id}-mezcla.wav", pista, cfg["estilo"]["musica_db"] + 2)

    por_id = {e.id: e for e in g.escenas}

    def resolver(v: Visual) -> Visual:
        return por_id[v.de_escena].visuales[0] if v.de_escena else v

    buscador = Buscador(cfg, tam, g.id)
    planos = planificar(s.escenas, linea.tramos, False, avisos)
    clips = _render_planos(planos, buscador, tam, fps, resolver)
    rotulos = []
    for i, e in enumerate(s.escenas):
        if e.texto_pantalla:
            a, b = linea.tramos[i]
            rotulos.append((a + (0.0 if i == 0 else 0.15), min(b, a + 2.6), e.texto_pantalla))
    ass = carpeta / "trabajo" / f"{s.id}.ass"
    ass.write_text(subtitulos.ass_short(linea.palabras, *tam, cfg["estilo"], int(cfg["short"]["palabras_por_grupo"]),
                                        rotulos), encoding="utf-8")
    salida = carpeta / f"{s.id}.mp4"
    _componer(clips, mezcla, ass, salida, cfg, fps)
    (carpeta / f"{s.id}.srt").write_text(subtitulos.srt(linea.palabras), encoding="utf-8")
    if linea.duracion > cfg["short"]["duracion_max_seg"]:
        avisos.append(f"{s.id}: dura {linea.duracion:.0f} s, más de lo que YouTube acepta como Short")
    return Pieza("short", salida, linea.duracion, linea.palabras, linea.tramos, buscador.recursos,
                 avisos + buscador.avisos)


def producir(g: Guion, cfg: dict, solo: str | None = None, proveedor_voz: str | None = None) -> dict:
    carpeta = SALIDA / g.id
    (carpeta / "trabajo").mkdir(parents=True, exist_ok=True)
    precargar_wikimedia(visuales_del_guion(g), cfg)
    narrador = Narrador(cfg, proveedor_voz)
    piezas: list[Pieza] = []
    if solo in (None, "largo"):
        piezas.append(producir_largo(g, cfg, narrador, carpeta))
    if solo in (None, "shorts"):
        for i in range(len(g.shorts)):
            piezas.append(producir_short(g, i, cfg, narrador, carpeta))
    largo = next((p for p in piezas if p.tipo == "largo"), None)
    if largo:
        miniatura.crear(g, cfg, carpeta)
    meta = metadatos.escribir(g, cfg, carpeta, piezas, narrador.p.nombre)
    registro.accion("producir", video=g.id, piezas=[p.ruta.name for p in piezas], voz=narrador.p.nombre)
    return meta


def limpiar_trabajo(carpeta: Path) -> None:
    shutil.rmtree(carpeta / "trabajo", ignore_errors=True)
