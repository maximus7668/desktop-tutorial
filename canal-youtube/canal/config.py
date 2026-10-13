"""Configuración del canal (canal.yaml) y claves (variables de entorno o .env)."""
from __future__ import annotations

import copy
import os
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
FUENTES = RAIZ / "fuentes"
MUSICA = RAIZ / "musica"
MEMORIA = RAIZ / "memoria"
GUIONES = RAIZ / "guiones"
SECRETOS = RAIZ / "secretos"
CACHE = Path(os.environ.get("CANAL_CACHE", RAIZ / "cache"))
SALIDA = Path(os.environ.get("CANAL_SALIDA", RAIZ / "salida"))

# Valores por defecto: canal.yaml solo necesita lo que cambie.
POR_DEFECTO: dict = {
    "canal": {
        "nombre": "Mi canal",
        "idioma": "es",
        "contacto_api": "",
    },
    "voz": {
        "proveedor": "piper",
        "velocidad": 1.0,
        "pausa_entre_escenas": 0.25,
        "pausa_entre_capitulos": 0.7,
        "normalizar_numeros": "auto",
        "pronunciacion": {},
        "elevenlabs": {
            "voice_id": "",
            "modelo": "eleven_multilingual_v2",
            "estabilidad": 0.45,
            "similitud": 0.8,
            "estilo": 0.15,
        },
        "azure": {"region": "westeurope", "voz": "es-ES-AlvaroNeural"},
        "openai": {
            "modelo": "gpt-4o-mini-tts",
            "voz": "onyx",
            "instrucciones": "Narrador de documental en español, tono cálido y con intriga, ritmo ágil.",
        },
        "piper": {"modelo": "es_ES-davefx-medium"},
    },
    "visuales": {
        "stock": ["pexels", "pixabay", "wikimedia"],
        "ia": {"proveedor": "ninguno", "modelo": "gpt-image-1", "calidad": "medium"},
        "plano_max_seg": 7.0,
    },
    "estilo": {
        "color_acento": "#F5C518",
        "color_texto": "#FFFFFF",
        "color_fondo": "#0D0F14",
        "fuente_titulos": "Anton-Regular.ttf",
        "fuente_subtitulos": "Montserrat-Black.ttf",
        "fuente_texto": "Montserrat-ExtraBold.ttf",
        "vineta": True,
        "grano": 4,
        "musica_db": -22,
        "animo_musica": "misterio",
        "aviso_ia": True,
        "sfx_transiciones": True,
    },
    "largo": {
        "resolucion": [1920, 1080],
        "fps": 30,
        "subtitulos_quemados": False,
        "palabras_min": 1100,
        "palabras_max": 2400,
    },
    "short": {
        "resolucion": [1080, 1920],
        "fps": 30,
        "duracion_objetivo_seg": 55,
        "duracion_max_seg": 180,
        "palabras_por_grupo": 3,
    },
    "presupuesto": {
        "mensual_eur": 25.0,
        "eur_por_1000_caracteres": {"elevenlabs": 0.24, "azure": 0.015, "openai": 0.012, "piper": 0.0},
        "eur_por_imagen_ia": 0.05,
    },
    "autonomia": {
        "subir_privado": False,
    },
    "youtube": {
        "categoria": "27",
        "idioma": "es",
        "hecho_para_ninos": False,
    },
}


def _fusionar(base: dict, encima: dict) -> dict:
    res = copy.deepcopy(base)
    for k, v in (encima or {}).items():
        if isinstance(v, dict) and isinstance(res.get(k), dict):
            res[k] = _fusionar(res[k], v)
        else:
            res[k] = v
    return res


def cargar(ruta: Path | None = None) -> dict:
    ruta = Path(ruta) if ruta else RAIZ / "canal.yaml"
    datos = {}
    if ruta.exists():
        with open(ruta, encoding="utf-8") as f:
            datos = yaml.safe_load(f) or {}
    return _fusionar(POR_DEFECTO, datos)


_ENV_CARGADO = False


def _cargar_env() -> None:
    """Lee canal-youtube/.env (no se sube al repo) sin pisar variables ya definidas."""
    global _ENV_CARGADO
    if _ENV_CARGADO:
        return
    _ENV_CARGADO = True
    fichero = RAIZ / ".env"
    if not fichero.exists():
        return
    for linea in fichero.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, v = linea.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def clave(nombre: str, obligatoria: bool = True) -> str | None:
    _cargar_env()
    valor = os.environ.get(nombre) or None
    if obligatoria and not valor:
        raise SystemExit(
            f"Falta la clave {nombre}. Ponla en canal-youtube/.env o como variable de entorno "
            f"(en la nube: secretos del entorno). Nunca en el chat ni en el repositorio."
        )
    return valor


def fuente(nombre: str) -> Path:
    ruta = FUENTES / nombre
    if not ruta.exists():
        raise FileNotFoundError(f"No encuentro la fuente {ruta}")
    return ruta
