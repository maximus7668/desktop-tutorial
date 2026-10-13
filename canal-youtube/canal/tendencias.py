"""Vídeos atípicos: los que tienen muchas más vistas de lo que su canal suele conseguir.

Son la mejor pista de un tema con demanda. Usa una clave de API de YouTube (YOUTUBE_API_KEY);
search.list tiene su propio cupo de 100 llamadas al día.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

from .config import MEMORIA, clave

API = "https://www.googleapis.com/youtube/v3"


def _get(recurso: str, **params) -> dict:
    r = requests.get(f"{API}/{recurso}", params={"key": clave("YOUTUBE_API_KEY"), **params}, timeout=60)
    if r.status_code >= 400:
        raise SystemExit(f"YouTube API {recurso}: {r.status_code} {r.text[:300]}")
    return r.json()


def _duracion(iso: str) -> int:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def buscar(terminos: list[str], dias: int = 60, region: str | None = None, minimo_seg: int = 240) -> list[dict]:
    desde = (datetime.now(timezone.utc) - timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ids: list[str] = []
    for t in terminos:
        params = dict(part="snippet", q=t, type="video", order="viewCount", publishedAfter=desde,
                      relevanceLanguage="es", maxResults=50, safeSearch="none")
        if region:
            params["regionCode"] = region
        ids += [i["id"]["videoId"] for i in _get("search", **params).get("items", [])]
    ids = list(dict.fromkeys(ids))
    videos = []
    for i in range(0, len(ids), 50):
        videos += _get("videos", part="snippet,statistics,contentDetails", id=",".join(ids[i:i + 50])).get("items", [])
    canales = {}
    cids = list({v["snippet"]["channelId"] for v in videos})
    for i in range(0, len(cids), 50):
        for c in _get("channels", part="statistics,snippet", id=",".join(cids[i:i + 50])).get("items", []):
            canales[c["id"]] = c
    hoy = datetime.now(timezone.utc)
    res = []
    for v in videos:
        dur = _duracion(v["contentDetails"].get("duration", ""))
        if dur < minimo_seg:
            continue
        c = canales.get(v["snippet"]["channelId"], {})
        subs = int(c.get("statistics", {}).get("subscriberCount") or 0)
        vistas = int(v["statistics"].get("viewCount") or 0)
        publicado = datetime.fromisoformat(v["snippet"]["publishedAt"].replace("Z", "+00:00"))
        dias_pub = max(1, (hoy - publicado).days)
        res.append({
            "titulo": v["snippet"]["title"], "canal": v["snippet"]["channelTitle"], "suscriptores": subs,
            "vistas": vistas, "dias": dias_pub, "vistas_dia": round(vistas / dias_pub),
            "ratio": round(vistas / max(subs, 1000), 1), "min": round(dur / 60, 1),
            "url": f"https://youtu.be/{v['id']}",
        })
    return sorted(res, key=lambda x: x["ratio"], reverse=True)


def informe(terminos: list[str], dias: int = 60, region: str | None = None, minimo_seg: int = 240) -> Path:
    filas = buscar(terminos, dias, region, minimo_seg)
    carpeta = MEMORIA / "tendencias"
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{date.today().isoformat()}.md"
    lineas = [f"# Vídeos atípicos · {', '.join(terminos)} · últimos {dias} días" + (f" · {region}" if region else ""), "",
              "Ratio = vistas / suscriptores del canal (mínimo 1.000). Más de 3 suele indicar un tema con demanda.", "",
              "| Ratio | Vistas | Subs canal | Días | Min | Título | Canal |", "|---:|---:|---:|---:|---:|---|---|"]
    def n(x: int) -> str:
        return f"{x:,}".replace(",", ".")

    for f in filas[:40]:
        titulo = f["titulo"].replace("|", "/")
        lineas.append(f"| {f['ratio']} | {n(f['vistas'])} | {n(f['suscriptores'])} | {f['dias']} | {f['min']} | "
                      f"[{titulo}]({f['url']}) | {f['canal'].replace('|', '/')} |")
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return ruta
