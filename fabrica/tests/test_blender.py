import json
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from fabrica.agentes import Contexto, ErrorAgente
from fabrica.agentes.blender import AgenteBlender, buscar_blender
from fabrica.agentes.simulado import caja_gltf
from fabrica.plan import Tarea


def tarea(**datos) -> Tarea:
    return Tarea(id="ren/limpieza", tipo="limpieza", titulo="", proveedor="blender", requiere_aprobacion=False, datos=datos)


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.modelo = self.base / "modelo.gltf"
        self.modelo.write_text(json.dumps(caja_gltf("Prueba")), encoding="utf-8")
        self.salida = self.base / "salida"
        self.salida.mkdir()

    def ctx(self, **datos) -> Contexto:
        return Contexto(tarea=tarea(**datos), juego="", estilo="", carpeta=self.salida, entradas={"ren/modelo3d": [self.modelo]})


class TestAgenteBlender(Base):
    def test_sin_blender_explica_como_instalarlo(self):
        self.assertIn("blender.org", AgenteBlender(ejecutable="").disponible())

    def test_lanza_blender_y_lee_el_informe(self):
        llamadas = []

        def ejecutar(orden, **kwargs):
            llamadas.append(orden)
            opciones = json.loads(orden[-1])
            Path(opciones["salida"]).write_bytes(b"glTF")
            Path(opciones["vista"]).write_bytes(b"png")
            informe = {"caras_antes": 90000, "caras_despues": 60000, "altura_final": 1.6}
            return subprocess.CompletedProcess(orden, 0, stdout="algo\nINFORME: " + json.dumps(informe), stderr="")

        resultado = AgenteBlender(ejecutable="/ruta/blender", ejecutar=ejecutar).generar(self.ctx(altura=1.6))
        orden = llamadas[0]
        self.assertEqual(orden[:4], ["/ruta/blender", "--background", "--factory-startup", "--python"])
        opciones = json.loads(orden[-1])
        self.assertEqual(opciones["altura"], 1.6)
        self.assertEqual(opciones["entrada"], str(self.modelo))
        self.assertEqual([a.name for a in resultado.archivos], ["modelo_limpio.glb", "vista.png"])
        self.assertIn("90000 → 60000 caras", resultado.nota)

    def test_si_blender_falla_se_ve_por_que(self):
        def ejecutar(orden, **kwargs):
            return subprocess.CompletedProcess(orden, 1, stdout="", stderr="Traceback\nRuntimeError: archivo dañado")

        with self.assertRaisesRegex(ErrorAgente, "archivo dañado"):
            AgenteBlender(ejecutable="/ruta/blender", ejecutar=ejecutar).generar(self.ctx())


@unittest.skipUnless(buscar_blender(), "Blender no está instalado (o define BLENDER con su ruta)")
class TestBlenderDeVerdad(Base):
    def test_escala_apoya_en_el_suelo_y_hace_vista_previa(self):
        resultado = AgenteBlender(limite=300).generar(self.ctx(altura=2.0))
        glb = resultado.archivos[0].read_bytes()
        self.assertEqual(glb[:4], b"glTF")
        largo_json = struct.unpack("<I", glb[12:16])[0]
        gltf = json.loads(glb[20:20 + largo_json])
        posicion = gltf["meshes"][0]["primitives"][0]["attributes"]["POSITION"]
        acceso = gltf["accessors"][posicion]
        self.assertAlmostEqual(acceso["min"][1], 0.0, places=3)  # apoyado en el suelo (Y arriba en glTF)
        self.assertAlmostEqual(acceso["max"][1], 2.0, places=3)  # con la altura pedida
        self.assertAlmostEqual(acceso["min"][0] + acceso["max"][0], 0.0, places=3)  # centrado
        self.assertTrue((self.salida / "vista.png").stat().st_size > 1000)
        self.assertIn("Altura 2 m", resultado.nota)
