"""Utilidades de audio: leer/escribir, recortar silencios, mezclar voz y música."""
from __future__ import annotations

import json
import re
import subprocess
import wave
from pathlib import Path

import numpy as np

SR = 48000


def ffmpeg(*args: str, silencioso: bool = True) -> subprocess.CompletedProcess:
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error" if silencioso else "info", *args]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg falló: {' '.join(cmd)}\n{res.stderr[-2000:]}")
    return res


def leer(ruta: str | Path, sr: int = SR) -> np.ndarray:
    """Cualquier audio → float32 mono a `sr` Hz."""
    res = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(ruta), "-f", "f32le", "-ac", "1",
         "-ar", str(sr), "-af", "aresample=resampler=soxr", "-"],
        capture_output=True,
    )
    if res.returncode != 0:
        raise RuntimeError(f"No pude leer {ruta}: {res.stderr.decode()[-500:]}")
    return np.frombuffer(res.stdout, dtype=np.float32).copy()


def desde_pcm(pcm: np.ndarray, sr_origen: int, sr: int = SR) -> np.ndarray:
    if sr_origen == sr:
        return pcm.astype(np.float32)
    res = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "f32le", "-ar", str(sr_origen), "-ac", "1",
         "-i", "-", "-f", "f32le", "-ar", str(sr), "-af", "aresample=resampler=soxr", "-"],
        input=pcm.astype(np.float32).tobytes(), capture_output=True,
    )
    return np.frombuffer(res.stdout, dtype=np.float32).copy()


def escribir(ruta: str | Path, audio: np.ndarray, sr: int = SR) -> Path:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(datos.tobytes())
    return ruta


def bordes_voz(audio: np.ndarray, sr: int = SR, umbral_db: float = -42.0) -> tuple[int, int]:
    """Primera y última muestra con voz (ventanas de 10 ms)."""
    if audio.size == 0:
        return 0, 0
    v = int(sr * 0.01)
    n = len(audio) // v
    if n == 0:
        return 0, len(audio)
    rms = np.sqrt(np.mean(audio[: n * v].reshape(n, v) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    umbral = max(umbral_db, db.max() - 45)
    activos = np.nonzero(db > umbral)[0]
    if activos.size == 0:
        return 0, len(audio)
    return int(activos[0] * v), int(min(len(audio), (activos[-1] + 1) * v))


def recortar(audio: np.ndarray, sr: int = SR, antes: float = 0.03, despues: float = 0.08) -> tuple[np.ndarray, float]:
    """Quita silencios de los bordes. Devuelve (audio, segundos quitados al principio)."""
    a, b = bordes_voz(audio, sr)
    a = max(0, a - int(antes * sr))
    b = min(len(audio), b + int(despues * sr))
    return audio[a:b], a / sr


def silencio(seg: float, sr: int = SR) -> np.ndarray:
    return np.zeros(int(round(seg * sr)), dtype=np.float32)


def duracion(ruta: str | Path) -> float:
    res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(ruta)],
                         capture_output=True, text=True)
    return float(res.stdout.strip() or 0)


def sonoridad(ruta: str | Path) -> dict:
    """Loudness integrado (LUFS) y pico real (dBTP) con el filtro loudnorm."""
    res = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(ruta), "-af", "loudnorm=print_format=json", "-f", "null", "-"],
                         capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", res.stderr, re.S)
    if not m:
        return {}
    d = json.loads(m.group(0))
    return {"lufs": float(d["input_i"]), "pico_db": float(d["input_tp"]), "lra": float(d["input_lra"]),
            "umbral": float(d["input_thresh"])}


def mezclar(voz: Path, salida: Path, musica: Path | None = None, musica_db: float = -22.0,
            lufs: float = -14.0) -> Path:
    """Voz tratada + música agachada bajo la voz, normalizado a `lufs` en dos pasadas."""
    cadena_voz = "highpass=f=75,acompressor=threshold=-20dB:ratio=3:attack=8:release=120:makeup=2.5,alimiter=limit=0.95"
    tmp = salida.with_suffix(".premezcla.wav")
    if musica:
        filtro = (
            f"[0:a]{cadena_voz},asplit=2[v][sc];"
            f"[1:a]volume={musica_db}dB,afade=t=in:d=2[m];"
            f"[m][sc]sidechaincompress=threshold=0.03:ratio=6:attack=30:release=450[md];"
            f"[v][md]amix=inputs=2:duration=first:normalize=0[out]"
        )
        ffmpeg("-i", str(voz), "-stream_loop", "-1", "-i", str(musica), "-filter_complex", filtro,
               "-map", "[out]", "-ar", str(SR), "-ac", "2", str(tmp))
    else:
        ffmpeg("-i", str(voz), "-af", cadena_voz, "-ar", str(SR), "-ac", "2", str(tmp))
    m = sonoridad(tmp)
    if m:
        ln = (f"loudnorm=I={lufs}:TP=-1.5:LRA=11:measured_I={m['lufs']}:measured_TP={m['pico_db']}:"
              f"measured_LRA={m['lra']}:measured_thresh={m['umbral']}:linear=true")
    else:
        ln = f"loudnorm=I={lufs}:TP=-1.5:LRA=11"
    total = duracion(voz)
    ffmpeg("-i", str(tmp), "-af", f"{ln},afade=t=out:st={max(0.0, total - 1.2):.2f}:d=1.2", "-ar", str(SR),
           "-ac", "2", "-c:a", "pcm_s16le", str(salida))
    tmp.unlink(missing_ok=True)
    return salida
