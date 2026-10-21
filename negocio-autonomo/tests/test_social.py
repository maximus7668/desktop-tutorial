"""Conector de LinkedIn con una API simulada: nada se publica de verdad en estas pruebas."""
import json

import pytest

from app import settings_store
from app.actors import PermissionDenied, agent
from app.agents import content
from app.integrations import IntegrationError, IntegrationNotConfigured, social
from app.redact import redact

from .test_content import _published_product


class FakeLinkedIn:
    def __init__(self, post_status=201, userinfo_status=200):
        self.calls = []
        self.post_status, self.userinfo_status = post_status, userinfo_status

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, json.loads(body) if body else None))
        if url.endswith("/v2/userinfo"):
            return self.userinfo_status, {}, json.dumps({"sub": "abc123", "name": "Alejandro"}).encode()
        if url.endswith("/rest/posts"):
            if self.post_status == 201:
                return 201, {"x-restli-id": "urn:li:share:999"}, b""
            return self.post_status, {}, json.dumps({"message": "Not enough permissions"}).encode()
        return 404, {}, b""


@pytest.fixture
def ready(conn, owner, settings, monkeypatch):
    monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "AQX-token-de-prueba-muy-largo-123456")
    settings.public_base_url = "https://ejemplo.trycloudflare.com"
    _published_product(conn, owner, settings)
    did = conn.execute("SELECT id FROM content_drafts WHERE channel='linkedin'").fetchone()["id"]
    content.decide(conn, owner, did, "approved")
    return did


def test_escape_little_keeps_hashtags_and_escapes_reserved():
    s = social.escape_little("Hola (beta) #pymes en web_app: precio 15€ *ya* ~ok~ a@b [x] {y} <z> | \\ #1")
    assert "#pymes" in s and "\\(beta\\)" in s and "web\\_app" in s and "\\*ya\\*" in s
    assert "a\\@b" in s and "\\[x\\]" in s and "\\{y\\}" in s and "\\<z\\>" in s and "\\|" in s and "\\\\" in s
    assert "#1" in s  # hashtag con número también vale


def test_publish_approved_draft(conn, owner, settings, ready):
    fake = FakeLinkedIn()
    res = social.publish_draft(conn, owner, settings, ready, http=fake)
    assert res["url"] == "https://www.linkedin.com/feed/update/urn:li:share:999/"
    post = [c for c in fake.calls if c[1].endswith("/rest/posts")][0]
    assert post[2]["X-Restli-Protocol-Version"] == "2.0.0" and post[2]["Linkedin-Version"].isdigit()
    assert post[3]["author"] == "urn:li:person:abc123" and post[3]["visibility"] == "PUBLIC"
    assert "https://ejemplo.trycloudflare.com/p/" in post[3]["commentary"]
    row = conn.execute("SELECT * FROM content_drafts WHERE id=?", (ready,)).fetchone()
    assert row["status"] == "published" and row["published_via"] == "api:linkedin" and row["external_id"] == "urn:li:share:999"


def test_only_humans_and_only_approved(conn, owner, settings, ready):
    with pytest.raises(PermissionDenied):
        social.publish_draft(conn, agent("contenido"), settings, ready, http=FakeLinkedIn())
    other = conn.execute("SELECT id FROM content_drafts WHERE channel='x'").fetchone()["id"]
    with pytest.raises(ValueError):  # sin aprobar, y además X no tiene conector
        social.publish_draft(conn, owner, settings, other, http=FakeLinkedIn())


def test_kill_switch_and_daily_limit(conn, owner, settings, ready):
    settings_store.activate_kill_switch(conn, owner, "prueba")
    with pytest.raises(PermissionError):
        social.publish_draft(conn, owner, settings, ready, http=FakeLinkedIn())
    settings_store.release_kill_switch(conn, owner)
    settings_store.set_value(conn, owner, "social_daily_limit", "0")
    with pytest.raises(PermissionError, match="límite"):
        social.publish_draft(conn, owner, settings, ready, http=FakeLinkedIn())


def test_local_link_is_refused(conn, owner, settings, ready):
    settings.public_base_url = "http://localhost:8000"
    with pytest.raises(ValueError, match="PUBLIC_BASE_URL"):
        social.publish_draft(conn, owner, settings, ready, http=FakeLinkedIn())


def test_api_error_is_not_marked_published_and_token_not_leaked(conn, owner, settings, ready):
    with pytest.raises(IntegrationError, match="403"):
        social.publish_draft(conn, owner, settings, ready, http=FakeLinkedIn(post_status=403))
    assert conn.execute("SELECT status FROM content_drafts WHERE id=?", (ready,)).fetchone()["status"] == "approved"
    dump = "".join(r["details"] for r in conn.execute("SELECT details FROM audit_log"))
    assert "AQX-token-de-prueba-muy-largo-123456" not in dump and "social.publish_failed" in \
        "".join(r["action"] for r in conn.execute("SELECT action FROM audit_log"))
    assert redact("Bearer AQX-token-de-prueba-muy-largo-123456").count("AQX") == 0


def test_not_configured_without_token(conn, owner, settings, ready, monkeypatch):
    monkeypatch.delenv("LINKEDIN_ACCESS_TOKEN")
    with pytest.raises(IntegrationNotConfigured):
        social.publish_draft(conn, owner, settings, ready, http=FakeLinkedIn())
