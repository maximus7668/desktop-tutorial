"""Subida a YouTube (siempre en privado), miniatura, subtítulos y programación de la publicación.

Credenciales: cliente OAuth «Aplicación de escritorio» en secretos/client_secret.json y el token
en secretos/token-youtube.json (o en la variable YT_TOKEN_JSON en la nube). Ninguno va al repo.
"""
from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path

from . import registro
from .config import MEMORIA, SECRETOS

ALCANCES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
CLIENTE = SECRETOS / "client_secret.json"
TOKEN = SECRETOS / "token-youtube.json"
REINTENTABLES = (500, 502, 503, 504)


def credenciales(interactivo: bool = False):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = None
    if os.environ.get("YT_TOKEN_JSON"):
        creds = Credentials.from_authorized_user_info(json.loads(os.environ["YT_TOKEN_JSON"]), ALCANCES)
    elif TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), ALCANCES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        if not os.environ.get("YT_TOKEN_JSON"):
            TOKEN.write_text(creds.to_json(), encoding="utf-8")
    if creds and creds.valid:
        return creds
    if not interactivo:
        raise SystemExit("No hay autorización de YouTube válida. Ejecuta en tu ordenador: python -m canal autorizar")
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CLIENTE.exists():
        raise SystemExit(f"Falta {CLIENTE}: descárgalo de Google Cloud (cliente OAuth de tipo «Aplicación de escritorio»).")
    flujo = InstalledAppFlow.from_client_secrets_file(str(CLIENTE), ALCANCES)
    creds = flujo.run_local_server(port=0, access_type="offline", prompt="consent")
    SECRETOS.mkdir(parents=True, exist_ok=True)
    TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return creds


def servicio(nombre: str = "youtube", version: str = "v3"):
    from googleapiclient.discovery import build

    return build(nombre, version, credentials=credenciales(), cache_discovery=False)


def _publicados() -> dict:
    p = MEMORIA / "publicados.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _guardar_publicados(d: dict) -> None:
    MEMORIA.mkdir(parents=True, exist_ok=True)
    (MEMORIA / "publicados.json").write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _ejecutar_subida(peticion) -> dict:
    from googleapiclient.errors import HttpError

    respuesta, fallos = None, 0
    while respuesta is None:
        try:
            _, respuesta = peticion.next_chunk()
        except HttpError as e:
            if e.resp.status not in REINTENTABLES or fallos >= 6:
                raise
            fallos += 1
            time.sleep(min(64, 2 ** fallos) + random.random())
        except (ConnectionError, TimeoutError, OSError):
            if fallos >= 6:
                raise
            fallos += 1
            time.sleep(min(64, 2 ** fallos) + random.random())
    return respuesta


def subir(ruta: Path, titulo: str, descripcion: str, etiquetas: list[str], cfg: dict, sintetico: bool,
          miniatura: Path | None = None, subtitulos: Path | None = None) -> str:
    """Sube en PRIVADO. Publicar es otra orden (programar), con aprobación expresa."""
    from googleapiclient.http import MediaFileUpload

    yt = servicio()
    c = cfg["youtube"]
    cuerpo = {
        "snippet": {"title": titulo[:100], "description": descripcion[:5000], "tags": etiquetas,
                    "categoryId": str(c["categoria"]), "defaultLanguage": c["idioma"],
                    "defaultAudioLanguage": c["idioma"]},
        "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": bool(c["hecho_para_ninos"]),
                   "containsSyntheticMedia": bool(sintetico), "embeddable": True, "license": "youtube"},
    }
    media = MediaFileUpload(str(ruta), mimetype="video/mp4", chunksize=16 * 1024 * 1024, resumable=True)
    resp = _ejecutar_subida(yt.videos().insert(part="snippet,status", body=cuerpo, media_body=media,
                                               notifySubscribers=False))
    vid = resp["id"]
    if miniatura and miniatura.exists():
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(miniatura), mimetype="image/jpeg")).execute()
        except Exception as e:  # sin verificar el teléfono del canal, YouTube no deja poner miniaturas
            print(f"⚠️  Miniatura no subida ({e}). Verifica el canal en youtube.com/verify y súbela en Studio.")
    if subtitulos and subtitulos.exists():
        yt.captions().insert(part="snippet", body={"snippet": {"videoId": vid, "language": c["idioma"],
                                                              "name": "Español", "isDraft": False}},
                             media_body=MediaFileUpload(str(subtitulos), mimetype="application/octet-stream")).execute()
    registro.accion("subir_privado", archivo=ruta.name, youtube_id=vid, titulo=titulo)
    return vid


def subir_video_local(video_id: str, cfg: dict, carpeta: Path, cuales: str = "todo") -> dict:
    meta = json.loads((carpeta / "metadatos.json").read_text(encoding="utf-8"))
    pub = _publicados()
    entrada = pub.setdefault(video_id, {"largo": None, "shorts": {}})
    if cuales in ("todo", "largo") and meta.get("largo") and not entrada.get("largo"):
        m = meta["largo"]
        mini = carpeta / m["miniaturas"][0] if m.get("miniaturas") else None
        yid = subir(carpeta / m["archivo"], m["titulo"], m["descripcion"], m["etiquetas"], cfg,
                    meta["contenido_sintetico_realista"], mini, carpeta / m["subtitulos"])
        entrada["largo"] = {"youtube_id": yid, "subido": _ahora(), "estado": "privado"}
        _guardar_publicados(pub)
        print(f"✅ Largo subido en privado: https://studio.youtube.com/video/{yid}/edit")
    if cuales in ("todo", "shorts"):
        for sid, s in meta.get("shorts", {}).items():
            if entrada["shorts"].get(sid):
                continue
            yid = subir(carpeta / s["archivo"], s["titulo"], s["descripcion"], s["etiquetas"], cfg,
                        meta["contenido_sintetico_realista"], None, carpeta / s["subtitulos"])
            entrada["shorts"][sid] = {"youtube_id": yid, "subido": _ahora(), "estado": "privado"}
            _guardar_publicados(pub)
            print(f"✅ Short {sid} subido en privado: https://studio.youtube.com/video/{yid}/edit")
    return entrada


def programar(youtube_id: str, cuando: datetime) -> dict:
    """Deja el vídeo programado para hacerse público en `cuando` (sigue privado hasta entonces)."""
    yt = servicio()
    actual = yt.videos().list(part="status", id=youtube_id).execute()["items"][0]["status"]
    estado = {k: actual[k] for k in ("embeddable", "license", "publicStatsViewable", "selfDeclaredMadeForKids",
                                      "containsSyntheticMedia") if k in actual}
    estado.update({"privacyStatus": "private", "publishAt": cuando.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    resp = yt.videos().update(part="status", body={"id": youtube_id, "status": estado}).execute()
    registro.accion("programar", youtube_id=youtube_id, cuando=estado["publishAt"])
    pub = _publicados()
    for v in pub.values():
        for d in [v.get("largo")] + list(v.get("shorts", {}).values()):
            if d and d.get("youtube_id") == youtube_id:
                d.update({"estado": "programado", "publica": estado["publishAt"]})
    _guardar_publicados(pub)
    return resp


def _ahora() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
