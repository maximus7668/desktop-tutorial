"""Recogida de noticias: RSS de medios y fuentes oficiales, limpieza, agrupación por tema y quita de repetidos.

Solo se guarda lo que dicen los feeds (título, enlace, fecha y entradilla). Nada se da por cierto aquí:
el contraste con varias fuentes lo hace el paso del guion."""
from __future__ import annotations

import html
import re
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

# (medio, url, tipo). «oficial» = la propia empresa u organismo: fuente primaria de sus anuncios.
FEEDS = [
    ("Xataka", "https://www.xataka.com/feedburner.xml", "medio"),
    ("Genbeta", "https://feeds.weblogssl.com/genbeta", "medio"),
    ("El País Tecnología", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/tecnologia/portada", "medio"),
    ("Europa Press Portaltic", "https://www.europapress.es/rss/rss.aspx?ch=00564", "medio"),
    ("20minutos Tecnología", "https://www.20minutos.es/rss/tecnologia/", "medio"),
    ("Hipertextual", "https://hipertextual.com/feed", "medio"),
    ("The Verge IA", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "medio"),
    ("Ars Technica IA", "https://arstechnica.com/ai/feed/", "medio"),
    ("TechCrunch IA", "https://techcrunch.com/category/artificial-intelligence/feed/", "medio"),
    ("MIT Technology Review", "https://www.technologyreview.com/feed/", "medio"),
    ("Wired IA", "https://www.wired.com/feed/tag/ai/latest/rss", "medio"),
    ("OpenAI", "https://openai.com/news/rss.xml", "oficial"),
    ("Google IA", "https://blog.google/technology/ai/rss/", "oficial"),
    ("Hugging Face", "https://huggingface.co/blog/feed.xml", "oficial"),
]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) productora-noticias/1.0"
ATOM = "{http://www.w3.org/2005/Atom}"
STOP = set("para como sobre este esta estos estas desde hasta entre porque pero tiene tienen nuevo nueva nuevos nuevas "
           "with from that this your have will what when their about into more than after over".split())


def domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    parts = host.split(".")
    return ".".join(parts[-3:]) if len(parts) > 2 and parts[-2] in ("co", "com", "org") else ".".join(parts[-2:])


def _text(s: str | None, limit: int = 600) -> str:
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()[:limit]


def _date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def parse(xml: bytes, medio: str, tipo: str, per_feed: int = 30) -> list[dict]:
    root = ET.fromstring(xml)
    out = []
    for it in root.iter("item"):
        out.append({"titulo": _text(it.findtext("title"), 300), "url": (it.findtext("link") or "").strip(),
                    "fecha": _date(it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date")),
                    "resumen": _text(it.findtext("description"))})
    for e in root.iter(f"{ATOM}entry"):
        link = next((l.get("href") for l in e.findall(f"{ATOM}link") if l.get("rel", "alternate") == "alternate"), "")
        out.append({"titulo": _text(e.findtext(f"{ATOM}title"), 300), "url": (link or "").strip(),
                    "fecha": _date(e.findtext(f"{ATOM}published") or e.findtext(f"{ATOM}updated")),
                    "resumen": _text(e.findtext(f"{ATOM}summary") or e.findtext(f"{ATOM}content"))})
    out = [x for x in out if x["titulo"] and x["url"].startswith("http") and x["fecha"]]
    out.sort(key=lambda x: x["fecha"], reverse=True)
    for x in out:
        x.update(medio=medio, tipo=tipo, dominio=domain(x["url"]))
    return out[:per_feed]


def fetch_all(feeds=FEEDS, timeout: int = 20) -> tuple[list[dict], list[str]]:
    items, errors = [], []
    for medio, url, tipo in feeds:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                items += parse(r.read(5_000_000), medio, tipo)
        except Exception as e:  # un feed caído no para el día
            errors.append(f"{medio}: {type(e).__name__}: {str(e)[:120]}")
    return items, errors


def tokens(title: str) -> set[str]:
    t = unicodedata.normalize("NFKD", title.lower()).encode("ascii", "ignore").decode()
    return {w for w in re.findall(r"[a-z0-9]{4,}", t) if w not in STOP}


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def candidates(items: list[dict], seen: list[set[str]], hours: int = 36, top: int = 8) -> list[dict]:
    """Agrupa noticias del mismo tema (títulos parecidos), descarta temas ya contados y ordena por
    número de medios independientes y por lo recientes que son."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    fresh = [dict(x, tokens=tokens(x["titulo"])) for x in items if x["fecha"] >= since]
    groups: list[dict] = []
    for x in fresh:
        g = next((g for g in groups if _jaccard(g["tokens"], x["tokens"]) >= 0.34), None)
        if g:
            g["noticias"].append(x)
            g["tokens"] |= x["tokens"]
        else:
            groups.append({"tokens": set(x["tokens"]), "noticias": [x]})
    out = []
    for g in groups:
        if any(_jaccard(g["tokens"], s) >= 0.5 for s in seen):
            continue
        doms = {n["dominio"] for n in g["noticias"]}
        newest = max(n["fecha"] for n in g["noticias"])
        age_h = (datetime.now(timezone.utc) - newest).total_seconds() / 3600
        score = len(doms) * 2 + (1 if any(n["tipo"] == "oficial" for n in g["noticias"]) else 0) + max(0.0, 2 - age_h / 12)
        out.append({"puntuacion": round(score, 2), "medios": sorted(doms), "tokens": sorted(g["tokens"]),
                    "noticias": [{k: (v.isoformat() if k == "fecha" else v) for k, v in n.items() if k != "tokens"}
                                 for n in g["noticias"][:6]]})
    out.sort(key=lambda c: c["puntuacion"], reverse=True)
    return out[:top]
