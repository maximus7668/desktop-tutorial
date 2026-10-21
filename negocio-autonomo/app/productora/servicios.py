"""Servicios externos de la productora: HeyGen (presentador) y TikTok (subida y métricas).

HeyGen API v3: POST /v3/assets (audio), POST /v3/videos (avatar con nuestro audio), GET /v3/videos/{id}.
TikTok: OAuth v2, Content Posting API en modo «bandeja» (el vídeo llega como borrador a la app de TikTok y el
dueño pulsa Publicar; sin auditoría de la app no se puede publicar en público) y Display API para métricas."""
from __future__ import annotations

import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HEYGEN = "https://api.heygen.com"
TIKTOK = "https://open.tiktokapis.com"
TIKTOK_AUTH = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_SCOPES = "user.info.basic,video.upload,video.list"


class ServiceError(RuntimeError):
    pass


def _env(k: str) -> str:
    return os.environ.get(k, "").strip()


def _call(req: urllib.request.Request, timeout: int = 120) -> dict:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        raise ServiceError(f"HTTP {e.code} en {req.full_url.split('?')[0]}: {e.read()[:300].decode('utf-8', 'replace')}")
    except urllib.error.URLError as e:
        raise ServiceError(f"sin conexión con {req.full_url.split('?')[0]}: {e.reason}")
    return json.loads(body) if body else {}


# ------------------------------------------------------------------ HeyGen
def heygen_configured() -> bool:
    return bool(_env("HEYGEN_API_KEY") and _env("HEYGEN_AVATAR_ID"))


def _multipart(field: str, filename: str, data: bytes, ctype: str) -> tuple[bytes, str]:
    b = "----productora" + secrets.token_hex(8)
    head = (f"--{b}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n").encode()
    return head + data + f"\r\n--{b}--\r\n".encode(), f"multipart/form-data; boundary={b}"


def heygen_presenter(audio: Path, out: Path, max_wait_s: int = 2400) -> dict:
    """Genera el presentador hablando con nuestro audio (WAV/MP3, máx. 32 MB) y lo descarga en out."""
    key, avatar = _env("HEYGEN_API_KEY"), _env("HEYGEN_AVATAR_ID")
    if not (key and avatar):
        raise ServiceError("Faltan HEYGEN_API_KEY o HEYGEN_AVATAR_ID en .env")
    body, ctype = _multipart("file", audio.name, audio.read_bytes(),
                             "audio/wav" if audio.suffix == ".wav" else "audio/mpeg")
    asset = _call(urllib.request.Request(f"{HEYGEN}/v3/assets", data=body, method="POST",
                                         headers={"X-Api-Key": key, "Content-Type": ctype}))
    asset_id = asset["data"]["id"]
    req = {"type": "avatar", "avatar_id": avatar, "audio_asset_id": asset_id, "aspect_ratio": "9:16",
           "resolution": "1080p", "background": {"type": "color", "value": _env("HEYGEN_BG") or "#1B2246"},
           "title": out.parent.name}
    if _env("HEYGEN_ENGINE"):
        req["engine"] = {"type": _env("HEYGEN_ENGINE")}
    created = _call(urllib.request.Request(f"{HEYGEN}/v3/videos", data=json.dumps(req).encode(), method="POST",
                                           headers={"X-Api-Key": key, "Content-Type": "application/json"}))
    vid = created["data"]["video_id"]
    t0 = time.time()
    while time.time() - t0 < max_wait_s:
        st = _call(urllib.request.Request(f"{HEYGEN}/v3/videos/{vid}", headers={"X-Api-Key": key}))["data"]
        if st.get("status") == "completed":
            urllib.request.urlretrieve(st["video_url"], out)
            return {"video_id": vid, "segundos_espera": round(time.time() - t0)}
        if st.get("status") == "failed":
            raise ServiceError(f"HeyGen falló: {st.get('failure_message')}")
        time.sleep(15)
    raise ServiceError(f"HeyGen no terminó en {max_wait_s} s (video_id {vid})")


# ------------------------------------------------------------------ TikTok
def tiktok_configured() -> bool:
    return bool(_env("TIKTOK_CLIENT_KEY") and _env("TIKTOK_CLIENT_SECRET"))


def tiktok_auth_url(redirect_uri: str, state: str) -> str:
    q = {"client_key": _env("TIKTOK_CLIENT_KEY"), "scope": TIKTOK_SCOPES, "response_type": "code",
         "redirect_uri": redirect_uri, "state": state}
    return TIKTOK_AUTH + "?" + urllib.parse.urlencode(q)


def _token_request(form: dict) -> dict:
    data = urllib.parse.urlencode({"client_key": _env("TIKTOK_CLIENT_KEY"),
                                   "client_secret": _env("TIKTOK_CLIENT_SECRET"), **form}).encode()
    tok = _call(urllib.request.Request(f"{TIKTOK}/v2/oauth/token/", data=data, method="POST",
                                       headers={"Content-Type": "application/x-www-form-urlencoded"}))
    if "access_token" not in tok:
        raise ServiceError(f"TikTok no dio token: {tok.get('error_description') or tok.get('error') or tok}")
    tok["expires_at"] = time.time() + int(tok.get("expires_in", 0)) - 120
    return tok


def tiktok_exchange_code(code: str, redirect_uri: str, store: Path) -> dict:
    tok = _token_request({"code": code, "grant_type": "authorization_code", "redirect_uri": redirect_uri})
    store.write_text(json.dumps(tok), encoding="utf-8")
    return {"open_id": tok.get("open_id"), "scope": tok.get("scope")}


def tiktok_token(store: Path) -> str:
    if not store.exists():
        raise ServiceError("TikTok sin autorizar: entra en el panel → /tiktok/conectar")
    tok = json.loads(store.read_text(encoding="utf-8"))
    if time.time() >= tok.get("expires_at", 0):
        tok = _token_request({"grant_type": "refresh_token", "refresh_token": tok["refresh_token"]})
        store.write_text(json.dumps(tok), encoding="utf-8")
    return tok["access_token"]


def tiktok_upload_draft(video: Path, store: Path) -> dict:
    """Sube el vídeo a la bandeja de TikTok del dueño (borrador). Un solo trozo: vale hasta 64 MB."""
    size = video.stat().st_size
    if size > 64 * 1024 * 1024:
        raise ServiceError("vídeo de más de 64 MB: hay que subirlo por trozos")
    auth = {"Authorization": f"Bearer {tiktok_token(store)}", "Content-Type": "application/json; charset=UTF-8"}
    init = _call(urllib.request.Request(
        f"{TIKTOK}/v2/post/publish/inbox/video/init/", method="POST", headers=auth,
        data=json.dumps({"source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size,
                                         "total_chunk_count": 1}}).encode()))
    if init.get("error", {}).get("code", "ok") != "ok":
        raise ServiceError(f"TikTok init: {init['error']}")
    data = init["data"]
    _call(urllib.request.Request(data["upload_url"], data=video.read_bytes(), method="PUT",
                                 headers={"Content-Type": "video/mp4", "Content-Length": str(size),
                                          "Content-Range": f"bytes 0-{size - 1}/{size}"}), timeout=600)
    st = _call(urllib.request.Request(f"{TIKTOK}/v2/post/publish/status/fetch/", method="POST", headers=auth,
                                      data=json.dumps({"publish_id": data["publish_id"]}).encode()))
    return {"publish_id": data["publish_id"], "estado": st.get("data", {}).get("status")}


def tiktok_video_metrics(store: Path, max_videos: int = 20) -> list[dict]:
    fields = "id,title,create_time,duration,view_count,like_count,comment_count,share_count,share_url"
    req = urllib.request.Request(f"{TIKTOK}/v2/video/list/?fields={fields}", method="POST",
                                 data=json.dumps({"max_count": max_videos}).encode(),
                                 headers={"Authorization": f"Bearer {tiktok_token(store)}",
                                          "Content-Type": "application/json"})
    res = _call(req)
    if res.get("error", {}).get("code", "ok") != "ok":
        raise ServiceError(f"TikTok métricas: {res['error']}")
    return res.get("data", {}).get("videos", [])
