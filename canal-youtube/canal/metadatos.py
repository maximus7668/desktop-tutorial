"""Título, descripción con capítulos, fuentes y créditos, etiquetas: todo listo para subir."""
from __future__ import annotations

import json
from pathlib import Path

from .guion import Guion

LIMITE_DESCRIPCION = 4900


def marca_tiempo(s: float) -> str:
    s = int(s)
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def capitulos(g: Guion, tramos: list[tuple[float, float]]) -> list[tuple[float, str]]:
    caps = [(tramos[i][0], e.capitulo) for i, e in enumerate(g.escenas) if e.capitulo]
    if not caps or caps[0][0] > 0.5:
        caps.insert(0, (0.0, "Introducción"))
    return [(0.0 if i == 0 else t, c) for i, (t, c) in enumerate(caps)]


def _url_corta(r) -> str:
    if r.fuente == "wikimedia" and r.id.startswith("wikimedia-"):
        return f"https://commons.wikimedia.org/?curid={r.id[len('wikimedia-'):]}"
    return r.url


def _creditos(recursos) -> tuple[list[str], set[str]]:
    lineas, fuentes, vistos = [], set(), set()
    for r in recursos:
        if r.generado or r.id in vistos:
            continue
        vistos.add(r.id)
        fuentes.add({"wikimedia": "Wikimedia Commons", "pexels": "Pexels (https://www.pexels.com)",
                     "pixabay": "Pixabay (https://pixabay.com)",
                     "ia": "imágenes generadas con IA", "propio": "material propio",
                     "Natural Earth": "mapas de Natural Earth"}.get(r.fuente, r.fuente))
        if r.atribucion:
            autor = (r.autor or "autor desconocido").strip()
            autor = autor if len(autor) <= 48 else autor[:46].rstrip() + "…"
            lineas.append(f"• {autor} · {r.licencia} · {_url_corta(r)}")
    return lineas, fuentes


def descripcion_largo(g: Guion, caps: list[tuple[float, str]], recursos) -> str:
    """Texto, capítulos, fuentes, aviso de IA y créditos. Los créditos con atribución son
    obligatorios (CC BY / BY-SA): si no cabe todo, se acortan las fuentes, nunca los créditos."""
    creditos, origenes = _creditos(recursos)
    cabeza = [g.descripcion.strip(), ""]
    if len(caps) >= 3:
        cabeza += ["📌 Capítulos"] + [f"{marca_tiempo(t)} {c}" for t, c in caps] + [""]
    pie = ["🎙️ Narración con voz sintética (IA). Guion documentado: fuentes arriba."]
    if origenes:
        pie.append("🖼️ Imágenes: " + ", ".join(sorted(origenes)) + ".")
    if creditos:
        pie += ["Créditos con atribución:"] + creditos
    if g.hashtags:
        pie += ["", " ".join(h if h.startswith("#") else f"#{h}" for h in g.hashtags)]

    def montar(fuentes: list[str]) -> str:
        bloque = (["📚 Fuentes"] + fuentes + [""]) if fuentes else []
        return "\n".join(cabeza + bloque + pie).strip()

    completas = [f"• {f.titulo} — {f.url}" for f in g.fuentes]
    texto = montar(completas)
    if len(texto) > LIMITE_DESCRIPCION:  # 1) títulos de fuente más cortos
        cortas = [f"• {f.titulo if len(f.titulo) <= 60 else f.titulo[:58].rstrip() + '…'} — {f.url}" for f in g.fuentes]
        texto = montar(cortas)
        n = len(cortas)
        while len(texto) > LIMITE_DESCRIPCION and n > 0:  # 2) menos fuentes (las demás, en el guion)
            n -= 1
            resto = len(cortas) - n
            texto = montar(cortas[:n] + [f"• … y {resto} fuente{'s' if resto > 1 else ''} más"])
    if len(texto) > LIMITE_DESCRIPCION:  # 3) último recurso
        texto = texto[:LIMITE_DESCRIPCION].rsplit("\n", 1)[0] + "\n…"
    return texto


def descripcion_short(g: Guion, s) -> str:
    partes = [s.descripcion.strip() or g.descripcion.split("\n")[0], "",
              "▶️ Historia completa en el canal.", "🎙️ Narración con voz sintética (IA)."]
    if g.hashtags:
        partes += ["", " ".join(h if h.startswith("#") else f"#{h}" for h in g.hashtags[:3])]
    return "\n".join(partes).strip()


def escribir(g: Guion, cfg: dict, carpeta: Path, piezas, voz: str) -> dict:
    yt = cfg["youtube"]
    largo = next((p for p in piezas if p.tipo == "largo"), None)
    meta_previa = {}
    ruta = carpeta / "metadatos.json"
    if ruta.exists():
        meta_previa = json.loads(ruta.read_text(encoding="utf-8"))
    meta = {
        "id": g.id,
        "tema": g.tema,
        "voz": voz,
        "categoria": yt["categoria"],
        "idioma": yt["idioma"],
        "hecho_para_ninos": bool(yt["hecho_para_ninos"]),
        "contenido_sintetico_realista": g.sintetico_realista,
        "largo": meta_previa.get("largo"),
        "shorts": meta_previa.get("shorts", {}),
    }
    if largo:
        caps = capitulos(g, largo.tramos)
        meta["largo"] = {
            "archivo": largo.ruta.name,
            "duracion_seg": round(largo.duracion, 1),
            "titulo": g.titulos[0],
            "titulos_alternativos": g.titulos[1:],
            "descripcion": descripcion_largo(g, caps, largo.recursos),
            "etiquetas": g.etiquetas,
            "capitulos": [[marca_tiempo(t), c] for t, c in caps],
            "subtitulos": largo.ruta.with_suffix(".srt").name,
            "miniaturas": sorted(p.name for p in carpeta.glob("miniatura-*.jpg")),
            "creditos": [r.credito() for r in largo.recursos if not r.generado],
            "avisos": largo.avisos,
        }
    for p in piezas:
        if p.tipo != "short":
            continue
        s = next(x for x in g.shorts if x.id == p.ruta.stem)
        meta["shorts"][s.id] = {
            "archivo": p.ruta.name,
            "duracion_seg": round(p.duracion, 1),
            "titulo": s.titulo,
            "descripcion": descripcion_short(g, s),
            "etiquetas": g.etiquetas[:10],
            "subtitulos": p.ruta.with_suffix(".srt").name,
            "creditos": [r.credito() for r in p.recursos if not r.generado],
            "avisos": p.avisos,
        }
    ruta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    if meta["largo"]:
        (carpeta / "descripcion.txt").write_text(meta["largo"]["descripcion"], encoding="utf-8")
    return meta
