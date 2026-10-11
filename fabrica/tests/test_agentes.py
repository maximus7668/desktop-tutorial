import base64
import io
import json
import struct
import tempfile
import unittest
import urllib.error
import wave
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

from fabrica.agentes import Contexto, ErrorAgente
from fabrica.agentes import elevenlabs
from fabrica.agentes.elevenlabs import AgenteElevenLabs
from fabrica.agentes.simulado import caja_gltf, escribir_tono, hoja_concepto
from fabrica.plan import Tarea


def tarea(tipo: str, id_: str, **datos) -> Tarea:
    return Tarea(id=id_, tipo=tipo, titulo=id_, proveedor="elevenlabs", requiere_aprobacion=False, datos=datos)


class HttpFalso:
    def __init__(self, respuesta: bytes = b"ID3audio"):
        self.llamadas: list[tuple[str, dict, dict, float]] = []
        self.respuesta = respuesta

    def __call__(self, url, cuerpo, cabeceras, espera):
        self.llamadas.append((url, cuerpo, cabeceras, espera))
        return self.respuesta


class TestElevenLabs(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.carpeta = Path(self._tmp.name)
        self.http = HttpFalso()
        self.agente = AgenteElevenLabs(clave="clave-secreta", http=self.http)

    def ctx(self, t: Tarea, **extra) -> Contexto:
        return Contexto(tarea=t, juego="Prueba", estilo="anime", carpeta=self.carpeta, **extra)

    def test_disponible_segun_la_clave(self):
        self.assertIn("ELEVENLABS_API_KEY", AgenteElevenLabs(clave="").disponible())
        self.assertIsNone(self.agente.disponible())

    def test_voz(self):
        t = tarea("voz", "ren/voz/grito", personaje="Ren", texto="¡Ya!", voz="", voz_id="abc/1")
        resultado = self.agente.generar(self.ctx(t, intento=3))
        url, cuerpo, cabeceras, _ = self.http.llamadas[0]
        self.assertEqual(url, "https://api.elevenlabs.io/v1/text-to-speech/abc%2F1?output_format=mp3_44100_128")
        self.assertEqual(cuerpo, {"text": "¡Ya!", "model_id": "eleven_multilingual_v2", "seed": 3})
        self.assertEqual(cabeceras["xi-api-key"], "clave-secreta")
        self.assertEqual(resultado.archivos[0].name, "grito.mp3")
        self.assertEqual(resultado.archivos[0].read_bytes(), b"ID3audio")

    def test_voz_sin_voz_id(self):
        t = tarea("voz", "ren/voz/grito", personaje="Ren", texto="¡Ya!", voz="", voz_id="")
        with self.assertRaisesRegex(ErrorAgente, "Falta voz_id de Ren"):
            self.agente.generar(self.ctx(t))
        self.assertEqual(self.http.llamadas, [])

    def test_sonido_con_motivo_de_rechazo(self):
        t = tarea("sonido", "sonido/impacto", descripcion="punch impact", duracion=0.6)
        self.agente.generar(self.ctx(t, motivo_rechazo="more bass"))
        url, cuerpo, _, _ = self.http.llamadas[0]
        self.assertEqual(url, "https://api.elevenlabs.io/v1/sound-generation?output_format=mp3_44100_128")
        self.assertEqual(cuerpo["text"], "punch impact. more bass")
        self.assertEqual(cuerpo["duration_seconds"], 0.6)
        self.assertEqual(cuerpo["model_id"], "eleven_text_to_sound_v2")

    def test_sonido_en_bucle(self):
        t = tarea("sonido", "sonido/carga", descripcion="aura", duracion=4.0, bucle=True)
        self.agente.generar(self.ctx(t))
        self.assertIs(self.http.llamadas[0][1]["loop"], True)
        t = tarea("sonido", "sonido/golpe", descripcion="punch", duracion=0.6)
        self.agente.generar(self.ctx(t))
        self.assertNotIn("loop", self.http.llamadas[1][1])

    def test_sonido_demasiado_largo(self):
        t = tarea("sonido", "sonido/lluvia", descripcion="rain", duracion=45.0)
        with self.assertRaisesRegex(ErrorAgente, "de 0,5 a 30 segundos"):
            self.agente.generar(self.ctx(t))

    def test_musica(self):
        t = tarea("musica", "musica/tema", descripcion="battle theme", duracion=90.0, instrumental=True)
        self.agente.generar(self.ctx(t))
        url, cuerpo, _, espera = self.http.llamadas[0]
        self.assertTrue(url.startswith("https://api.elevenlabs.io/v1/music"))
        self.assertEqual(cuerpo, {"prompt": "battle theme", "force_instrumental": True, "music_length_ms": 90000})
        self.assertGreaterEqual(espera, 300)

    def test_audio_vacio(self):
        agente = AgenteElevenLabs(clave="k", http=HttpFalso(b""))
        t = tarea("sonido", "sonido/impacto", descripcion="punch", duracion=None)
        with self.assertRaisesRegex(ErrorAgente, "vacío"):
            agente.generar(self.ctx(t))

    def test_error_http_se_explica_sin_mostrar_la_clave(self):
        error = urllib.error.HTTPError(
            "https://api.elevenlabs.io/v1/music", 401, "Unauthorized", {}, io.BytesIO(b'{"detail":"invalid_api_key"}')
        )
        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(ErrorAgente) as caso:
                elevenlabs._post("https://api.elevenlabs.io/v1/music", {}, {"xi-api-key": "clave-secreta"}, 5)
        self.assertIn("401", str(caso.exception))
        self.assertIn("invalid_api_key", str(caso.exception))
        self.assertNotIn("clave-secreta", str(caso.exception))


class TestSimulado(unittest.TestCase):
    def test_caja_gltf_valida(self):
        g = caja_gltf("Ren")
        buffer = base64.b64decode(g["buffers"][0]["uri"].split(",", 1)[1])
        self.assertEqual(len(buffer), g["buffers"][0]["byteLength"])
        indices = struct.unpack("<36H", buffer[:72])
        posiciones = struct.unpack("<24f", buffer[72:])
        self.assertEqual(max(indices), 7)
        acc = g["accessors"][1]
        for eje in range(3):
            self.assertEqual(min(posiciones[eje::3]), acc["min"][eje])
            self.assertEqual(max(posiciones[eje::3]), acc["max"][eje])
        json.dumps(g)  # serializable tal cual

    def test_tono_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "t.wav"
            escribir_tono(ruta, 440, 0.5)
            with wave.open(str(ruta)) as w:
                self.assertAlmostEqual(w.getnframes() / w.getframerate(), 0.5, places=2)

    def test_hoja_concepto_escapa_el_nombre(self):
        svg = hoja_concepto("<Ren & Co>", 2, "más rojo")
        ET.fromstring(svg)
        self.assertIn("&lt;Ren &amp; Co&gt;", svg)
        self.assertIn("intento 2", svg)
