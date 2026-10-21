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


# --------------------------------------------------------------------------- Instagram

class FakeInstagram:
    def __init__(self, publish_status=200, container_states=("FINISHED",)):
        self.calls, self.n = [], 0
        self.publish_status, self.states = publish_status, list(container_states)

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, json.loads(body) if body else None))
        if "/me?" in url:
            return 200, {}, json.dumps({"user_id": "1789", "username": "minegocio"}).encode()
        if url.endswith("/1789/media"):
            self.n += 1
            return 200, {}, json.dumps({"id": f"c{self.n}"}).encode()
        if "fields=status_code" in url:
            return 200, {}, json.dumps({"status_code": self.states.pop(0) if len(self.states) > 1 else self.states[0]}).encode()
        if url.endswith("/media_publish"):
            if self.publish_status != 200:
                return self.publish_status, {}, json.dumps({"error": {"message": "Application does not have permission"}}).encode()
            return 200, {}, json.dumps({"id": "m42"}).encode()
        if "fields=permalink" in url:
            return 200, {}, json.dumps({"permalink": "https://www.instagram.com/p/ABC/"}).encode()
        return 404, {}, b""


@pytest.fixture
def ig_ready(conn, owner, settings, monkeypatch):
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "IGAA-token-de-prueba-muy-largo-123456")
    settings.public_base_url = "https://ejemplo.trycloudflare.com"
    _published_product(conn, owner, settings)
    did = conn.execute("SELECT id FROM content_drafts WHERE channel='instagram'").fetchone()["id"]
    content.decide(conn, owner, did, "approved")
    return did


def _fake_ig(monkeypatch, fake):
    monkeypatch.setitem(social.PUBLISHERS, "instagram", lambda http=None: social.Instagram(http=fake, sleep=lambda s: None))


def test_parse_carousel_splits_slides_and_caption():
    from app.integrations.slides import parse_carousel
    slides, cap = parse_carousel("1/ Titular\n2/ Qué incluye:\n• uno\n• dos\n\nPie de foto: Hola. Enlace en la bio ({enlace})")
    assert slides == ["Titular", "Qué incluye:\n• uno\n• dos"] and cap == "Hola. Enlace en la bio ({enlace})"
    assert parse_carousel("Texto suelto")[0] == ["Texto suelto"]


def test_slide_is_a_vertical_jpeg():
    from io import BytesIO

    from PIL import Image

    from app.integrations.slides import render_slide
    img = Image.open(BytesIO(render_slide("Guía de 40 instrucciones de IA por sector, en español: ñ á é", 1, 5, "deika.eu")))
    assert img.format == "JPEG" and img.size == (1080, 1350)


def test_instagram_publishes_carousel(conn, owner, settings, ig_ready, monkeypatch):
    fake = FakeInstagram()
    _fake_ig(monkeypatch, fake)
    res = social.publish_draft(conn, owner, settings, ig_ready)
    assert res == {"id": "m42", "url": "https://www.instagram.com/p/ABC/"}
    posts = [c for c in fake.calls if c[0] == "POST"]
    items = [c[3] for c in posts if c[3].get("is_carousel_item")]
    assert len(items) == 5 and items[0]["image_url"] == f"https://ejemplo.trycloudflare.com/media/ig/{ig_ready}/1.jpg"
    carousel = [c[3] for c in posts if c[3].get("media_type") == "CAROUSEL"][0]
    assert carousel["children"] == "c1,c2,c3,c4,c5"
    assert "1/" not in carousel["caption"] and "https://ejemplo.trycloudflare.com/p/" in carousel["caption"]
    assert all(c[2]["Authorization"].startswith("Bearer ") and "access_token" not in c[1] for c in fake.calls)
    row = conn.execute("SELECT * FROM content_drafts WHERE id=?", (ig_ready,)).fetchone()
    assert row["status"] == "published" and row["published_via"] == "api:instagram"


def test_instagram_error_keeps_draft_and_hides_token(conn, owner, settings, ig_ready, monkeypatch):
    _fake_ig(monkeypatch, FakeInstagram(publish_status=403))
    with pytest.raises(IntegrationError, match="403"):
        social.publish_draft(conn, owner, settings, ig_ready)
    assert conn.execute("SELECT status FROM content_drafts WHERE id=?", (ig_ready,)).fetchone()["status"] == "approved"
    dump = "".join(r["details"] for r in conn.execute("SELECT details FROM audit_log"))
    assert "IGAA-token-de-prueba-muy-largo-123456" not in dump


def test_instagram_container_error_stops(monkeypatch):
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "IGAA-token")
    ig = social.Instagram(http=FakeInstagram(container_states=("ERROR",)), sleep=lambda s: None)
    with pytest.raises(IntegrationError, match="ERROR"):
        ig.publish("texto", images=["https://x/1.jpg", "https://x/2.jpg"])


def test_slide_route_only_serves_approved_instagram_drafts(conn, owner, settings):
    from fastapi.testclient import TestClient

    from app.web.app import create_app
    _published_product(conn, owner, settings)
    did = conn.execute("SELECT id FROM content_drafts WHERE channel='instagram'").fetchone()["id"]
    other = conn.execute("SELECT id FROM content_drafts WHERE channel='linkedin'").fetchone()["id"]
    client = TestClient(create_app(settings))
    assert client.get(f"/media/ig/{did}/1.jpg").status_code == 404  # aún sin aprobar
    content.decide(conn, owner, did, "approved")
    r = client.get(f"/media/ig/{did}/1.jpg")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert client.get(f"/media/ig/{did}/9.jpg").status_code == 404
    content.decide(conn, owner, other, "approved")
    assert client.get(f"/media/ig/{other}/1.jpg").status_code == 404
