"""Efectos de sonido sintetizados (originales, sin derechos): «whoosh» de transición."""
from __future__ import annotations

import numpy as np

from . import audio


def whoosh(dur: float = 0.9, sr: int = audio.SR, semilla: int = 0) -> np.ndarray:
    """Ruido filtrado cuyo brillo sube y baja (filtro por bloques con FFT: rápido y sin dependencias)."""
    rng = np.random.default_rng(semilla)
    n = int(dur * sr)
    marco, salto = 2048, 512
    total = n + marco
    ventana = np.hanning(marco)
    bloques = (total - marco) // salto + 1
    idx = np.arange(marco)[None, :] + salto * np.arange(bloques)[:, None]
    espectro = np.fft.rfft(rng.normal(0, 1, total)[idx] * ventana, axis=1)
    f = np.fft.rfftfreq(marco, 1 / sr)[None, :]
    t = ((np.arange(bloques) * salto + marco / 2) / total)[:, None]
    corte = 250 + 3800 * np.sin(np.pi * np.clip(t * 1.1, 0, 1)) ** 1.5
    mascara = (1 / (1 + (f / corte) ** 4)) * (1 - 1 / (1 + (f / 140) ** 4))
    trozos = np.fft.irfft(espectro * mascara, n=marco, axis=1) * ventana
    salida = np.zeros(total)
    np.add.at(salida, idx, trozos)
    s = salida[marco // 2: marco // 2 + n] * np.sin(np.pi * np.linspace(0, 1, n)) ** 2.2
    return (s / (np.abs(s).max() + 1e-9) * 0.5).astype(np.float32)


def pista(duracion: float, momentos: list[float], sr: int = audio.SR) -> np.ndarray:
    """Pista mono de `duracion` s con un whoosh cuyo pico cae en cada momento."""
    res = np.zeros(int(duracion * sr), np.float32)
    for k, m in enumerate(momentos):
        w = whoosh(semilla=k)
        ini = int((m - 0.42) * sr)
        if ini < 0 or ini + len(w) > len(res):
            continue
        res[ini:ini + len(w)] += w
    return res
