"""Qué funciona en la comunidad: vídeos cortos públicos de referentes de cada nicho (TikTok y YouTube Shorts,
leídos con yt-dlp, sin descargar vídeos) y patrones con datos reales: duración, tipo de gancho y longitud del
título frente a visualizaciones. Se copian patrones, nunca contenido: los textos de otros solo se guardan
como referencia interna y no van al guion."""
from __future__ import annotations

import json
import re
import statistics
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# Perfiles de TikTok de referencia por nicho (se pueden ampliar; los que no existan se ignoran)
# y búsquedas de YouTube Shorts para descubrir más.
NICHOS = {
    "ia": {"tiktok": ["javadex", "iafacil.es", "aprende_ia", "techconpaula", "xavier.mitjana", "dotcsv"],
           "youtube": ["noticias inteligencia artificial shorts", "novedades IA esta semana shorts", "chatgpt truco shorts español"]},
    "ciencia": {"tiktok": ["doctorfision", "cuarentaydos", "bigvanciencia", "andyenriquez", "quantumfracture"],
                "youtube": ["noticias espacio shorts español", "curiosidades ciencia shorts español", "NASA noticia shorts español"]},
    "videojuegos": {"tiktok": ["vandal_es", "3djuegos", "ign_es", "eurogamer.es", "hobbyconsolas"],
                    "youtube": ["noticias videojuegos shorts español", "filtración videojuego shorts", "nintendo noticia shorts español"]},
    "ciberseguridad": {"tiktok": ["chemaalonso", "incibe", "policia", "guardiacivil", "osi_es"],
                       "youtube": ["estafa nueva cuidado shorts español", "ciberseguridad consejos shorts español", "phishing whatsapp estafa shorts"]},
}
HOOKS = {
    "pregunta": r"[¿?]",
    "cifra": r"\d",
    "negacion_o_alerta": r"\b(no|nadie|nunca|cuidado|ojo|alerta|peligro|deja de)\b",
    "esto_asi": r"\b(esto|así|este|esta)\b",
    "por_que_como": r"\b(por qué|cómo|como)\b",
    "novedad": r"\b(nuevo|nueva|acaba|ya|lanza|presenta|oficial)\b",
}


def _ytdlp(args: list[str], timeout: int = 240) -> list[dict]:
    try:
        out = subprocess.run(["yt-dlp", "--ignore-errors", "--no-warnings", *args], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=timeout).stdout
    except subprocess.TimeoutExpired:
        return []
    items = []
    for line in out.splitlines():
        if line.startswith("{"):
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return items


def _video(j: dict, plataforma: str, cuenta: str) -> dict | None:
    if not j.get("view_count") or not j.get("duration"):
        return None
    return {"plataforma": plataforma, "cuenta": cuenta, "titulo": (j.get("title") or "")[:200],
            "vistas": int(j["view_count"]), "duracion": int(j["duration"]), "url": j.get("url") or j.get("webpage_url"),
            "me_gusta": j.get("like_count"), "comentarios": j.get("comment_count")}


def recopilar(nicho: str, por_cuenta: int = 30, por_busqueda: int = 25) -> list[dict]:
    cfg, vids = NICHOS[nicho], []
    for h in cfg["tiktok"]:
        for j in _ytdlp(["--flat-playlist", "-I", f"1:{por_cuenta}", "--dump-json", f"https://www.tiktok.com/@{h}"]):
            v = _video(j, "tiktok", h)
            if v:
                vids.append(v)
    for q in cfg["youtube"]:
        for j in _ytdlp(["--flat-playlist", "--dump-json", f"ytsearch{por_busqueda}:{q}"]):
            v = _video(j, "youtube", j.get("channel") or j.get("uploader") or "?")
            if v and v["duracion"] <= 90:  # solo formato corto
                vids.append(v)
    return vids


def patrones(vids: list[dict]) -> dict:
    """Compara el cuarto con más vistas (relativo a su cuenta) con el resto. Usar las vistas relativas a la
    mediana de cada cuenta evita que gane siempre la cuenta más grande."""
    by_acc: dict[str, list[int]] = {}
    for v in vids:
        by_acc.setdefault(f"{v['plataforma']}:{v['cuenta']}", []).append(v["vistas"])
    med = {k: statistics.median(x) for k, x in by_acc.items()}
    for v in vids:
        v["rel"] = v["vistas"] / max(1, med[f"{v['plataforma']}:{v['cuenta']}"])
    vids = sorted(vids, key=lambda v: v["rel"], reverse=True)
    q = max(1, len(vids) // 4)
    top, rest = vids[:q], vids[q:] or vids
    share = lambda group, rx: sum(1 for v in group if re.search(rx, v["titulo"].lower())) / max(1, len(group))  # noqa: E731
    out = {"videos": len(vids), "cuentas": len(by_acc),
           "duracion_mediana_top": statistics.median(v["duracion"] for v in top),
           "duracion_mediana_resto": statistics.median(v["duracion"] for v in rest),
           "longitud_titulo_top": statistics.median(len(v["titulo"]) for v in top),
           "longitud_titulo_resto": statistics.median(len(v["titulo"]) for v in rest),
           "ganchos": {k: {"top": round(share(top, rx), 2), "resto": round(share(rest, rx), 2)} for k, rx in HOOKS.items()}}
    buckets = {"<30 s": (0, 30), "30-60 s": (30, 60), "60-90 s": (60, 90), ">90 s": (90, 10**6)}
    out["vistas_relativas_por_duracion"] = {
        b: round(statistics.median([v["rel"] for v in vids if lo <= v["duracion"] < hi]), 2)
        for b, (lo, hi) in buckets.items() if any(lo <= v["duracion"] < hi for v in vids)}
    out["ejemplos_top"] = [{k: v[k] for k in ("plataforma", "cuenta", "titulo", "vistas", "duracion", "url")} for v in top[:12]]
    return out


def resumen_md(nicho: str, p: dict) -> str:
    g = p["ganchos"]
    mejores = [k for k, x in g.items() if x["top"] >= x["resto"] + 0.08]
    peores = [k for k, x in g.items() if x["resto"] >= x["top"] + 0.08]
    dur = max(p["vistas_relativas_por_duracion"].items(), key=lambda kv: kv[1])[0] if p["vistas_relativas_por_duracion"] else "?"
    return "\n".join([
        f"# Lo que funciona en la comunidad · nicho {nicho}",
        f"Datos reales de {p['videos']} vídeos cortos de {p['cuentas']} cuentas (TikTok y YouTube Shorts), "
        f"{datetime.now(timezone.utc).date().isoformat()}. Patrones, no contenido: no copies titulares ni frases.",
        "",
        f"- Duración con más vistas relativas: {dur} (mediana de los mejores {p['duracion_mediana_top']} s frente a {p['duracion_mediana_resto']} s).",
        f"- Ganchos que aparecen más en los mejores: {', '.join(mejores) or 'ninguno destaca'}.",
        f"- Ganchos que aparecen más en los peores: {', '.join(peores) or 'ninguno destaca'}.",
        "- Detalle por gancho (porcentaje en el top frente al resto): "
        + "; ".join(f"{k} {x['top']:.0%} / {x['resto']:.0%}" for k, x in g.items()),
    ])


def analizar(base: Path, nicho: str) -> dict:
    vids = recopilar(nicho)
    if len(vids) < 20:
        raise RuntimeError(f"pocos datos para {nicho}: {len(vids)} vídeos")
    p = patrones(vids)
    d = base / "referentes"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{nicho}.json").write_text(json.dumps({"fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                                  "patrones": p, "videos": vids}, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
    (d / f"{nicho}.md").write_text(resumen_md(nicho, p), encoding="utf-8")
    return {"nicho": nicho, "videos": p["videos"], "cuentas": p["cuentas"]}
