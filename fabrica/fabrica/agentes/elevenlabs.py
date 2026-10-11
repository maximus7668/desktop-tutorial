"""Voces, efectos de sonido y música con la API de ElevenLabs.

Rutas según la documentación oficial (elevenlabs.io/docs/api-reference):
  voz     POST /v1/text-to-speech/{voice_id}
  sonido  POST /v1/sound-generation   (de 0,5 a 30 segundos)
  musica  POST /v1/music              (de 3 segundos a 10 minutos)
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

from . import Contexto, ErrorAgente, Resultado

API = "https://api.elevenlabs.io"
VARIABLE_CLAVE = "ELEVENLABS_API_KEY"
FORMATO = "mp3_44100_128"

# (url, cuerpo JSON, cabeceras, segundos de espera) -> bytes del audio
Http = Callable[[str, dict, dict, float], bytes]


def _post(url: str, cuerpo: dict, cabeceras: dict, espera: float) -> bytes:
    peticion = urllib.request.Request(
        url, data=json.dumps(cuerpo).encode("utf-8"), headers=cabeceras, method="POST"
    )
    try:
        with urllib.request.urlopen(peticion, timeout=espera) as respuesta:
            return respuesta.read()
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", "replace")[:300]
        raise ErrorAgente(f"ElevenLabs respondió {e.code}: {detalle}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise ErrorAgente(f"No se pudo hablar con ElevenLabs: {getattr(e, 'reason', e)}") from None


class AgenteElevenLabs:
    nombre = "elevenlabs"
    tipos = frozenset({"voz", "sonido", "musica"})
    AJUSTES: tuple[str, ...] = ()

    def __init__(self, clave: str | None = None, http: Http | None = None):
        self._clave = (clave if clave is not None else os.environ.get(VARIABLE_CLAVE, "")).strip()
        self._http = http or _post

    def disponible(self) -> str | None:
        if not self._clave:
            return f"Falta la clave de ElevenLabs: define la variable de entorno {VARIABLE_CLAVE}."
        return None

    def generar(self, ctx: Contexto) -> Resultado:
        tipo = ctx.tarea.tipo
        if tipo == "voz":
            url, cuerpo, espera, nota = self._voz(ctx)
        elif tipo == "sonido":
            url, cuerpo, espera, nota = self._sonido(ctx)
        elif tipo == "musica":
            url, cuerpo, espera, nota = self._musica(ctx)
        else:
            raise ErrorAgente(f"ElevenLabs no hace '{tipo}'.")

        cabeceras = {"xi-api-key": self._clave, "Content-Type": "application/json", "Accept": "audio/mpeg"}
        audio = self._http(url, cuerpo, cabeceras, espera)
        if not audio:
            raise ErrorAgente("ElevenLabs devolvió un audio vacío.")
        ruta = ctx.archivo(f"{ctx.tarea.nombre}.mp3")
        ruta.write_bytes(audio)
        return Resultado([ruta], nota)

    def _voz(self, ctx: Contexto) -> tuple[str, dict, float, str]:
        datos = ctx.tarea.datos
        if not datos.get("voz_id"):
            raise ErrorAgente(
                f"Falta voz_id de {datos['personaje']} en juego.toml: copia el ID de una voz de tu"
                " biblioteca de ElevenLabs."
            )
        voz = urllib.parse.quote(datos["voz_id"], safe="")
        url = f"{API}/v1/text-to-speech/{voz}?output_format={FORMATO}"
        # El texto de la frase no cambia al rechazarla; otra semilla da otra interpretación.
        cuerpo = {"text": datos["texto"], "model_id": "eleven_multilingual_v2", "seed": ctx.intento}
        nota = "Toma nueva con otra semilla." if ctx.motivo_rechazo else ""
        return url, cuerpo, 60.0, nota

    def _sonido(self, ctx: Contexto) -> tuple[str, dict, float, str]:
        datos = ctx.tarea.datos
        texto = datos["descripcion"]
        if ctx.motivo_rechazo:
            texto = f"{texto}. {ctx.motivo_rechazo}"
        cuerpo: dict = {"text": texto, "model_id": "eleven_text_to_sound_v2", "prompt_influence": 0.5}
        duracion = datos.get("duracion")
        if duracion is not None:
            if not 0.5 <= duracion <= 30:
                raise ErrorAgente(
                    f"ElevenLabs hace efectos de 0,5 a 30 segundos y «{ctx.tarea.nombre}» pide {duracion:g}."
                )
            cuerpo["duration_seconds"] = duracion
        if datos.get("bucle"):
            cuerpo["loop"] = True  # solo lo admite eleven_text_to_sound_v2, el modelo que se usa
        return f"{API}/v1/sound-generation?output_format={FORMATO}", cuerpo, 120.0, ""

    def _musica(self, ctx: Contexto) -> tuple[str, dict, float, str]:
        datos = ctx.tarea.datos
        prompt = datos["descripcion"]
        if ctx.motivo_rechazo:
            prompt = f"{prompt}. {ctx.motivo_rechazo}"
        cuerpo: dict = {"prompt": prompt, "force_instrumental": bool(datos["instrumental"])}
        duracion = datos.get("duracion")
        if duracion is not None:
            milisegundos = round(duracion * 1000)
            if not 3000 <= milisegundos <= 600000:
                raise ErrorAgente(
                    f"ElevenLabs hace música de 3 segundos a 10 minutos y «{ctx.tarea.nombre}» pide {duracion:g} s."
                )
            cuerpo["music_length_ms"] = milisegundos
        # Una canción larga puede tardar varios minutos en generarse.
        return f"{API}/v1/music?output_format={FORMATO}", cuerpo, 600.0, ""
