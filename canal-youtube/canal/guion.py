"""Formato del guion (JSON) y su revisión editorial antes de producir."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

TIPOS_VISUAL = ("stock", "foto", "wikimedia", "ia", "tarjeta", "dato", "cita", "grafico", "mapa", "archivo", "de_escena")
PALABRAS_POR_SEG = 2.6  # ~155 palabras/minuto, ritmo de narración de documental


class Punto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-360, le=360)
    pos: Literal["izq", "der", "arriba", "abajo"] | None = None


class Visual(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stock: str | None = None      # vídeo de stock (búsqueda en inglés), si no hay, foto
    foto: str | None = None       # foto de stock
    wikimedia: str | None = None  # imagen libre de Wikimedia Commons
    ia: str | None = None         # prompt para imagen generada con IA
    tarjeta: str | None = None    # rótulo grande sobre fondo de marca
    dato: str | None = None       # cifra grande (con `sub` como explicación)
    cita: str | None = None       # cita textual (con `autor`)
    grafico: str | None = None    # título de un gráfico animado (con `datos` y `forma`)
    mapa: str | None = None       # título de un mapa animado (con `puntos`, `ruta`, `resaltar`)
    archivo: str | None = None    # ruta a un archivo propio (imagen o vídeo)
    de_escena: str | None = None  # reutiliza el primer visual de otra escena (para Shorts)
    sub: str | None = None
    autor: str | None = None
    mov: Literal["zoom_in", "zoom_out", "izq", "der", "arriba", "abajo", "fijo"] | None = None
    peso: float = Field(default=1.0, gt=0)
    encuadre: list[float] | None = Field(default=None, min_length=4, max_length=4)  # detalle x,y,ancho,alto (0-1)
    # gráficos
    forma: Literal["barras", "linea", "cronologia"] | None = None
    datos: list[tuple[str | int | float, float | str]] | None = None
    unidad: str | None = None
    destacar: list[str] | None = None
    nota: str | None = None        # fuente del dato o del mapa, en pequeño
    # mapas
    puntos: list[Punto] | None = None
    ruta: bool = False
    zona: list[float] | None = Field(default=None, min_length=4, max_length=4)  # lon0, lat0, lon1, lat1
    resaltar: list[str] | None = None  # códigos ISO3 de países (ESP, BOL, MEX…)

    @model_validator(mode="after")
    def _un_tipo(self):
        tipos = [t for t in TIPOS_VISUAL if getattr(self, t)]
        if len(tipos) != 1:
            raise ValueError(f"cada visual lleva exactamente un tipo de {TIPOS_VISUAL}; este tiene {tipos or 'ninguno'}")
        return self

    @model_validator(mode="after")
    def _completo(self):
        if self.grafico:
            if not self.datos or len(self.datos) < 2:
                raise ValueError(f"el gráfico «{self.grafico}» necesita `datos` (al menos 2 pares [etiqueta, valor])")
            if (self.forma or "barras") != "cronologia":
                for et, v in self.datos:
                    if not isinstance(v, (int, float)):
                        raise ValueError(f"gráfico «{self.grafico}»: el valor de «{et}» debe ser un número")
        if self.mapa and not self.puntos and not self.zona:
            raise ValueError(f"el mapa «{self.mapa}» necesita `puntos` o `zona`")
        if self.encuadre:
            x, y, w, h = self.encuadre
            if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 - x + 1e-6 and 0 < h <= 1 - y + 1e-6):
                raise ValueError("encuadre: [x, y, ancho, alto] entre 0 y 1, dentro de la imagen")
        return self

    @property
    def tipo(self) -> str:
        return next(t for t in TIPOS_VISUAL if getattr(self, t))

    @property
    def valor(self) -> str:
        return getattr(self, self.tipo)


class Escena(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    capitulo: str | None = None
    narracion: str = Field(min_length=1)
    visuales: list[Visual] = Field(min_length=1)
    texto_pantalla: str | None = None


class Short(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    titulo: str
    descripcion: str = ""
    escenas: list[Escena] = Field(min_length=1)


class Fuente(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titulo: str
    url: str


class Miniatura(BaseModel):
    model_config = ConfigDict(extra="forbid")

    texto: str
    visual: Visual
    texto_secundario: str | None = None


class Guion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,80}$")
    tema: str
    titulos: list[str] = Field(min_length=1, max_length=3)
    descripcion: str
    etiquetas: list[str] = []
    hashtags: list[str] = []
    fuentes: list[Fuente] = []
    miniatura: Miniatura
    sintetico_realista: bool = False
    notas: str = ""
    escenas: list[Escena] = Field(min_length=1)
    shorts: list[Short] = []

    @model_validator(mode="after")
    def _ids(self):
        ids = [e.id for e in self.escenas]
        if len(ids) != len(set(ids)):
            raise ValueError("hay ids de escena repetidos")
        for s in self.shorts:
            for e in s.escenas:
                for v in e.visuales:
                    if v.de_escena and v.de_escena not in ids:
                        raise ValueError(f"short {s.id}: de_escena '{v.de_escena}' no existe")
        return self


def cargar(ruta: str | Path) -> Guion:
    ruta = Path(ruta)
    try:
        return Guion.model_validate(json.loads(ruta.read_text(encoding="utf-8")))
    except ValidationError as e:
        raise SystemExit(f"El guion {ruta.name} no es válido:\n{e}") from None


# ---------------------------------------------------------------- revisión editorial

@dataclass
class Hallazgo:
    nivel: Literal["error", "aviso"]
    texto: str


MULETILLAS = [
    "en este vídeo", "en este video", "en el vídeo de hoy", "en el video de hoy", "sin más dilación",
    "no olvides suscribirte", "dale like", "dale a like", "bienvenidos a", "hola a todos",
    "hoy vamos a hablar", "prepárate para", "te sorprenderá", "en conclusión", "en resumen",
    "adentrémonos", "sumérgete", "sumerjámonos", "fascinante mundo", "viaje fascinante",
    "desde tiempos inmemoriales", "a lo largo de la historia", "cabe destacar", "es importante destacar",
    "en definitiva", "no te lo pierdas", "quédate hasta el final",
]


def palabras(texto: str) -> int:
    return len(re.findall(r"[\wÁÉÍÓÚÜÑáéíóúüñ'’-]+", texto))


def frases(texto: str) -> list[str]:
    return [f.strip() for f in re.split(r"(?<=[.!?…])\s+", texto) if f.strip()]


def _tejas(texto: str, n: int = 5) -> set[str]:
    toks = re.findall(r"\w+", texto.lower())
    return {" ".join(toks[i:i + n]) for i in range(max(0, len(toks) - n + 1))}


def narracion_total(g: Guion) -> str:
    return " ".join(e.narracion for e in g.escenas)


def similitud(a: str, b: str) -> float:
    ta, tb = _tejas(a), _tejas(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _revisar_escenas(escenas: list[Escena], plano_max: float, prefijo: str) -> list[Hallazgo]:
    h: list[Hallazgo] = []
    for e in escenas:
        texto = e.narracion.lower()
        for m in MULETILLAS:
            if m in texto:
                h.append(Hallazgo("aviso", f"{prefijo}{e.id}: muletilla «{m}»; suena a relleno o a IA, reescríbela"))
        for f in frases(e.narracion):
            if palabras(f) > 35:
                h.append(Hallazgo("aviso", f"{prefijo}{e.id}: frase de {palabras(f)} palabras; pártela, de oído se pierde"))
        seg = palabras(e.narracion) / PALABRAS_POR_SEG
        pesos = sum(v.peso for v in e.visuales)
        plano = seg * max(v.peso for v in e.visuales) / pesos
        if plano > plano_max:
            h.append(Hallazgo("aviso", f"{prefijo}{e.id}: un plano duraría ~{plano:.1f} s (máximo {plano_max:.1f} s); añade otro visual"))
    return h


def revisar(g: Guion, cfg: dict, anteriores: dict[str, str] | None = None) -> tuple[list[Hallazgo], dict]:
    """Devuelve (hallazgos, estadísticas). Los errores bloquean la producción."""
    h: list[Hallazgo] = []
    largo = cfg["largo"]
    plano_max = float(cfg["visuales"]["plano_max_seg"])

    total = palabras(narracion_total(g))
    minutos = total / PALABRAS_POR_SEG / 60
    capitulos = [e for e in g.escenas if e.capitulo]
    visuales = [v for e in g.escenas for v in e.visuales]

    for t in g.titulos:
        if len(t) > 100:
            h.append(Hallazgo("error", f"título de {len(t)} caracteres (máximo 100): «{t}»"))
        elif len(t) > 70:
            h.append(Hallazgo("aviso", f"título de {len(t)} caracteres; en el móvil se corta hacia los 70: «{t}»"))
        if t.isupper():
            h.append(Hallazgo("aviso", f"título todo en mayúsculas: «{t}»"))
    if re.search(r"[<>]", g.descripcion):
        h.append(Hallazgo("error", "la descripción no puede llevar < ni > (YouTube la rechaza)"))
    if len(", ".join(g.etiquetas)) > 450:
        h.append(Hallazgo("error", "las etiquetas pasan de 450 caracteres (límite de YouTube: 500)"))
    if len(g.hashtags) > 15:
        h.append(Hallazgo("error", "más de 15 hashtags: YouTube los ignora todos"))
    elif len(g.hashtags) > 3:
        h.append(Hallazgo("aviso", "solo los 3 primeros hashtags salen encima del título"))
    if len(g.fuentes) < 3:
        h.append(Hallazgo("aviso" if g.fuentes else "error",
                          f"solo {len(g.fuentes)} fuentes; cada dato del guion debe poder comprobarse (mínimo 3)"))
    for f in g.fuentes:
        if not f.url.startswith(("http://", "https://")):
            h.append(Hallazgo("error", f"fuente sin URL válida: {f.titulo}"))

    if not g.escenas[0].capitulo:
        h.append(Hallazgo("aviso", "la primera escena no tiene capítulo; se llamará «Introducción»"))
    if len(capitulos) < 3:
        h.append(Hallazgo("aviso", f"{len(capitulos)} capítulos; YouTube necesita al menos 3 para mostrarlos"))
    if total < largo["palabras_min"]:
        h.append(Hallazgo("aviso", f"{total} palabras (~{minutos:.1f} min): por debajo del mínimo del canal ({largo['palabras_min']}); cada minuto visto cuenta para las horas del Programa de Partners"))
    if total > largo["palabras_max"]:
        h.append(Hallazgo("aviso", f"{total} palabras (~{minutos:.1f} min): por encima de {largo['palabras_max']}; ¿sobra relleno?"))
    gancho = palabras(g.escenas[0].narracion)
    if gancho > 45:
        h.append(Hallazgo("aviso", f"el gancho tiene {gancho} palabras; los primeros 10-15 s deciden si se quedan, recórtalo"))

    h += _revisar_escenas(g.escenas, plano_max, "")

    graficos = sum(1 for v in visuales if v.tipo in ("tarjeta", "dato", "cita"))  # mapas y gráficos de datos sí cuentan como imagen
    if visuales and graficos / len(visuales) > 0.35:
        h.append(Hallazgo("aviso", f"{graficos} de {len(visuales)} visuales son rótulos; parecerá una presentación, mete más imagen real"))
    busquedas: dict[str, int] = {}
    for v in visuales:
        if v.tipo in ("stock", "foto", "wikimedia", "ia"):
            busquedas[v.valor.lower()] = busquedas.get(v.valor.lower(), 0) + 1
    for b, n in busquedas.items():
        if n > 2:
            h.append(Hallazgo("aviso", f"la búsqueda «{b}» se repite {n} veces; varía las imágenes"))
    if any(v.tipo == "ia" for v in visuales) and not g.sintetico_realista:
        h.append(Hallazgo("aviso", "hay imágenes IA: si parecen reales (personas, lugares o hechos reales), pon sintetico_realista=true para activar la etiqueta de YouTube"))

    for s in g.shorts:
        n = sum(palabras(e.narracion) for e in s.escenas)
        seg = n / PALABRAS_POR_SEG
        if seg > cfg["short"]["duracion_max_seg"] * 0.95:
            h.append(Hallazgo("error", f"short {s.id}: ~{seg:.0f} s, pasa de los {cfg['short']['duracion_max_seg']} s que admite YouTube"))
        elif seg > cfg["short"]["duracion_objetivo_seg"] * 1.25:
            h.append(Hallazgo("aviso", f"short {s.id}: ~{seg:.0f} s; los que mejor retienen rondan {cfg['short']['duracion_objetivo_seg']} s"))
        if palabras(s.escenas[0].narracion) > 22:
            h.append(Hallazgo("aviso", f"short {s.id}: el gancho debe entrar en 1-2 s; recorta la primera frase"))
        if len(s.titulo) > 100:
            h.append(Hallazgo("error", f"short {s.id}: título de más de 100 caracteres"))
        h += _revisar_escenas(s.escenas, plano_max * 0.6, f"short {s.id}/")

    for otro_id, texto in (anteriores or {}).items():
        if otro_id == g.id:
            continue
        sim = similitud(narracion_total(g), texto)
        if sim > 0.35:
            h.append(Hallazgo("error", f"el guion se parece demasiado a {otro_id} ({sim:.0%}); YouTube desmonetiza el contenido repetitivo"))
        elif sim > 0.12:
            h.append(Hallazgo("aviso", f"el guion comparte frases con {otro_id} ({sim:.0%}); reescribe lo repetido"))

    stats = {
        "palabras": total,
        "minutos_estimados": round(minutos, 1),
        "escenas": len(g.escenas),
        "capitulos": len(capitulos) + (0 if g.escenas[0].capitulo else 1),
        "visuales": len(visuales),
        "shorts": len(g.shorts),
    }
    return h, stats


def anteriores(carpeta: Path) -> dict[str, str]:
    """Narraciones de los guiones ya existentes, para detectar repeticiones."""
    res = {}
    for p in sorted(Path(carpeta).glob("*.json")):
        try:
            datos = json.loads(p.read_text(encoding="utf-8"))
            res[datos["id"]] = " ".join(e["narracion"] for e in datos.get("escenas", []))
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    return res
