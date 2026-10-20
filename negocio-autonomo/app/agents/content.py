"""Agente de contenido: redacta borradores para redes sociales que lleven visitas a una página publicada.

Reglas:
- Nunca publica. Una persona aprueba, publica a mano y lo marca como publicado.
- Cada borrador lleva un enlace con utm_source=<canal> para saber qué canal trae visitas reales.
- Filtro de honestidad: sin promesas de ingresos, urgencia falsa, testimonios inventados ni cifras sin fuente;
  si aún no se cobra, lo dice ("lista de espera").
- No genera mensajes privados en frío ni emails comerciales (LSSI art. 21): solo publicaciones propias
  y mensajes para grupos donde el propietario ya participa.
- Con 0 € usa plantillas; con modelo configurado y presupuesto, puede redactar con IA y pasa el mismo filtro."""
from __future__ import annotations

import json
import re
import secrets
import sqlite3

from .. import audit, permissions, settings_store
from ..actors import Actor, require_human
from ..budget import BudgetError
from ..config import Settings
from ..db import now_iso, one, rows, transaction
from ..integrations import IntegrationError, IntegrationNotConfigured
from ..integrations.llm import LLMProvider, guarded_complete
from ..untrusted import clean, looks_like_injection

AGENT = "contenido"
CHANNELS = ("tiktok", "instagram", "x", "linkedin", "grupo")
MAX_LEN = {"tiktok": 1500, "instagram": 2200, "x": 280, "linkedin": 3000, "grupo": 700}

# Frases que no se permiten en ningún borrador (minúsculas, sin tildes en la comparación).
FORBIDDEN = [
    r"gana(r|s)? dinero", r"ingresos? pasivos?", r"hazte rico", r"garantizad", r"\b100 ?% seguro",
    r"sin esfuerzo", r"ultimas? (plazas|unidades)", r"solo hoy", r"oferta por tiempo limitado",
    r"miles de (clientes|personas) (ya )?(lo )?(usan|confian)", r"testimonio", r"\d+ ?(€|euros?) al (dia|mes)",
    r"precio (sube|subira) (manana|pronto)",
]


def _norm(s: str) -> str:
    return (s.lower().replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o")
            .replace("ú", "u").replace("ü", "u"))


def link_path(product: dict, channel: str) -> str:
    return f"/p/{product['slug']}?utm_source={channel}&utm_medium=social&utm_campaign=exp{product['experiment_id'] or 0}"


def check_draft(channel: str, body: str, commerce: bool) -> dict:
    n = _norm(body)
    checks = {
        "sin_promesas_ni_urgencia_falsa": not any(re.search(p, n) for p in FORBIDDEN),
        "longitud_canal": len(body) <= MAX_LEN[channel],
        "incluye_enlace": "{enlace}" in body,
        "honesto_sobre_estado": commerce or any(w in n for w in ("lista de espera", "en preparacion", "aun no", "todavia no")),
        "sin_instrucciones_raras": not looks_like_injection(body),
    }
    return {"ok": all(checks.values()), "checks": checks}


def _lc(s: str) -> str:
    """Primera letra en minúscula sin tocar nombres propios ni siglas (España, IA)."""
    return s[:1].lower() + s[1:] if s[:2] != s[:2].upper() else s


def _templates(p: dict, c: dict, price: str, commerce: bool) -> dict[str, tuple[str, str]]:
    name, headline, seg = c["name"], c["headline"], c.get("segment") or "pequeños negocios"
    benefits = [b for b in [c.get("description", "")] + c.get("bullets", []) if b][:3]
    bl = "\n".join(f"• {b}" for b in benefits) or f"• {headline}"
    estado = ("Ya disponible." if commerce else
              "Aún no está a la venta: estoy midiendo si interesa. Si te interesa, apúntate a la lista de espera y te aviso.")
    cta = "Más info y compra:" if commerce else "Lista de espera (gratis, sin compromiso):"
    return {
        "tiktok": (
            f"Guion TikTok/Reels (30-45 s): {name}",
            f"[0-3 s · gancho, a cámara] ¿Trabajas en {_lc(seg)} y te preguntas cómo usar mejor tu tiempo?\n"
            f"[3-15 s · problema] Cuéntalo con un caso tuyo y real, sin exagerar.\n"
            f"[15-30 s · propuesta] Estoy preparando esto: {headline}.\n{bl}\n"
            f"[30-40 s · estado] Precio previsto {price}. {estado}\n"
            f"[Cierre] El enlace está en mi perfil.\n\n"
            f"Texto del post: {headline}. {estado} {cta} {{enlace}}\n"
            f"#pymes #emprender #productividad"),
        "instagram": (
            f"Carrusel Instagram (5 diapositivas): {name}",
            f"1/ {headline}\n2/ Para quién: {seg}\n3/ Qué incluye:\n{bl}\n"
            f"4/ Precio previsto: {price} (IVA incluido)\n5/ {estado}\n\n"
            f"Pie de foto: {headline}. {estado} {cta} enlace en la bio ({{enlace}})"),
        "x": (
            f"Publicación X: {name}",
            f"{headline}. Precio previsto {price}. "
            f"{'Ya disponible' if commerce else 'Aún en preparación: lista de espera'} → {{enlace}}"),
        "linkedin": (
            f"Publicación LinkedIn: {name}",
            f"Estoy validando una idea antes de construirla del todo: {headline}.\n\n"
            f"Pensada para {_lc(seg)}:\n{bl}\n\n"
            f"Precio previsto: {price} (IVA incluido). {estado}\n\n"
            f"Si te interesa o tienes una opinión sincera sobre si lo pagarías, me ayuda mucho: {{enlace}}"),
        "grupo": (
            f"Mensaje para un grupo donde ya participas: {name}",
            f"Hola a todos. Estoy preparando algo para {_lc(seg)}: {headline}. "
            f"Precio previsto {price}. {estado} Por si a alguien le sirve: {{enlace}}\n"
            f"(Si las normas del grupo no permiten promoción, no lo publiques.)"),
    }


LLM_SYSTEM = """Redactas publicaciones honestas para redes sociales en español de España para una página de producto.
Prohibido: prometer ingresos o resultados, urgencia falsa, testimonios o cifras inventadas, mensajes privados en frío.
Si el producto aún no se vende, dilo claramente ("lista de espera"). Escribe {enlace} donde vaya el enlace.
Responde SOLO con JSON: {"tiktok": {"title": "...", "body": "..."}, "instagram": {...}, "x": {...}, "linkedin": {...}, "grupo": {...}}"""


def generate(conn: sqlite3.Connection, actor: Actor, settings: Settings, product_id: int,
             provider: LLMProvider | None = None) -> dict:
    permissions.authorize(conn, actor, "content", "draft", f"product:{product_id}")
    p = one(conn, "SELECT * FROM products WHERE id=?", (product_id,))
    if p is None or p["status"] != "published":
        raise ValueError("solo se preparan contenidos para productos publicados")
    existing = conn.execute("SELECT COUNT(*) c FROM content_drafts WHERE product_id=? AND status IN ('draft','approved')",
                            (product_id,)).fetchone()["c"]
    if existing:
        return {"created": 0, "reason": "ya hay borradores pendientes de revisar"}
    c = json.loads(p["content"])
    commerce = settings_store.is_on(conn, "commerce_authorized") and bool(p["payment_link"])
    price = f"{p['price_cents'] / 100:.2f} €".replace(".", ",") if p["price_cents"] else "por confirmar"
    drafts = {ch: (t, b) for ch, (t, b) in _templates(p, c, price, commerce).items()}
    generator = "plantilla"
    if provider is not None and provider.info().configured:
        try:
            user = json.dumps({"producto": c["name"], "titular": c["headline"], "para": c.get("segment"),
                               "ventajas": [c.get("description")] + c.get("bullets", []), "precio": price,
                               "a_la_venta": commerce}, ensure_ascii=False)
            res = guarded_complete(conn, actor, provider, settings, LLM_SYSTEM, user, 4000, f"content:{product_id}:{secrets.token_hex(6)}")
            data = json.loads(re.search(r"\{.*\}", res.text, re.S).group(0))
            llm = {ch: (clean(data[ch]["title"], 200), str(data[ch]["body"])[:MAX_LEN[ch] + 200]) for ch in CHANNELS if ch in data}
            for ch, (t, b) in llm.items():
                if check_draft(ch, b, commerce)["ok"]:  # solo se usa la versión IA si pasa el filtro
                    drafts[ch] = (t, b)
            generator = f"llm:{res.model}+plantilla"
        except (IntegrationNotConfigured, IntegrationError, BudgetError, permissions.ActionBlocked,
                ValueError, KeyError, TypeError, AttributeError, json.JSONDecodeError) as e:
            audit.log(conn, actor, "content.llm_fallback", f"product:{product_id}", {"error": f"{type(e).__name__}: {e}"[:300]})
    created = []
    with transaction(conn):
        for ch in CHANNELS:
            title, body = drafts[ch]
            result = check_draft(ch, body, commerce)
            if not result["ok"]:
                audit.log(conn, actor, "content.discarded", f"product:{product_id}", {"channel": ch, **result})
                continue
            cur = conn.execute(
                "INSERT INTO content_drafts (product_id, channel, title, body, link_path, generator, checks, created_by,"
                " created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (product_id, ch, title, body, link_path(p, ch), generator, json.dumps(result), actor.label, now_iso()))
            created.append(cur.lastrowid)
        audit.log(conn, actor, "content.draft", f"product:{product_id}", {"drafts": created, "generator": generator})
    return {"created": len(created), "ids": created, "generator": generator}


def render_body(draft: dict, base_url: str) -> str:
    return draft["body"].replace("{enlace}", base_url.rstrip("/") + draft["link_path"])


def decide(conn: sqlite3.Connection, actor: Actor, draft_id: int, status: str, published_url: str = "") -> None:
    """approved | rejected | published. Solo personas: el sistema no publica en redes."""
    require_human(actor, "revisar contenido")
    if status not in ("approved", "rejected", "published"):
        raise ValueError(status)
    with transaction(conn):
        d = one(conn, "SELECT * FROM content_drafts WHERE id=?", (draft_id,))
        if d is None:
            raise KeyError(draft_id)
        if status == "published" and d["status"] != "approved":
            raise ValueError("primero aprueba el borrador")
        conn.execute("UPDATE content_drafts SET status=?, decided_by=?, decided_at=?, published_url=COALESCE(NULLIF(?, ''), published_url),"
                     " published_at=CASE WHEN ?='published' THEN ? ELSE published_at END WHERE id=?",
                     (status, actor.label, now_iso(), clean(published_url, 500), status, now_iso(), draft_id))
        audit.log(conn, actor, f"content.{status}", f"draft:{draft_id}", {"channel": d["channel"]})


def visits_by_channel(conn: sqlite3.Connection, data_kind: str) -> list[dict]:
    """Visitantes únicos y registros por canal (utm_source) y producto."""
    return rows(conn,
                "SELECT p.name AS producto, COALESCE(NULLIF(e.source,''),'directo/otros') AS canal,"
                " COUNT(DISTINCT CASE WHEN e.type='visit' THEN e.visitor_hash END) AS visitantes,"
                " SUM(CASE WHEN e.type='signup' THEN 1 ELSE 0 END) AS registros"
                " FROM events e JOIN products p ON p.id=e.product_id WHERE e.data_kind=?"
                " GROUP BY p.name, canal ORDER BY visitantes DESC", (data_kind,))
