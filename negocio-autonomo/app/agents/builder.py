"""Agente constructor: genera la página de prueba de un experimento, la valida técnicamente y
pide aprobación para publicarla. El contenido procede de datos (posiblemente externos), así que
se renderiza con autoescape: nunca se inyecta HTML de terceros."""
from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .. import approvals, audit, compliance, permissions, settings_store, validation
from ..actors import Actor
from ..config import Settings
from ..db import now_iso, one, transaction
from ..untrusted import clean

AGENT = "constructor"
_TEMPLATES = Path(__file__).resolve().parent.parent / "web" / "templates" / "public"
_env = Environment(loader=FileSystemLoader(_TEMPLATES), autoescape=select_autoescape(["html"]))


def slugify(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:60] or "producto"


def consent_text(settings: Settings) -> str:
    owner = settings.owner_legal_name or "[TITULAR SIN CONFIGURAR]"
    return (f"Acepto que {owner} trate mi email solo para avisarme del lanzamiento de este producto. "
            "Puedo darme de baja en cualquier momento.")


def render(conn: sqlite3.Connection, settings: Settings, product: dict) -> str:
    c = json.loads(product["content"])
    commerce = settings_store.is_on(conn, "commerce_authorized") and bool(product["payment_link"])
    price = product["price_cents"]
    ctx = {
        **c,
        "price_text": f"{price / 100:.2f} €".replace(".", ",") if price else "Precio por confirmar",
        "commerce": commerce,
        "checkout_path": f"/p/{product['slug']}/checkout",
        "signup_path": f"/p/{product['slug']}/signup",
        "inquiry_path": f"/p/{product['slug']}/inquiry",
        "consent_text": consent_text(settings),
        "owner_name": settings.owner_legal_name or "[Titular sin configurar]",
        "is_test": not settings.is_production,
    }
    return _env.get_template("landing.html").render(c=ctx)


def technical_checks(html: str, settings: Settings) -> dict:
    checks = {
        "titulo": bool(re.search(r"<title>[^<]{3,}</title>", html)),
        "encabezado_h1": "<h1>" in html,
        "precio_con_iva": "IVA incluido" in html,
        "enlace_privacidad": 'href="/legal/privacidad"' in html,
        "enlace_aviso_legal": 'href="/legal/aviso-legal"' in html,
        "llamada_a_la_accion": ("<form" in html) or ("/checkout" in html),
        "consentimiento_obligatorio": ("required" in html and 'name="consent"' in html) or "/checkout" in html,
        "sin_plantilla_sin_rellenar": "{{" not in html and "{%" not in html,
        "sin_scripts": "<script" not in html.lower(),
        "tamano_razonable": len(html.encode()) < 200_000,
        "titular_configurado": bool(settings.owner_legal_name and settings.owner_contact_email),
    }
    return {"ok": all(checks.values()), "checks": checks}


def build_for_experiment(conn: sqlite3.Connection, actor: Actor, settings: Settings, experiment_id: int) -> dict:
    permissions.authorize(conn, actor, "product", "build", f"experiment:{experiment_id}")
    exp = one(conn, "SELECT * FROM experiments WHERE id=?", (experiment_id,))
    if exp is None or exp["status"] not in ("approved", "running"):
        raise ValueError("el experimento no está aprobado")
    existing = one(conn, "SELECT * FROM products WHERE experiment_id=?", (experiment_id,))
    if existing and existing["status"] not in ("draft", "failed_checks"):
        return existing
    if existing:  # repetir las comprobaciones (p. ej. tras configurar los datos del titular)
        return _check_and_request(conn, actor, settings, existing["id"])
    opp = one(conn, "SELECT * FROM opportunities WHERE id=?", (exp["opportunity_id"],))
    # Solo texto pensado para el público: la descripción de la oportunidad es análisis interno y no se publica.
    benefits = json.loads(opp["inputs"]).get("benefits") or []
    content = {
        "name": clean(opp["title"], 120),
        "segment": clean(opp["segment"] or "", 120),
        "headline": clean(opp["product_idea"], 200),
        "description": clean(benefits[0], 400) if benefits else "",
        "bullets": [clean(b, 200) for b in benefits[1:5]],
        "data_kind": "estimate",
    }
    slug = slugify(opp["title"])
    if conn.execute("SELECT 1 FROM products WHERE slug=?", (slug,)).fetchone():
        slug = f"{slug}-{experiment_id}"
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO products (experiment_id, name, slug, price_cents, content, created_by, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (experiment_id, content["name"], slug, opp["price_hint_cents"], json.dumps(content, ensure_ascii=False),
             actor.label, now_iso()),
        )
        pid = cur.lastrowid
    return _check_and_request(conn, actor, settings, pid)


def _check_and_request(conn: sqlite3.Connection, actor: Actor, settings: Settings, pid: int) -> dict:
    product = one(conn, "SELECT * FROM products WHERE id=?", (pid,))
    html = render(conn, settings, product)
    result = technical_checks(html, settings)
    with transaction(conn):
        conn.execute("UPDATE products SET html=?, checks=?, status=? WHERE id=?",
                     (html, json.dumps(result), "tested" if result["ok"] else "failed_checks", pid))
        audit.log(conn, actor, "product.build", f"product:{pid}", result)
    if result["ok"]:
        request_publish(conn, actor, pid)
    return one(conn, "SELECT * FROM products WHERE id=?", (pid,))


def request_publish(conn: sqlite3.Connection, actor: Actor, product_id: int) -> str:
    d = permissions.check(conn, actor, "product", "publish")
    p = one(conn, "SELECT * FROM products WHERE id=?", (product_id,))
    if d.needs_approval:
        approvals.request(conn, actor, "product.publish", f"Publicar «{p['name']}» en /p/{p['slug']}",
                          "products", product_id)
        return "pending_approval"
    if d.allowed:
        permissions.authorize(conn, actor, "product", "publish", f"product:{product_id}")
        with transaction(conn):
            _publish(conn, actor, product_id)
        return "published"
    audit.log(conn, actor, "blocked", "product.publish", {"reason": d.reason})
    return "blocked"


def _publish(conn: sqlite3.Connection, actor: Actor, product_id: int) -> None:
    p = one(conn, "SELECT * FROM products WHERE id=?", (product_id,))
    if p["status"] != "tested":
        raise ValueError("solo se publican productos que han pasado las comprobaciones")
    if settings_store.is_on(conn, "kill_switch"):
        raise PermissionError("parada de emergencia activa")
    missing = compliance.missing_for(conn, "publish")
    if missing:
        raise PermissionError("Antes de publicar confirma: " + ", ".join(missing))
    conn.execute("UPDATE products SET status='published', published_at=? WHERE id=?", (now_iso(), product_id))
    if p["experiment_id"]:
        validation.start(conn, p["experiment_id"])
    audit.log(conn, actor, "product.publish", f"product:{product_id}")
    from .. import tasks  # importación local: evita ciclo de importaciones
    tasks.enqueue(conn, "content.drafts", "contenido", {"product_id": product_id}, f"content:auto:{product_id}")


def _on_publish_decision(conn: sqlite3.Connection, actor: Actor, ap: dict, approve: bool) -> None:
    if approve:
        _publish(conn, actor, ap["ref_id"])


approvals.ON_DECIDE["product.publish"] = _on_publish_decision


def set_payment_link(conn: sqlite3.Connection, actor: Actor, product_id: int, link: str) -> None:
    """El propietario asigna el Payment Link que creó en Stripe (acción humana)."""
    from ..actors import require_human
    from ..integrations.payments import checkout_url

    require_human(actor, "asignar enlace de pago")
    checkout_url(link, product_id)  # valida el formato
    with transaction(conn):
        conn.execute("UPDATE products SET payment_link=? WHERE id=?", (link, product_id))
        audit.log(conn, actor, "product.payment_link", f"product:{product_id}")
