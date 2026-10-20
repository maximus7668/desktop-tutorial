"""Agente de contenido: borradores honestos con enlace medible; nunca publica; solo personas deciden."""
import json

import pytest
from fastapi.testclient import TestClient

from app import approvals, compliance, settings_store
from app.actors import PermissionDenied, agent
from app.agents import content, director, researcher
from app.integrations.llm import FakeProvider
from app.web import auth
from app.web.app import create_app
from app.worker import run_once

from .fixtures import research_fixture


def _published_product(conn, owner, settings):
    researcher.import_research(conn, agent("investigador"), research_fixture())
    director.cycle(conn, agent("director"))
    approvals.decide(conn, owner, approvals.pending(conn)[0]["id"], True)
    for item in compliance.list_items(conn):
        if item["required_for"] == "publish":
            compliance.confirm(conn, owner, item["key"], "done")
    while run_once(conn, settings, FakeProvider()):  # construye la página
        pending = [a for a in approvals.pending(conn) if a["kind"] == "product.publish"]
        if pending:
            approvals.decide(conn, owner, pending[0]["id"], True)
    return conn.execute("SELECT * FROM products").fetchone()


def test_publishing_triggers_honest_drafts_with_tracked_links(conn, owner, settings):
    p = _published_product(conn, owner, settings)
    drafts = conn.execute("SELECT * FROM content_drafts").fetchall()
    assert {d["channel"] for d in drafts} == set(content.CHANNELS)
    for d in drafts:
        assert d["status"] == "draft" and d["generator"] == "plantilla"
        assert d["link_path"].startswith(f"/p/{p['slug']}?utm_source={d['channel']}")
        assert json.loads(d["checks"])["ok"]
        assert "lista de espera" in d["body"].lower()  # aún no se cobra: lo dice
    assert len(drafts) <= 5 and all(len(d["body"]) <= content.MAX_LEN[d["channel"]] for d in drafts)
    again = content.generate(conn, agent("contenido"), settings, p["id"])
    assert again["created"] == 0  # no amontona borradores sin revisar


def test_only_published_products_get_content(conn, settings):
    pid = conn.execute("INSERT INTO products (name, slug, created_by, created_at) VALUES ('x','x','t','t')").lastrowid
    with pytest.raises(ValueError):
        content.generate(conn, agent("contenido"), settings, pid)


def test_filter_blocks_dishonest_claims():
    bad = "Gana dinero sin esfuerzo, ¡solo hoy! 500 € al mes garantizados {enlace}"
    r = content.check_draft("x", bad, commerce=False)
    assert not r["ok"] and not r["checks"]["sin_promesas_ni_urgencia_falsa"]
    assert not content.check_draft("x", "Muy buen producto, ya a la venta", commerce=False)["checks"]["incluye_enlace"]
    assert not content.check_draft("x", "Mira esto {enlace}", commerce=False)["checks"]["honesto_sobre_estado"]


def test_llm_text_used_only_if_it_passes_filter(conn, owner, settings):
    settings_store.set_value(conn, owner, "api_envelope_month_cents", "1000")
    p = _published_product(conn, owner, settings)
    conn.execute("DELETE FROM content_drafts")
    fake = FakeProvider(lambda s, u: json.dumps({
        "x": {"title": "X", "body": "Lista de espera abierta para la guía → {enlace}"},
        "linkedin": {"title": "L", "body": "Gana dinero sin esfuerzo con esto {enlace}"},
    }))
    out = content.generate(conn, agent("contenido"), settings, p["id"], fake)
    rows = {r["channel"]: r["body"] for r in conn.execute("SELECT channel, body FROM content_drafts")}
    assert out["generator"].startswith("llm:")
    assert rows["x"] == "Lista de espera abierta para la guía → {enlace}"
    assert "sin esfuerzo" not in rows["linkedin"]  # se rechazó la versión IA y se usó la plantilla


def test_only_humans_decide_and_publish_needs_approval(conn, owner, settings):
    _published_product(conn, owner, settings)
    did = conn.execute("SELECT id FROM content_drafts LIMIT 1").fetchone()["id"]
    with pytest.raises(PermissionDenied):
        content.decide(conn, agent("contenido"), did, "approved")
    with pytest.raises(ValueError):
        content.decide(conn, owner, did, "published")
    content.decide(conn, owner, did, "approved")
    content.decide(conn, owner, did, "published", "https://www.tiktok.com/@yo/video/1")
    assert conn.execute("SELECT status FROM content_drafts WHERE id=?", (did,)).fetchone()["status"] == "published"


def test_visits_and_signups_attributed_to_channel(settings, conn, owner):
    p = _published_product(conn, owner, settings)
    auth.create_user(conn, "propietario", "una-contraseña-larga-de-prueba")
    c = TestClient(create_app(settings))
    page = f"http://testserver/p/{p['slug']}?utm_source=tiktok&utm_medium=social"
    for i in range(3):
        c.get(f"/p/{p['slug']}?utm_source=tiktok", headers={"user-agent": f"Mozilla/5.0 v{i}"})
    c.post(f"/p/{p['slug']}/signup", data={"email": "a@example.com", "consent": "yes"},
           headers={"user-agent": "Mozilla/5.0 v0", "referer": page})
    c.get(f"/p/{p['slug']}", headers={"user-agent": "Mozilla/5.0 otro", "referer": "https://www.instagram.com/"})
    by = {r["canal"]: r for r in content.visits_by_channel(conn, "simulation")}
    assert by["tiktok"]["visitantes"] == 3 and by["tiktok"]["registros"] == 1
    assert by["www.instagram.com"]["visitantes"] == 1
    c.post("/login", data={"username": "propietario", "password": "una-contraseña-larga-de-prueba"})
    html = c.get("/contenido").text
    assert "utm_source=tiktok" in html and "Visitas por canal" in html


def test_lowercasing_keeps_proper_nouns():
    assert content._lc("Pequeños negocios locales en España") == "pequeños negocios locales en España"
    assert content._lc("Guía de IA") == "guía de IA" and content._lc("IA para pymes") == "IA para pymes"
