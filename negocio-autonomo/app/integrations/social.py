"""Publicación en redes sociales con sus API oficiales.

Reglas (todas en el servidor):
- Solo se publican borradores APROBADOS por una persona, y solo cuando una persona pulsa «Publicar».
- Límite diario por red (ajuste social_daily_limit). La parada de emergencia lo bloquea todo.
- Solo publicar: no se leen mensajes privados, no se comenta, no se sigue a nadie.
- El token va en .env (nunca en la BD, el chat ni los logs). Si la red responde con error, el borrador
  sigue aprobado y no se marca como publicado.

LinkedIn (documentación oficial, Microsoft Learn):
- Productos de la app: «Share on LinkedIn» (w_member_social) y «Sign In with LinkedIn using OpenID
  Connect» (openid, profile).
- Identidad: GET https://api.linkedin.com/v2/userinfo → campo "sub" → autor urn:li:person:{sub}.
- Publicar: POST https://api.linkedin.com/rest/posts con cabeceras Linkedin-Version (AAAAMM) y
  X-Restli-Protocol-Version: 2.0.0; el id llega en la cabecera x-restli-id.
- El texto usa el formato «little»: hay que escapar | { } @ [ ] ( ) < > # \\ * _ ~.

Instagram («API de Instagram con inicio de sesión de Instagram», Meta for Developers):
- Cuenta profesional (empresa o creador); no hace falta página de Facebook. Permisos
  instagram_business_basic e instagram_business_content_publish.
- Identidad: GET https://graph.instagram.com/{versión}/me?fields=user_id,username.
- Publicar: un contenedor por imagen (POST /{id}/media con image_url, is_carousel_item), el carrusel
  (media_type=CAROUSEL, children, caption), esperar status_code=FINISHED y POST /{id}/media_publish.
- Instagram descarga las imágenes de una URL pública: las sirve este sistema en /media/ig/{borrador}/{n}.jpg."""
from __future__ import annotations

import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from typing import Callable

from .. import audit, permissions, settings_store
from ..actors import Actor, require_human
from ..config import Settings
from ..db import now_iso, one, transaction
from ..redact import redact
from . import IntegrationError, IntegrationInfo, IntegrationNotConfigured

LINKEDIN_API = "https://api.linkedin.com"
_RESERVED = set("|{}@[]()<>#\\*_~")

# (método, url, cabeceras, cuerpo) -> (estado, cabeceras, cuerpo). Sustituible en pruebas.
HttpFn = Callable[[str, str, dict, bytes | None], tuple[int, dict, bytes]]


def _http(method: str, url: str, headers: dict, body: bytes | None) -> tuple[int, dict, bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, e.read() or b""
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise IntegrationError(f"no se pudo conectar con la red social: {type(e).__name__}") from e


def escape_little(text: str) -> str:
    """Escapa los caracteres reservados del formato «little» de LinkedIn.
    Se respetan los hashtags (#palabra al inicio o tras espacio) para que sigan siendo hashtags."""
    out = []
    for i, ch in enumerate(text):
        if ch == "#" and (i == 0 or text[i - 1].isspace()) and i + 1 < len(text) and (text[i + 1].isalnum()):
            out.append(ch)
        elif ch in _RESERVED:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


class LinkedIn:
    name = "linkedin"

    def __init__(self, http: HttpFn | None = None):
        self.token = os.environ.get("LINKEDIN_ACCESS_TOKEN", "").strip()
        self.version = os.environ.get("LINKEDIN_VERSION", "").strip() or "202610"
        self.expires = os.environ.get("LINKEDIN_TOKEN_EXPIRES", "").strip()
        self.http = http or _http

    def info(self) -> IntegrationInfo:
        return IntegrationInfo(
            "red_linkedin", bool(self.token),
            "publicar en tu perfil (w_member_social) solo borradores aprobados; sin leer mensajes",
            "Crea una app en linkedin.com/developers con «Share on LinkedIn» y «Sign In with LinkedIn using "
            "OpenID Connect», genera un token y ponlo en LINKEDIN_ACCESS_TOKEN (y su caducidad en "
            "LINKEDIN_TOKEN_EXPIRES=AAAA-MM-DD). Guía: docs/REDES.md")

    def days_left(self) -> int | None:
        try:
            return (date.fromisoformat(self.expires) - datetime.now(timezone.utc).date()).days
        except ValueError:
            return None

    def _headers(self, json_body: bool = False) -> dict:
        h = {"Authorization": f"Bearer {self.token}", "X-Restli-Protocol-Version": "2.0.0",
             "Linkedin-Version": self.version}
        if json_body:
            h["Content-Type"] = "application/json"
        return h

    def _error(self, what: str, status: int, body: bytes) -> IntegrationError:
        try:
            msg = json.loads(body).get("message", "")
        except (ValueError, AttributeError):
            msg = body[:200].decode("utf-8", "replace")
        hint = {401: " (token caducado o no válido: genera uno nuevo)",
                403: " (faltan permisos: revisa los productos de la app y los scopes del token)",
                429: " (límite de LinkedIn alcanzado: prueba mañana)"}.get(status, "")
        return IntegrationError(redact(f"LinkedIn {what}: HTTP {status} {msg}{hint}")[:300])

    def whoami(self) -> dict:
        if not self.token:
            raise IntegrationNotConfigured(self.info().setup)
        status, _, body = self.http("GET", f"{LINKEDIN_API}/v2/userinfo", {"Authorization": f"Bearer {self.token}"}, None)
        if status != 200:
            raise self._error("al identificar la cuenta", status, body)
        data = json.loads(body)
        if not data.get("sub"):
            raise IntegrationError("LinkedIn no devolvió el identificador de la cuenta")
        return {"sub": data["sub"], "name": data.get("name", "")}

    def publish(self, text: str, **_) -> dict:
        me = self.whoami()
        payload = {
            "author": f"urn:li:person:{me['sub']}",
            "commentary": escape_little(text),
            "visibility": "PUBLIC",
            "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        status, headers, body = self.http("POST", f"{LINKEDIN_API}/rest/posts", self._headers(True),
                                          json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        if status != 201:
            raise self._error("al publicar", status, body)
        post_id = headers.get("x-restli-id", "")
        if not post_id:
            raise IntegrationError("LinkedIn respondió 201 sin id de publicación; revísalo en tu perfil antes de reintentar")
        return {"id": post_id, "url": f"https://www.linkedin.com/feed/update/{post_id}/"}


INSTAGRAM_API = "https://graph.instagram.com"


def image_urls(draft: dict, base_url: str) -> list[str]:
    """URLs públicas de las diapositivas de un borrador de Instagram (las sirve /media/ig/...)."""
    from .slides import parse_carousel

    texts, _ = parse_carousel(draft["body"])
    return [f"{base_url.rstrip('/')}/media/ig/{draft['id']}/{n}.jpg" for n in range(1, len(texts) + 1)]


class Instagram:
    name = "instagram"

    def __init__(self, http: HttpFn | None = None, sleep: Callable[[float], None] | None = None):
        self.token = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip()
        self.version = os.environ.get("INSTAGRAM_API_VERSION", "").strip() or "v23.0"
        self.expires = os.environ.get("INSTAGRAM_TOKEN_EXPIRES", "").strip()
        self.http = http or _http
        self.sleep = sleep or time.sleep

    def info(self) -> IntegrationInfo:
        return IntegrationInfo(
            "red_instagram", bool(self.token),
            "publicar carruseles en tu cuenta profesional solo de borradores aprobados; sin leer mensajes",
            "Crea una app en developers.facebook.com con el producto «API de Instagram» (inicio de sesión de "
            "Instagram), genera un token para tu cuenta profesional y ponlo en INSTAGRAM_ACCESS_TOKEN (y su "
            "caducidad en INSTAGRAM_TOKEN_EXPIRES=AAAA-MM-DD). Guía: docs/REDES.md")

    days_left = LinkedIn.days_left

    def _url(self, path: str) -> str:
        return f"{INSTAGRAM_API}/{self.version}/{path.lstrip('/')}"

    def _call(self, method: str, path: str, what: str, data: dict | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self.token}"}
        body = None
        if data is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        status, _, raw = self.http(method, self._url(path), headers, body)
        if status != 200:
            try:
                msg = json.loads(raw).get("error", {}).get("message", "")
            except (ValueError, AttributeError):
                msg = raw[:200].decode("utf-8", "replace")
            hint = {400: " (revisa que la cuenta sea profesional y que la imagen sea accesible)",
                    401: " (token caducado o no válido: genera uno nuevo)",
                    403: " (faltan permisos: instagram_business_content_publish)"}.get(status, "")
            raise IntegrationError(redact(f"Instagram {what}: HTTP {status} {msg}{hint}")[:300])
        return json.loads(raw or b"{}")

    def whoami(self) -> dict:
        if not self.token:
            raise IntegrationNotConfigured(self.info().setup)
        data = self._call("GET", "me?fields=user_id,username", "al identificar la cuenta")
        if not data.get("user_id"):
            raise IntegrationError("Instagram no devolvió el identificador de la cuenta")
        return {"id": str(data["user_id"]), "name": data.get("username", "")}

    def _wait(self, container: str) -> None:
        for _ in range(10):
            st = self._call("GET", f"{container}?fields=status_code", "al comprobar el contenedor").get("status_code")
            if st == "FINISHED":
                return
            if st in ("ERROR", "EXPIRED"):
                raise IntegrationError(f"Instagram no pudo procesar la publicación (estado {st})")
            self.sleep(3)
        raise IntegrationError("Instagram tarda demasiado en procesar las imágenes; inténtalo más tarde")

    def publish(self, text: str, images: list[str] | None = None, **_) -> dict:
        if not images:
            raise ValueError("Instagram solo publica con imagen y este borrador no tiene diapositivas")
        me = self.whoami()
        uid = me["id"]
        if len(images) == 1:
            container = self._call("POST", f"{uid}/media", "al subir la imagen",
                                   {"image_url": images[0], "caption": text})["id"]
        else:
            children = [self._call("POST", f"{uid}/media", f"al subir la imagen {i}",
                                   {"image_url": url, "is_carousel_item": True})["id"]
                        for i, url in enumerate(images, 1)]
            for child in children:
                self._wait(child)
            container = self._call("POST", f"{uid}/media", "al crear el carrusel",
                                   {"media_type": "CAROUSEL", "children": ",".join(children), "caption": text})["id"]
        self._wait(container)
        media_id = self._call("POST", f"{uid}/media_publish", "al publicar", {"creation_id": container})["id"]
        try:
            url = self._call("GET", f"{media_id}?fields=permalink", "al pedir el enlace").get("permalink", "")
        except IntegrationError:
            url = ""
        return {"id": media_id, "url": url or f"https://www.instagram.com/{me['name']}/"}


PUBLISHERS = {"linkedin": LinkedIn, "instagram": Instagram}


def publish_draft(conn: sqlite3.Connection, actor: Actor, settings: Settings, draft_id: int,
                  http: HttpFn | None = None) -> dict:
    """Publica un borrador aprobado en su red. Acción humana (botón del panel)."""
    from ..agents.content import render_body

    require_human(actor, "publicar en redes")
    d = permissions.check(conn, actor, "social", "publish")
    if not d.allowed:
        raise PermissionError(d.reason)
    draft = one(conn, "SELECT * FROM content_drafts WHERE id=?", (draft_id,))
    if draft is None:
        raise KeyError(draft_id)
    if draft["status"] != "approved":
        raise ValueError("solo se publican borradores aprobados (y no publicados)")
    cls = PUBLISHERS.get(draft["channel"])
    if cls is None:
        raise ValueError(f"no hay conector para {draft['channel']}: publícalo a mano")
    if any(h in settings.public_base_url for h in ("localhost", "127.0.0.1")):
        raise ValueError("PUBLIC_BASE_URL apunta a tu ordenador: el enlace no funcionaría fuera. Pon la dirección https de cloudflared")
    today = datetime.now(timezone.utc).date().isoformat()
    used = conn.execute("SELECT COUNT(*) c FROM content_drafts WHERE published_via=? AND published_at >= ?",
                        (f"api:{draft['channel']}", today)).fetchone()["c"]
    if used >= settings_store.get_int(conn, "social_daily_limit"):
        raise PermissionError(f"límite diario de publicaciones en {draft['channel']} alcanzado")
    text = render_body(draft, settings.public_base_url)
    images = None
    if draft["channel"] == "instagram":
        from .slides import parse_carousel

        images = image_urls(draft, settings.public_base_url)
        text = parse_carousel(text)[1]
    publisher = cls(http=http)
    try:
        res = publisher.publish(text, images=images)
    except (IntegrationError, IntegrationNotConfigured) as e:
        audit.log(conn, actor, "social.publish_failed", f"draft:{draft_id}", {"channel": draft["channel"], "error": str(e)})
        raise
    with transaction(conn):
        conn.execute("UPDATE content_drafts SET status='published', published_at=?, published_url=?, published_via=?,"
                     " external_id=?, decided_by=? WHERE id=?",
                     (now_iso(), res["url"], f"api:{draft['channel']}", res["id"], actor.label, draft_id))
        audit.log(conn, actor, "social.publish", f"draft:{draft_id}", {"channel": draft["channel"], "id": res["id"]})
    return res


def info_all() -> list[IntegrationInfo]:
    return [cls().info() for cls in PUBLISHERS.values()]


def token_warnings() -> list[str]:
    out = []
    for name, cls in PUBLISHERS.items():
        p = cls()
        if p.token and getattr(p, "days_left", None):
            left = p.days_left()
            if left is not None and left <= 7:
                out.append(f"El permiso de {name} caduca en {left} días: genera un token nuevo" if left >= 0
                           else f"El permiso de {name} ha caducado: genera un token nuevo")
    return out

