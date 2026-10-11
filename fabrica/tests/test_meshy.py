import base64
import json
import tempfile
import unittest
from pathlib import Path

from fabrica.agentes import Contexto, ErrorAgente
from fabrica.agentes.meshy import AgenteMeshy
from fabrica.director import Director
from fabrica.plan import Tarea
from fabrica.registro import ERROR

from .util import MINIMO, ConProyecto

PNG = b"\x89PNG\r\n\x1a\nimagen"
GLB = b"glTF\x02\x00\x00\x00modelo"


class MeshyFalso:
    """Imita la API de Meshy: cada tarea devuelve una lista de estados, uno por consulta."""

    def __init__(self, estados_por_ruta: dict[str, list[dict]] | None = None):
        self.llamadas: list[tuple[str, str, dict | None, dict]] = []
        self.estados_por_ruta = estados_por_ruta or {}
        self.tareas: dict[str, list[dict]] = {}

    def __call__(self, metodo, url, cuerpo, cabeceras, espera):
        self.llamadas.append((metodo, url, json.loads(cuerpo) if cuerpo else None, cabeceras))
        if url.startswith("https://archivos/"):
            return 200, PNG if url.endswith(".png") else GLB
        ruta = url.removeprefix("https://api.meshy.ai")
        if metodo == "POST":
            id_tarea = f"t{len(self.tareas) + 1}"
            self.tareas[id_tarea] = list(self.estados_por_ruta.get(ruta, [{"status": "SUCCEEDED"}]))
            return 200, json.dumps({"result": id_tarea}).encode()
        id_tarea = ruta.rsplit("/", 1)[1]
        estados = self.tareas[id_tarea]
        estado = estados.pop(0) if len(estados) > 1 else estados[0]
        return 200, json.dumps(estado).encode()

    def posts(self) -> list[tuple[str, dict]]:
        return [(url, cuerpo) for metodo, url, cuerpo, _ in self.llamadas if metodo == "POST"]


class Reloj:
    def __init__(self):
        self.ahora = 0.0

    def __call__(self) -> float:
        return self.ahora

    def dormir(self, segundos: float) -> None:
        self.ahora += segundos


def tarea(tipo: str, id_: str, **datos) -> Tarea:
    return Tarea(id=id_, tipo=tipo, titulo=id_, proveedor="meshy", requiere_aprobacion=False, datos=datos)


class TestMeshy(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.carpeta = Path(self._tmp.name)

    def agente(self, api: MeshyFalso, limite: float = 900.0) -> AgenteMeshy:
        reloj = Reloj()
        return AgenteMeshy(clave="clave-secreta", transporte=api, dormir=reloj.dormir, reloj=reloj, limite=limite)

    def ctx(self, t: Tarea, **extra) -> Contexto:
        return Contexto(tarea=t, juego="Prueba", estilo="anime", carpeta=self.carpeta, **extra)

    def test_otro_rechazo_pide_otra_tarea_aunque_repita_el_motivo(self):
        api = MeshyFalso({"/openapi/v1/text-to-image": [
            {"status": "SUCCEEDED", "image_urls": ["https://archivos/concepto.png"]},
        ]})
        t = tarea("concepto", "ren/concepto", personaje="Ren", descripcion="x", estilo="y")
        memoria: dict = {}
        agente = self.agente(api)
        agente.generar(self.ctx(t, memoria=memoria, motivo_rechazo="más alto", rechazos=1))
        agente.generar(self.ctx(t, memoria=memoria, motivo_rechazo="más alto", rechazos=1))  # se retoma
        self.assertEqual(len(api.posts()), 1)
        agente.generar(self.ctx(t, memoria=memoria, motivo_rechazo="más alto", rechazos=2))
        self.assertEqual(len(api.posts()), 2)

    def test_disponible_segun_la_clave(self):
        self.assertIn("MESHY_API_KEY", AgenteMeshy(clave="").disponible())
        self.assertIsNone(AgenteMeshy(clave="k").disponible())

    def test_concepto(self):
        api = MeshyFalso({"/openapi/v1/text-to-image": [
            {"status": "PENDING"}, {"status": "IN_PROGRESS"},
            {"status": "SUCCEEDED", "image_urls": ["https://archivos/concepto.png"]},
        ]})
        ctx = self.ctx(tarea("concepto", "ren/concepto", personaje="Ren", descripcion="pelo rojo", estilo="Anime."))
        resultado = self.agente(api).generar(ctx)
        url, cuerpo = api.posts()[0]
        self.assertEqual(url, "https://api.meshy.ai/openapi/v1/text-to-image")
        self.assertIn("pelo rojo", cuerpo["prompt"])
        self.assertEqual(cuerpo["pose_mode"], "a-pose")
        self.assertEqual(resultado.archivos[0].name, "concepto.png")
        self.assertEqual(ctx.memoria["imagen_meshy"], "t1")
        self.assertEqual(api.llamadas[0][3]["Authorization"], "Bearer clave-secreta")

    def test_modelo_reutiliza_la_imagen_de_meshy(self):
        api = MeshyFalso({"/openapi/v1/image-to-3d": [{"status": "SUCCEEDED", "model_urls": {"glb": "https://archivos/m.glb"}, "thumbnail_url": "https://archivos/mini.png"}]})
        ctx = self.ctx(tarea("modelo3d", "ren/modelo3d", personaje="Ren", descripcion="pelo rojo"), memorias={"ren/concepto": {"imagen_meshy": "img-9"}})
        resultado = self.agente(api).generar(ctx)
        _, cuerpo = api.posts()[0]
        self.assertEqual(cuerpo["input_task_id"], "img-9")
        self.assertNotIn("image_url", cuerpo)
        self.assertEqual([a.name for a in resultado.archivos], ["modelo.glb", "miniatura.png"])
        self.assertEqual(resultado.archivos[0].read_bytes(), GLB)

    def test_modelo_sube_la_imagen_si_no_es_de_meshy(self):
        imagen = self.carpeta / "frente.png"
        imagen.write_bytes(PNG)
        api = MeshyFalso({"/openapi/v1/image-to-3d": [{"status": "SUCCEEDED", "model_urls": {"glb": "https://archivos/m.glb"}}]})
        ctx = self.ctx(tarea("modelo3d", "ren/modelo3d", descripcion="x"), entradas={"ren/concepto": [imagen]})
        self.agente(api).generar(ctx)
        _, cuerpo = api.posts()[0]
        self.assertEqual(cuerpo["image_url"], "data:image/png;base64," + base64.b64encode(PNG).decode())

    def test_modelo_rechaza_un_concepto_svg(self):
        svg = self.carpeta / "concepto.svg"
        svg.write_text("<svg/>")
        ctx = self.ctx(tarea("modelo3d", "ren/modelo3d", descripcion="x"), entradas={"ren/concepto": [svg]})
        with self.assertRaisesRegex(ErrorAgente, "PNG, JPG o WebP"):
            self.agente(MeshyFalso()).generar(ctx)

    def test_rig(self):
        modelo = self.carpeta / "limpio.glb"
        modelo.write_bytes(GLB)
        api = MeshyFalso({"/openapi/v1/rigging": [{"status": "SUCCEEDED", "result": {
            "rigged_character_glb_url": "https://archivos/rig.glb",
            "basic_animations": {"walking_glb_url": "https://archivos/andar.glb"},
        }}]})
        ctx = self.ctx(tarea("rig", "ren/rig", personaje="Ren", altura=1.62), entradas={"ren/limpieza": [modelo]})
        resultado = self.agente(api).generar(ctx)
        _, cuerpo = api.posts()[0]
        self.assertEqual(cuerpo["height_meters"], 1.62)
        self.assertTrue(cuerpo["model_url"].startswith("data:model/gltf-binary;base64,"))
        self.assertEqual([a.name for a in resultado.archivos], ["modelo_rig.glb", "andar.glb"])
        self.assertEqual(ctx.memoria["rig_meshy"], "t1")

    def test_animacion_por_defecto_y_al_rechazar(self):
        respuesta = [{"status": "SUCCEEDED", "result": {"animation_glb_url": "https://archivos/a.glb"}}]
        memorias = {"ren/rig": {"rig_meshy": "rig-1"}}
        api = MeshyFalso({"/openapi/v1/animations": respuesta})
        resultado = self.agente(api).generar(self.ctx(tarea("animacion", "ren/animacion/patada", animacion="patada"), memorias=memorias))
        self.assertEqual(api.posts()[0][1], {"rig_task_id": "rig-1", "action_id": 207})
        self.assertIn("Roundhouse_Kick", resultado.nota)
        api = MeshyFalso({"/openapi/v1/animations": respuesta})
        self.agente(api).generar(self.ctx(tarea("animacion", "ren/animacion/patada", animacion="patada"), memorias=memorias, motivo_rechazo="215"))
        self.assertEqual(api.posts()[0][1]["action_id"], 215)
        api = MeshyFalso({"/openapi/v1/animations": respuesta})
        self.agente(api).generar(self.ctx(tarea("animacion", "ren/animacion/tecnica_guren", animacion="tecnica_guren", accion=94), memorias=memorias))
        self.assertEqual(api.posts()[0][1]["action_id"], 94)

    def test_animacion_desconocida_explica_como_elegirla(self):
        ctx = self.ctx(tarea("animacion", "ren/animacion/bailar", animacion="bailar"), memorias={"ren/rig": {"rig_meshy": "r"}})
        with self.assertRaisesRegex(ErrorAgente, r"\[personajes.acciones\] bailar"):
            self.agente(MeshyFalso()).generar(ctx)

    def test_animacion_sin_esqueleto_de_meshy(self):
        ctx = self.ctx(tarea("animacion", "ren/animacion/patada", animacion="patada"))
        with self.assertRaisesRegex(ErrorAgente, 'rig = "meshy"'):
            self.agente(MeshyFalso()).generar(ctx)

    def test_si_tarda_demasiado_se_retoma_sin_pagar_otra_vez(self):
        api = MeshyFalso({"/openapi/v1/text-to-image": [
            {"status": "IN_PROGRESS"}, {"status": "IN_PROGRESS"}, {"status": "IN_PROGRESS"},
            {"status": "SUCCEEDED", "image_urls": ["https://archivos/c.png"]},
        ]})
        t = tarea("concepto", "ren/concepto", personaje="Ren", descripcion="x", estilo="y")
        memoria: dict = {}
        with self.assertRaisesRegex(ErrorAgente, "sin pagarla otra vez"):
            self.agente(api, limite=8.0).generar(self.ctx(t, memoria=memoria))
        self.assertEqual(memoria["tarea"], "t1")
        self.agente(api).generar(self.ctx(t, memoria=memoria))
        self.assertEqual(len(api.posts()), 1)

    def test_tarea_fallida_se_pide_de_nuevo_la_proxima_vez(self):
        api = MeshyFalso({"/openapi/v1/text-to-image": [{"status": "FAILED", "task_error": {"message": "contenido no permitido"}}]})
        t = tarea("concepto", "ren/concepto", personaje="Ren", descripcion="x", estilo="y")
        memoria: dict = {}
        with self.assertRaisesRegex(ErrorAgente, "contenido no permitido"):
            self.agente(api).generar(self.ctx(t, memoria=memoria))
        self.assertNotIn("tarea", memoria)

    def test_error_http_sin_mostrar_la_clave(self):
        def transporte(metodo, url, cuerpo, cabeceras, espera):
            return 402, b'{"message": "Insufficient credits"}'
        agente = AgenteMeshy(clave="clave-secreta", transporte=transporte)
        t = tarea("concepto", "ren/concepto", personaje="Ren", descripcion="x", estilo="y")
        with self.assertRaises(ErrorAgente) as caso:
            agente.generar(self.ctx(t))
        self.assertIn("402", str(caso.exception))
        self.assertIn("Insufficient credits", str(caso.exception))
        self.assertNotIn("clave-secreta", str(caso.exception))


class TestMemoriaEnElRegistro(ConProyecto):
    def test_la_memoria_se_guarda_aunque_falle_y_se_borra_al_cambiar_el_diseno(self):
        class AgenteQueRecuerda:
            nombre = "simulado"
            tipos = frozenset({"concepto", "modelo3d", "limpieza", "rig", "animacion", "voz", "sonido", "musica"})

            def disponible(self):
                return None

            def generar(self, ctx):
                ctx.memoria["tarea"] = "remota-1"
                raise ErrorAgente("Meshy sigue trabajando")

        d = Director(self.carpeta, agentes={"simulado": AgenteQueRecuerda()})
        d.ejecutar()
        self.assertEqual(d.entrada("ren/concepto").estado, ERROR)
        otra_vez = Director(self.carpeta, agentes={"simulado": AgenteQueRecuerda()})
        self.assertEqual(otra_vez.entrada("ren/concepto").memoria, {"tarea": "remota-1"})
        self.escribir(MINIMO.replace("Luchador de fuego", "Luchador de hielo"))
        cambiado = Director(self.carpeta, agentes={"simulado": AgenteQueRecuerda()})
        self.assertEqual(cambiado.entrada("ren/concepto").memoria, {})
