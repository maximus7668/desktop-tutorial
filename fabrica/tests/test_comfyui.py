import json
import tempfile
import unittest
import urllib.parse
from pathlib import Path

from fabrica.agentes import Contexto, ErrorAgente
from fabrica.agentes.comfyui import AgenteComfyUI, rellenar
from fabrica.director import Director
from fabrica.diseno import ErrorDiseno
from fabrica.plan import Tarea

from .util import MINIMO, ConProyecto

PNG = b"\x89PNG\r\n\x1a\nconcepto"


class ComfyFalso:
    """Responde como el server.py de ComfyUI: /prompt, /history/<id>, /view y /system_stats."""

    def __init__(self, consultas_hasta_terminar=2, error=None, imagenes=1):
        self.llamadas: list[tuple[str, str, dict | None]] = []
        self.consultas = 0
        self.consultas_hasta_terminar = consultas_hasta_terminar
        self.error = error
        self.imagenes = imagenes

    def __call__(self, metodo, url, cuerpo, cabeceras, espera):
        datos = json.loads(cuerpo) if cuerpo else None
        self.llamadas.append((metodo, url, datos))
        ruta = urllib.parse.urlparse(url)
        if ruta.path == "/system_stats":
            return 200, b'{"system": {}}'
        if ruta.path == "/prompt":
            return 200, json.dumps({"prompt_id": "p-1", "number": 1, "node_errors": {}}).encode()
        if ruta.path.startswith("/history/"):
            self.consultas += 1
            if self.consultas < self.consultas_hasta_terminar:
                return 200, b"{}"
            if self.error:
                estado = {"status_str": "error", "completed": False, "messages": [["execution_error", {"node_type": "CheckpointLoaderSimple", "exception_message": self.error}]]}
                return 200, json.dumps({"p-1": {"outputs": {}, "status": estado}}).encode()
            imagenes = [{"filename": f"concepto_{i:05}_.png", "subfolder": "fabrica", "type": "output"} for i in range(self.imagenes)]
            return 200, json.dumps({"p-1": {"outputs": {"9": {"images": imagenes}}, "status": {"status_str": "success", "completed": True, "messages": []}}}).encode()
        if ruta.path == "/view":
            return 200, PNG
        return 404, b"{}"

    def flujo_enviado(self) -> dict:
        return next(d for m, u, d in self.llamadas if u.endswith("/prompt"))["prompt"]


class TestComfyUI(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def ctx(self, **extra) -> Contexto:
        t = Tarea(id="ren/concepto", tipo="concepto", titulo="", proveedor="comfyui", requiere_aprobacion=False,
                  datos={"personaje": "Ren", "descripcion": "Pelo rojo en punta.", "estilo": "Anime."})
        return Contexto(tarea=t, juego="", estilo="", carpeta=self.base, proyecto=self.base, **extra)

    def agente(self, api, **ajustes) -> AgenteComfyUI:
        ajustes.setdefault("modelo", "animagine.safetensors")
        return AgenteComfyUI(transporte=api, dormir=lambda s: None, **ajustes)

    def test_rellena_el_flujo_y_guarda_la_imagen(self):
        api = ComfyFalso()
        resultado = self.agente(api).generar(self.ctx())
        flujo = api.flujo_enviado()
        self.assertEqual(flujo["4"]["inputs"]["ckpt_name"], "animagine.safetensors")
        self.assertIn("Pelo rojo en punta", flujo["6"]["inputs"]["text"])
        self.assertIn("A-pose", flujo["6"]["inputs"]["text"])
        self.assertIsInstance(flujo["3"]["inputs"]["seed"], int)
        self.assertEqual(flujo["5"]["inputs"]["width"], 832)
        self.assertEqual(resultado.archivos[0].name, "concepto.png")
        self.assertEqual(resultado.archivos[0].read_bytes(), PNG)
        vista = next(u for m, u, d in api.llamadas if "/view" in u)
        self.assertIn("subfolder=fabrica", vista)

    def test_varias_imagenes(self):
        resultado = self.agente(ComfyFalso(imagenes=2)).generar(self.ctx())
        self.assertEqual([a.name for a in resultado.archivos], ["concepto.png", "concepto_2.png"])

    def test_otra_semilla_al_rechazar(self):
        api1, api2 = ComfyFalso(), ComfyFalso()
        self.agente(api1).generar(self.ctx())
        self.agente(api2).generar(self.ctx(motivo_rechazo="más musculoso"))
        self.assertNotEqual(api1.flujo_enviado()["3"]["inputs"]["seed"], api2.flujo_enviado()["3"]["inputs"]["seed"])
        self.assertIn("más musculoso", api2.flujo_enviado()["6"]["inputs"]["text"])

    def test_error_de_ejecucion_se_explica_y_se_pide_de_nuevo(self):
        memoria: dict = {}
        with self.assertRaisesRegex(ErrorAgente, "CheckpointLoaderSimple: no encuentro el modelo"):
            self.agente(ComfyFalso(error="no encuentro el modelo")).generar(self.ctx(memoria=memoria))
        self.assertNotIn("tarea", memoria)

    def test_flujo_propio_relativo_al_proyecto(self):
        (self.base / "flujos").mkdir()
        (self.base / "flujos" / "mio.json").write_text(json.dumps({"1": {"class_type": "SaveImage", "inputs": {"filename_prefix": "{{PROMPT}}"}}}), encoding="utf-8")
        api = ComfyFalso()
        self.agente(api, flujo="flujos/mio.json", modelo="").generar(self.ctx())
        self.assertIn("Pelo rojo", api.flujo_enviado()["1"]["inputs"]["filename_prefix"])

    def test_flujo_en_formato_de_interfaz_se_rechaza(self):
        (self.base / "ui.json").write_text(json.dumps({"nodes": [], "links": []}), encoding="utf-8")
        with self.assertRaisesRegex(ErrorAgente, "formato API"):
            self.agente(ComfyFalso(), flujo="ui.json").generar(self.ctx())

    def test_disponible(self):
        self.assertIn("Falta el modelo", AgenteComfyUI(transporte=ComfyFalso()).disponible())
        self.assertIsNone(self.agente(ComfyFalso()).disponible())

        def caido(*args):
            raise OSError("connection refused")

        self.assertIn("no responde", self.agente(caido).disponible())

    def test_error_al_encolar_es_legible(self):
        def transporte(metodo, url, cuerpo, cabeceras, espera):
            return 400, json.dumps({
                "error": {"type": "prompt_outputs_failed_validation", "message": "Prompt outputs failed validation", "details": ""},
                "node_errors": {"4": {"errors": [{"message": "Value not in list", "details": "ckpt_name: 'x' not in []"}]}},
            }).encode()

        with self.assertRaisesRegex(ErrorAgente, "Value not in list: ckpt_name"):
            self.agente(transporte).generar(self.ctx())

    def test_ajustes_invalidos(self):
        with self.assertRaisesRegex(ValueError, "múltiplo de 8"):
            AgenteComfyUI(ancho=1001)
        with self.assertRaisesRegex(ValueError, "http"):
            AgenteComfyUI(servidor="localhost:8188")

    def test_rellenar(self):
        self.assertEqual(rellenar({"a": "{{N}}", "b": ["x {{T}} y", "{{OTRA}}"]}, {"N": 3, "T": "z"}), {"a": 3, "b": ["x z y", "{{OTRA}}"]})


class TestAjustesDeProveedores(ConProyecto):
    def con(self, texto: str) -> None:
        self.escribir(MINIMO.replace("intentos_max = 2", "intentos_max = 2\n\n" + texto))

    def test_ajuste_desconocido(self):
        self.con('[fabrica.meshy]\ncaraz = 10000')
        with self.assertRaisesRegex(ErrorDiseno, "no conozco el ajuste 'caraz'"):
            Director(self.carpeta)

    def test_proveedor_desconocido(self):
        self.con('[fabrica.mesy]\ncaras = 10000')
        with self.assertRaisesRegex(ErrorDiseno, r"\[fabrica.mesy\]: no existe"):
            Director(self.carpeta)

    def test_valor_invalido_sale_al_empezar(self):
        self.con('[fabrica.proveedores]\nconcepto = "comfyui"\n\n[fabrica.comfyui]\nmodelo = "x.safetensors"\nancho = 1001')
        with self.assertRaisesRegex(ErrorDiseno, r"\[fabrica.comfyui\]: ancho"):
            Director(self.carpeta)

    def test_cambiar_ajustes_rehace_solo_lo_de_ese_proveedor(self):
        self.con('[fabrica.proveedores]\nconcepto = "comfyui"\n\n[fabrica.comfyui]\nmodelo = "a.safetensors"')
        antes = {t.id: t.huella for t in Director(self.carpeta).tareas}
        self.con('[fabrica.proveedores]\nconcepto = "comfyui"\n\n[fabrica.comfyui]\nmodelo = "b.safetensors"')
        despues = {t.id: t.huella for t in Director(self.carpeta).tareas}
        self.assertNotEqual(antes["ren/concepto"], despues["ren/concepto"])
        self.assertEqual(antes["ren/voz/grito"], despues["ren/voz/grito"])

    def test_tabla_con_otro_valor_explica_donde_van_los_ajustes(self):
        self.con('[fabrica.otra]\nx = 1')
        self.escribir(MINIMO.replace("intentos_max = 2", 'intentos_max = 2\nmodelo = "x"'))
        with self.assertRaisesRegex(ErrorDiseno, r"\[fabrica.modelo\]"):
            Director(self.carpeta)


class TestComfyUIPorRed(unittest.TestCase):
    """Igual que arriba, pero con un servidor HTTP local de verdad y el transporte real (urllib)."""

    def setUp(self):
        import http.server
        import threading

        falso = ComfyFalso()

        class Manejador(http.server.BaseHTTPRequestHandler):
            def _responder(self):
                largo = int(self.headers.get("Content-Length") or 0)
                cuerpo = self.rfile.read(largo) if largo else None
                codigo, datos = falso(self.command, f"http://127.0.0.1{self.path}", cuerpo, dict(self.headers), 5)
                self.send_response(codigo)
                self.end_headers()
                self.wfile.write(datos)

            do_GET = _responder
            do_POST = _responder

            def log_message(self, *args):
                pass

        self.servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        self.addCleanup(self.servidor.shutdown)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def test_de_punta_a_punta(self):
        puerto = self.servidor.server_address[1]
        agente = AgenteComfyUI(servidor=f"http://127.0.0.1:{puerto}", modelo="m.safetensors", dormir=lambda s: None)
        self.assertIsNone(agente.disponible())
        t = Tarea(id="ren/concepto", tipo="concepto", titulo="", proveedor="comfyui", requiere_aprobacion=False,
                  datos={"personaje": "Ren", "descripcion": "x", "estilo": "y"})
        resultado = agente.generar(Contexto(tarea=t, juego="", estilo="", carpeta=self.base))
        self.assertEqual(resultado.archivos[0].read_bytes(), PNG)
