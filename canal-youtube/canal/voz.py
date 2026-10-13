"""Voz sintética. Proveedores: elevenlabs, azure, openai y piper (gratis, local, para pruebas).

Cada escena se sintetiza una vez y se guarda en caché: volver a montar un vídeo no vuelve a
gastar créditos. El gasto se apunta y se corta al llegar al tope mensual de canal.yaml.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
import requests

from . import audio, registro
from .config import CACHE, clave
from .texto import Token, frases, repartir, texto_hablado, tiempos_por_caracteres

PIPER_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/{loc}/{nombre}/{calidad}/{modelo}.onnx"


@dataclass
class Locucion:
    audio: np.ndarray                    # float32 mono a audio.SR
    tiempos: list[tuple[float, float]]   # (inicio, fin) de cada token, en segundos


class Proveedor:
    nombre = "base"
    lotes_por_frase = False  # True: una petición por frase (tiempos exactos por frase)

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.vcfg = cfg["voz"]

    def firma(self) -> str:
        return json.dumps(self.vcfg.get(self.nombre, {}), sort_keys=True) + str(self.vcfg["velocidad"])

    def pedir(self, texto: str, contexto: tuple[str, str]) -> tuple[np.ndarray, list[float] | None, list[float] | None]:
        """Devuelve (audio, inicios_caracter, finales_caracter); los tiempos solo si el proveedor los da."""
        raise NotImplementedError


class Piper(Proveedor):
    nombre = "piper"
    lotes_por_frase = True

    def __init__(self, cfg):
        super().__init__(cfg)
        from piper import PiperVoice

        modelo = self.vcfg["piper"]["modelo"]
        ruta = CACHE / "voces" / f"{modelo}.onnx"
        if not ruta.exists():
            loc, nombre, calidad = modelo.split("-")
            ruta.parent.mkdir(parents=True, exist_ok=True)
            for ext in (".onnx", ".onnx.json"):
                url = PIPER_URL.format(loc=loc, nombre=nombre, calidad=calidad, modelo=modelo) + ext[5:]
                r = requests.get(url, timeout=300)
                r.raise_for_status()
                (ruta.parent / f"{modelo}{ext}").write_bytes(r.content)
        self.voz = PiperVoice.load(str(ruta))

    def pedir(self, texto, contexto):
        from piper import SynthesisConfig

        conf = SynthesisConfig(length_scale=1.0 / float(self.vcfg["velocidad"]))
        trozos = [c.audio_float_array for c in self.voz.synthesize(texto, syn_config=conf)]
        pcm = np.concatenate(trozos) if trozos else np.zeros(1, np.float32)
        return audio.desde_pcm(pcm, self.voz.config.sample_rate), None, None


class ElevenLabs(Proveedor):
    nombre = "elevenlabs"

    def pedir(self, texto, contexto):
        c = self.vcfg["elevenlabs"]
        if not c.get("voice_id"):
            raise SystemExit("Falta voz.elevenlabs.voice_id en canal.yaml")
        cuerpo = {
            "text": texto,
            "model_id": c["modelo"],
            "voice_settings": {
                "stability": c["estabilidad"], "similarity_boost": c["similitud"], "style": c["estilo"],
                "use_speaker_boost": True, "speed": float(self.vcfg["velocidad"]),
            },
            "previous_text": contexto[0][-600:] or None,
            "next_text": contexto[1][:600] or None,
        }
        r = _post(f"https://api.elevenlabs.io/v1/text-to-speech/{c['voice_id']}/with-timestamps"
                  f"?output_format=mp3_44100_128",
                  headers={"xi-api-key": clave("ELEVENLABS_API_KEY")}, json=cuerpo)
        datos = r.json()
        tmp = CACHE / "tmp_eleven.mp3"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(base64.b64decode(datos["audio_base64"]))
        al = datos.get("alignment") or {}
        return audio.leer(tmp), al.get("character_start_times_seconds"), al.get("character_end_times_seconds")


class Azure(Proveedor):
    nombre = "azure"

    def pedir(self, texto, contexto):
        c = self.vcfg["azure"]
        idioma = "-".join(c["voz"].split("-")[:2])
        ritmo = f"{(float(self.vcfg['velocidad']) - 1) * 100:+.0f}%"
        ssml = (f"<speak version='1.0' xml:lang='{idioma}'><voice name='{c['voz']}'>"
                f"<prosody rate='{ritmo}'>{escape(texto)}</prosody></voice></speak>")
        r = _post(f"https://{c['region']}.tts.speech.microsoft.com/cognitiveservices/v1",
                  headers={"Ocp-Apim-Subscription-Key": clave("AZURE_SPEECH_KEY"),
                           "Content-Type": "application/ssml+xml",
                           "X-Microsoft-OutputFormat": "riff-48khz-16bit-mono-pcm",
                           "User-Agent": "canal-youtube"},
                  data=ssml.encode("utf-8"))
        return _wav_a_array(r.content), None, None


class OpenAI(Proveedor):
    nombre = "openai"

    def pedir(self, texto, contexto):
        c = self.vcfg["openai"]
        r = _post("https://api.openai.com/v1/audio/speech",
                  headers={"Authorization": f"Bearer {clave('OPENAI_API_KEY')}"},
                  json={"model": c["modelo"], "voice": c["voz"], "input": texto,
                        "instructions": c.get("instrucciones", ""), "response_format": "wav",
                        "speed": float(self.vcfg["velocidad"])})
        return _wav_a_array(r.content), None, None


PROVEEDORES = {p.nombre: p for p in (Piper, ElevenLabs, Azure, OpenAI)}


def _post(url: str, **kw) -> requests.Response:
    for intento in range(4):
        r = requests.post(url, timeout=180, **kw)
        if r.status_code in (429, 500, 502, 503, 504) and intento < 3:
            time.sleep(2 ** (intento + 1))
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"{url.split('?')[0]} respondió {r.status_code}: {r.text[:400]}")
        return r
    raise RuntimeError("sin respuesta")


def _wav_a_array(datos: bytes) -> np.ndarray:
    with wave.open(io.BytesIO(datos)) as w:
        sr, n, ancho = w.getframerate(), w.getnframes(), w.getsampwidth()
        bruto = w.readframes(n)
    if ancho != 2:
        tmp = CACHE / "tmp_tts.wav"
        tmp.write_bytes(datos)
        return audio.leer(tmp)
    pcm = np.frombuffer(bruto, dtype=np.int16).astype(np.float32) / 32768.0
    return audio.desde_pcm(pcm, sr)


class Narrador:
    """Sintetiza escenas con caché, tiempos por palabra y control de gasto."""

    def __init__(self, cfg: dict, proveedor: str | None = None):
        self.cfg = cfg
        nombre = proveedor or cfg["voz"]["proveedor"]
        if nombre not in PROVEEDORES:
            raise SystemExit(f"Proveedor de voz desconocido: {nombre}. Opciones: {', '.join(PROVEEDORES)}")
        self.p = PROVEEDORES[nombre](cfg)
        norm = cfg["voz"]["normalizar_numeros"]
        self.normalizar = nombre == "piper" if norm == "auto" else bool(norm)

    def _cache(self, texto: str) -> Path:
        h = hashlib.sha256(f"{self.p.nombre}|{self.p.firma()}|{texto}".encode()).hexdigest()[:24]
        return CACHE / "voz" / self.p.nombre / f"{h}.npz"

    def _pedir(self, texto: str, contexto: tuple[str, str]):
        ruta = self._cache(texto)
        if ruta.exists():
            d = np.load(ruta, allow_pickle=False)
            ini = d["ini"].tolist() if d["ini"].size else None
            fin = d["fin"].tolist() if d["fin"].size else None
            return d["audio"], ini, fin
        tarifa = self.cfg["presupuesto"]["eur_por_1000_caracteres"].get(self.p.nombre, 0.0)
        coste = len(texto) / 1000 * tarifa
        registro.comprobar_gasto(self.cfg, coste, f"voz {self.p.nombre}")
        a, ini, fin = self.p.pedir(texto, contexto)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(ruta, audio=a.astype(np.float32), ini=np.array(ini or [], dtype=np.float64),
                            fin=np.array(fin or [], dtype=np.float64))
        if coste:
            registro.apuntar_gasto(self.cfg, coste, f"voz {self.p.nombre}: {len(texto)} caracteres")
        return a, ini, fin

    def locutar(self, tokens: list[Token], contexto: tuple[str, str] = ("", "")) -> Locucion:
        sr = audio.SR
        if self.p.lotes_por_frase:
            partes, tiempos, t = [], [], 0.0
            grupos = frases(tokens)
            for i, fr in enumerate(grupos):
                a, _, _ = self._pedir(texto_hablado(fr), contexto)
                a, _ = audio.recortar(a)
                dur = len(a) / sr
                tiempos += repartir(fr, t + 0.03, t + dur - 0.06)
                partes.append(a)
                t += dur
                if i + 1 < len(grupos):
                    pausa = 0.28 if fr[-1].habla.endswith((".", "!", "?", "…")) else 0.12
                    partes.append(audio.silencio(pausa))
                    t += pausa
            return Locucion(np.concatenate(partes), tiempos)

        texto = texto_hablado(tokens)
        a, ini, fin = self._pedir(texto, contexto)
        a_rec, quitado = audio.recortar(a)
        dur = len(a_rec) / sr
        if ini and fin and len(ini) == len(texto):
            tiempos = [(max(0.0, x - quitado), max(0.0, y - quitado)) for x, y in tiempos_por_caracteres(tokens, ini, fin)]
        else:
            tiempos = repartir(tokens, 0.03, max(0.1, dur - 0.08))
        return Locucion(a_rec, tiempos)
