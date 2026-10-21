"""Voz en español con Piper (modelo local; voces en data/voces, descargadas con
`python -m piper.download_voices --data-dir data/voces es_ES-davefx-medium`).

Se sintetiza frase a frase para conocer la duración exacta de cada una; dentro de la frase, el tiempo de
cada palabra se reparte en proporción a su longitud (suficiente para subtítulos de 2-3 palabras)."""
from __future__ import annotations

import array
import os
import wave
from dataclasses import dataclass
from pathlib import Path

DEFAULT_VOICE = "es_ES-davefx-medium"  # CC0
VOICES_DIR = Path(__file__).resolve().parents[2] / "data" / "voces"
PAUSE = 0.18  # silencio entre frases, en segundos


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class Speech:
    samples: array.array  # PCM 16 bits mono
    rate: int
    words: list[Word]

    @property
    def duration(self) -> float:
        return len(self.samples) / self.rate

    def save(self, path: Path) -> None:
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.rate)
            w.writeframes(self.samples.tobytes())


def _words_in(sentence: str, start: float, end: float) -> list[Word]:
    tokens = sentence.split()
    weights = [len(t) + 1 for t in tokens]
    total, t, out = sum(weights) or 1, start, []
    for tok, w in zip(tokens, weights):
        d = (end - start) * w / total
        out.append(Word(tok, t, t + d))
        t += d
    return out


def synthesize(sentences: list[str], voice: str | None = None, speed: float = 0.92) -> Speech:
    from piper import PiperVoice, SynthesisConfig

    name = voice or os.environ.get("VIDEO_VOICE", "").strip() or DEFAULT_VOICE
    model = VOICES_DIR / f"{name}.onnx"
    if not model.exists():
        raise FileNotFoundError(f"Falta la voz {name}: python -m piper.download_voices --data-dir data/voces {name}")
    pv = PiperVoice.load(str(model))
    cfg = SynthesisConfig(length_scale=speed)
    rate = pv.config.sample_rate
    pcm, words = array.array("h"), []
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        start = len(pcm) / rate
        for chunk in pv.synthesize(sentence, syn_config=cfg):
            pcm.frombytes(chunk.audio_int16_bytes)
        words += _words_in(sentence, start, len(pcm) / rate)
        pcm.extend([0] * int(PAUSE * rate))
    return Speech(pcm, rate, words)


ELEVEN_API = "https://api.elevenlabs.io/v1"


def synthesize_elevenlabs(sentences: list[str], voice_id: str | None = None, model: str | None = None) -> Speech:
    """Voz de ElevenLabs (ELEVENLABS_API_KEY y ELEVENLABS_VOICE_ID en .env). Todo el guion va en una sola
    llamada para que la entonación sea natural; ElevenLabs devuelve el tiempo de cada carácter, de donde
    salen los tiempos exactos de cada palabra. Modelo por defecto: eleven_v3 (el más expresivo)."""
    import base64
    import json
    import subprocess
    import urllib.error
    import urllib.request

    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    vid = voice_id or os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
    if not key or not vid:
        raise RuntimeError("Faltan ELEVENLABS_API_KEY o ELEVENLABS_VOICE_ID en .env")
    text = " ".join(s.strip() for s in sentences if s.strip())
    models = [model or os.environ.get("ELEVENLABS_MODEL", "").strip() or "eleven_v3", "eleven_multilingual_v2"]
    last_error = ""
    for m in dict.fromkeys(models):
        body = json.dumps({"text": text, "model_id": m, "language_code": "es"}).encode("utf-8")
        req = urllib.request.Request(f"{ELEVEN_API}/text-to-speech/{vid}/with-timestamps?output_format=mp3_44100_128",
                                     data=body, method="POST",
                                     headers={"xi-api-key": key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            last_error = f"HTTP {e.code} {e.read()[:200].decode('utf-8', 'replace')}"
    else:
        raise RuntimeError(f"ElevenLabs no generó la voz: {last_error}")
    mp3 = base64.b64decode(data["audio_base64"])
    rate = 44100
    pcm_bytes = subprocess.run(["ffmpeg", "-v", "error", "-i", "-", "-f", "s16le", "-ac", "1", "-ar", str(rate), "-"],
                               input=mp3, capture_output=True, check=True).stdout
    pcm = array.array("h")
    pcm.frombytes(pcm_bytes[: len(pcm_bytes) // 2 * 2])
    # «alignment» sigue el texto original (las palabras cuadran con el guion); la normalizada puede expandir cifras.
    al = data.get("alignment") or data["normalized_alignment"]
    chars, starts, ends = al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]
    words, cur, cs = [], "", 0.0
    for ch, s, e in zip(chars, starts, ends):
        if ch.isspace():
            if cur:
                words.append(Word(cur, cs, prev_end))
                cur = ""
            continue
        if not cur:
            cs = s
        cur += ch
        prev_end = e
    if cur:
        words.append(Word(cur, cs, prev_end))
    pcm.extend([0] * int(0.4 * rate))
    return Speech(pcm, rate, words)


FISH_API = "https://api.fish.audio/v1/tts"


def synthesize_fish(sentences: list[str], voice_id: str | None = None) -> Speech:
    """Voz de Fish Audio (FISH_API_KEY y FISH_VOICE_ID en .env; modelo FISH_MODEL, por defecto el gratuito
    s2.1-pro-free). Frase a frase, como Piper, para conocer la duración de cada una."""
    import json
    import subprocess
    import urllib.error
    import urllib.request

    key = os.environ.get("FISH_API_KEY", "").strip()
    vid = voice_id or os.environ.get("FISH_VOICE_ID", "").strip()
    if not key:
        raise RuntimeError("Falta FISH_API_KEY en .env")
    model = os.environ.get("FISH_MODEL", "").strip() or "s2.1-pro-free"
    rate = 44100
    pcm, words = array.array("h"), []
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        body = {"text": sentence, "format": "mp3"}
        if vid:
            body["reference_id"] = vid
        req = urllib.request.Request(FISH_API, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                              "model": model})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                mp3 = r.read()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Fish Audio no generó la voz: HTTP {e.code} {e.read()[:200].decode('utf-8', 'replace')}")
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", "-", "-f", "s16le", "-ac", "1", "-ar", str(rate), "-"],
                             input=mp3, capture_output=True, check=True).stdout
        start = len(pcm) / rate
        pcm.frombytes(raw[: len(raw) // 2 * 2])
        words += _words_in(sentence, start, len(pcm) / rate)
        pcm.extend([0] * int(PAUSE * rate))
    return Speech(pcm, rate, words)


def speak(sentences: list[str], voice_name: str | None = None) -> Speech:
    """Motor según VIDEO_TTS (elevenlabs | fish | piper); sin él, el primero con clave en .env y si no, Piper local."""
    engine = os.environ.get("VIDEO_TTS", "").strip().lower()
    if engine == "elevenlabs" or (not engine and os.environ.get("ELEVENLABS_API_KEY")):
        return synthesize_elevenlabs(sentences)
    if engine == "fish" or (not engine and os.environ.get("FISH_API_KEY")):
        return synthesize_fish(sentences)
    return synthesize(sentences, voice_name)


def loudness(speech: Speech, fps: int) -> list[float]:
    """Volumen (0-1) por fotograma, para mover la boca de la mascota."""
    per = max(1, speech.rate // fps)
    vals = []
    for i in range(0, len(speech.samples), per):
        block = speech.samples[i:i + per]
        vals.append((sum(abs(s) for s in block) / len(block)) if block else 0.0)
    peak = sorted(vals)[int(len(vals) * 0.95)] if vals else 1
    return [min(1.0, v / peak) if peak else 0.0 for v in vals]
