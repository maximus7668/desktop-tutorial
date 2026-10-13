"""Música de fondo. Usa pistas propias de canal-youtube/musica/ (p. ej. de la Biblioteca de audio
de YouTube) y, si no hay, genera una base ambiental original: sin reclamaciones de Content ID."""
from __future__ import annotations

import hashlib
import random
from pathlib import Path

import numpy as np

from . import audio
from .config import CACHE, MUSICA

NOTAS = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
ANIMOS = {  # progresiones lentas, acordes de 3 notas (nombres relativos a do)
    "misterio": [("A", "m"), ("F", ""), ("C", ""), ("G", "")],
    "tension": [("D", "m"), ("A#", ""), ("D", "m"), ("C", "")],
    "neutro": [("C", ""), ("G", ""), ("A", "m"), ("F", "")],
    "epico": [("D", "m"), ("A#", ""), ("F", ""), ("C", "")],
}


def _freq(nota: int, octava: int) -> float:
    return 440.0 * 2 ** ((nota + 12 * (octava + 1) - 69) / 12)


def _acorde(raiz: str, tipo: str) -> list[int]:
    r = NOTAS[raiz]
    return [r, r + (3 if tipo == "m" else 4), r + 7]


def generar(duracion: float, animo: str = "misterio", semilla: int = 0, sr: int = audio.SR) -> np.ndarray:
    """Pad ambiental estéreo: acordes suaves, bajo y algún destello; float32 (n, 2)."""
    rng = np.random.default_rng(semilla)
    prog = ANIMOS.get(animo, ANIMOS["misterio"])
    paso = 8.0  # segundos por acorde
    n = int(duracion * sr) + sr
    t = np.arange(n) / sr
    salida = np.zeros((n, 2), np.float32)
    ventana = int(paso * sr)
    caida = int(2.5 * sr)
    for k, inicio in enumerate(range(0, n, ventana)):
        raiz, tipo = prog[k % len(prog)]
        notas = _acorde(raiz, tipo)
        a, b = max(0, inicio - caida), min(n, inicio + ventana + caida)
        tt = t[a:b]
        env = np.ones(b - a, np.float32)
        sube = min(caida * 2, b - a)
        env[:sube] = np.linspace(0, 1, sube) ** 1.5
        env[-caida:] *= np.linspace(1, 0, min(caida, b - a)) ** 1.5
        for i, nota in enumerate(notas):
            f = _freq(nota % 12, 3 + (nota >= 12))
            for lado, desafino in ((0, 0.997), (1, 1.003)):
                fase = rng.uniform(0, 2 * np.pi)
                onda = np.sin(2 * np.pi * f * desafino * tt + fase) + 0.18 * np.sin(4 * np.pi * f * desafino * tt)
                trem = 0.85 + 0.15 * np.sin(2 * np.pi * (0.07 + 0.02 * i) * tt + fase)
                salida[a:b, lado] += (0.16 * onda * trem * env).astype(np.float32)
        bajo = np.sin(2 * np.pi * _freq(notas[0] % 12, 2) * tt) * 0.22 * env
        salida[a:b] += bajo[:, None].astype(np.float32)
        # destellos ocasionales: notas del acorde una octava arriba, con caída exponencial
        for _ in range(2):
            if rng.random() < 0.6:
                p = int(rng.uniform(0.5, paso - 1) * sr) + inicio
                largo = int(3.5 * sr)
                if p + largo < n:
                    f = _freq(notas[rng.integers(0, 3)] % 12, 5)
                    tb = np.arange(largo) / sr
                    gota = np.sin(2 * np.pi * f * tb) * np.exp(-tb * 1.6) * 0.07
                    pan = rng.uniform(0.25, 0.75)
                    salida[p:p + largo, 0] += (gota * (1 - pan)).astype(np.float32)
                    salida[p:p + largo, 1] += (gota * pan).astype(np.float32)
    salida = salida[: int(duracion * sr)]
    rms = np.sqrt(np.mean(salida ** 2)) + 1e-9
    salida *= 10 ** (-20 / 20) / rms
    return np.clip(salida, -0.98, 0.98)


def elegir(duracion: float, animo: str, video_id: str) -> Path:
    """Pista para este vídeo: una propia al azar (sin repetir la anterior) o una generada."""
    propias = sorted(p for p in MUSICA.glob("*") if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg", ".flac"))
    if propias:
        rnd = random.Random(video_id)
        return rnd.choice(propias)
    semilla = int(hashlib.sha1(video_id.encode()).hexdigest()[:8], 16)
    ruta = CACHE / "musica" / f"{animo}-{semilla}-{int(duracion)}.wav"
    if not ruta.exists():
        ruta.parent.mkdir(parents=True, exist_ok=True)
        estereo = generar(duracion + 2, animo, semilla)
        datos = (np.clip(estereo, -1, 1) * 32767).astype(np.int16)
        import wave

        with wave.open(str(ruta), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(audio.SR)
            w.writeframes(datos.tobytes())
    return ruta
