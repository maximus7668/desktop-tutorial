import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from fabrica.agentes.simulado import AgenteSimulado
from fabrica.panel import Panel, servidor
from fabrica.registro import APROBADO, ESPERANDO

from .test_idear import MUESTRA
from .util import MINIMO


class Lento(AgenteSimulado):
    """El simulado, pero cada tarea espera a que la prueba la suelte."""

    def __init__(self):
        self.empezado = threading.Event()
        self.soltar = threading.Event()

    def generar(self, ctx):
        self.empezado.set()
        self.soltar.wait(5)
        return super().generar(ctx)


class ClaudeFalso:
    def __init__(self, aviso=None):
        self.aviso = aviso

    def disponible(self):
        return self.aviso

    def json(self, sistema, contenido, esquema, max_tokens=16000):
        return MUESTRA


class ConPanel(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.carpeta = Path(self._tmp.name) / "mi_juego"
        self.agente = AgenteSimulado()

    def abrir(self, con_juego=True, agente=None, claude=None):
        if con_juego:
            self.carpeta.mkdir()
            (self.carpeta / "juego.toml").write_text(MINIMO, encoding="utf-8")
        self.agente = agente or self.agente
        self.panel = Panel(self.carpeta, agentes={"simulado": self.agente}, claude=lambda: claude or ClaudeFalso())
        self.srv = servidor(self.panel, puerto=0)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.puerto = self.srv.server_address[1]

    def pedir(self, metodo, ruta, datos=None, cabeceras=None):
        conexion = http.client.HTTPConnection("127.0.0.1", self.puerto, timeout=10)
        self.addCleanup(conexion.close)
        base = {"Host": f"127.0.0.1:{self.puerto}"}
        cuerpo = None
        if metodo == "POST":
            base.update({"Content-Type": "application/json", "X-Fabrica": "1"})
            cuerpo = json.dumps(datos or {}).encode()
        base.update(cabeceras or {})
        conexion.request(metodo, ruta, body=cuerpo, headers=base)
        respuesta = conexion.getresponse()
        datos = respuesta.read()
        tipo = respuesta.getheader("Content-Type") or ""
        return respuesta.status, (json.loads(datos) if tipo.startswith("application/json") else datos), respuesta

    def estado(self):
        return self.pedir("GET", "/api/estado")[1]

    def esperar_trabajo(self):
        self.panel.hilo.join(10)
        self.assertFalse(self.panel.hilo.is_alive())

    def tarea(self, id_):
        return next(t for g in self.estado()["grupos"] for t in g["tareas"] if t["id"] == id_)


class TestPanel(ConPanel):
    def test_pagina_y_seguridad(self):
        self.abrir()
        codigo, html, respuesta = self.pedir("GET", "/")
        self.assertEqual(codigo, 200)
        self.assertIn(b"model-viewer", html)
        self.assertIn("default-src 'self'", respuesta.getheader("Content-Security-Policy"))
        # Otra web que se hace pasar por el panel, o que intenta mandarle órdenes.
        self.assertEqual(self.pedir("GET", "/api/estado", cabeceras={"Host": f"malvada.com:{self.puerto}"})[0], 403)
        self.assertEqual(self.pedir("POST", "/api/ejecutar", cabeceras={"X-Fabrica": ""})[0], 403)
        self.assertEqual(self.pedir("POST", "/api/ejecutar", cabeceras={"Content-Type": "text/plain"})[0], 403)
        self.assertEqual(self.pedir("POST", "/api/no_existe")[0], 404)

    def test_ejecutar_aprobar_y_rechazar(self):
        self.abrir()
        self.assertEqual(self.pedir("POST", "/api/ejecutar")[0], 200)
        self.esperar_trabajo()
        e = self.estado()
        self.assertEqual(e["juego"], "Prueba")
        self.assertEqual(e["resumen"][ESPERANDO], 1)
        self.assertIn("Terminado.", e["mensajes"][-1])
        concepto = self.tarea("ren/concepto")
        self.assertEqual(concepto["archivos"][0]["clase"], "imagen")

        codigo, cuerpo, _ = self.pedir("POST", "/api/aprobar", {"ids": ["ren/concepto"]})
        self.assertEqual((codigo, cuerpo["aprobadas"]), (200, ["ren/concepto"]))
        self.assertEqual(self.tarea("ren/concepto")["estado"], APROBADO)

        codigo, cuerpo, _ = self.pedir("POST", "/api/rechazar", {"id": "ren/concepto", "motivo": "  "})
        self.assertEqual(codigo, 400)
        self.assertIn("motivo", cuerpo["error"])
        codigo, cuerpo, _ = self.pedir("POST", "/api/rechazar", {"id": "ren/concepto", "motivo": "más alto"})
        self.assertEqual(codigo, 200)
        self.assertEqual(self.tarea("ren/concepto")["motivo"], "más alto")

    def test_ocupado_y_parar(self):
        lento = Lento()
        self.abrir(agente=lento)
        self.pedir("POST", "/api/ejecutar")
        self.assertTrue(lento.empezado.wait(5))
        self.assertEqual(self.estado()["trabajo"], "ejecutar")
        for ruta, datos in (("/api/ejecutar", {}), ("/api/aprobar", {"todo": True}), ("/api/diseno", {"texto": MINIMO})):
            codigo, cuerpo, _ = self.pedir("POST", ruta, datos)
            self.assertEqual(codigo, 409, ruta)
            self.assertIn("Parar", cuerpo["error"])
        self.pedir("POST", "/api/parar")
        lento.soltar.set()
        self.esperar_trabajo()
        e = self.estado()
        self.assertEqual(e["trabajo"], "")
        self.assertIn("Parado.", e["mensajes"][-1])
        self.assertEqual(sum(e["resumen"].values()), 7)
        self.assertEqual(e["resumen"].get(APROBADO, 0) + e["resumen"].get(ESPERANDO, 0), 1)  # solo una tarea

    def test_archivos_solo_de_recursos(self):
        self.abrir()
        self.pedir("POST", "/api/ejecutar")
        self.esperar_trabajo()
        url = self.tarea("ren/concepto")["archivos"][0]["url"]
        codigo, datos, respuesta = self.pedir("GET", url)
        self.assertEqual(codigo, 200)
        self.assertIn(b"<svg", datos)
        self.assertEqual(respuesta.getheader("Content-Type"), "image/svg+xml")
        self.assertIn("sandbox", respuesta.getheader("Content-Security-Policy"))
        for ruta in ("/archivo/juego.toml", "/archivo/recursos/../juego.toml", "/archivo/recursos/%2e%2e/juego.toml",
                     "/archivo//etc/passwd", "/archivo/recursos/ren/no_existe.png", "/archivo/registro.json"):
            self.assertEqual(self.pedir("GET", ruta)[0], 404, ruta)

    def test_diseno_se_comprueba_antes_de_guardar(self):
        self.abrir()
        self.pedir("POST", "/api/ejecutar")
        self.esperar_trabajo()
        registro = (self.carpeta / "registro.json").read_text(encoding="utf-8")
        texto = self.pedir("GET", "/api/diseno")[1]["texto"]
        self.assertEqual(texto, MINIMO)
        for malo, error in ((texto.replace("intentos_max = 2", "intentos_max = 0"), "intentos_max"),
                            (texto.replace("intentos_max = 2", 'intentos_max = 2\n\n[fabrica.proveedores]\nconcepto = "mehsy"'),
                             "'mehsy': no existe ese proveedor"),
                            ("[juego", "TOML")):
            codigo, cuerpo, _ = self.pedir("POST", "/api/diseno", {"texto": malo})
            self.assertEqual(codigo, 400)
            self.assertIn(error, cuerpo["error"])
        self.assertEqual((self.carpeta / "juego.toml").read_text(encoding="utf-8"), MINIMO)
        self.assertEqual((self.carpeta / "registro.json").read_text(encoding="utf-8"), registro)

        codigo, _, _ = self.pedir("POST", "/api/diseno", {"texto": texto.replace('nombre = "Prueba"', 'nombre = "Otro"')})
        self.assertEqual(codigo, 200)
        self.assertEqual(self.estado()["juego"], "Otro")
        self.assertEqual(self.tarea("ren/voz/grito")["estado"], APROBADO)  # lo que no cambió, intacto

    def test_cambios_por_fuera_se_ven(self):
        self.abrir()
        self.assertEqual(self.estado()["juego"], "Prueba")
        (self.carpeta / "juego.toml").write_text(MINIMO.replace('nombre = "Prueba"', 'nombre = "Editado a mano"'), encoding="utf-8")
        self.assertEqual(self.estado()["juego"], "Editado a mano")
        (self.carpeta / "juego.toml").write_text("[juego", encoding="utf-8")
        e = self.estado()
        self.assertTrue(e["existe"])
        self.assertIn("TOML", e["error"])

    def test_montar_en_godot(self):
        self.abrir()
        self.pedir("POST", "/api/ejecutar")
        self.esperar_trabajo()
        self.pedir("POST", "/api/aprobar", {"todo": True})
        godot = Path(self._tmp.name) / "godot"
        godot.mkdir()
        codigo, cuerpo, _ = self.pedir("POST", "/api/montar", {"juego": str(godot)})
        self.assertEqual(codigo, 400)
        self.assertIn("project.godot", cuerpo["error"])
        (godot / "project.godot").write_text("", encoding="utf-8")
        codigo, cuerpo, _ = self.pedir("POST", "/api/montar", {"juego": str(godot), "incluir_simulados": True})
        self.assertEqual(codigo, 200)
        self.assertEqual(cuerpo["copiados"], 3)
        self.assertTrue((godot / "recursos_fabrica" / "indice.json").is_file())
        codigo, cuerpo, _ = self.pedir("POST", "/api/exportar")
        self.assertTrue(cuerpo["ruta"].endswith("indice_recursos.json"))


class TestPanelSinProyecto(ConPanel):
    def test_empezar_con_el_ejemplo(self):
        self.abrir(con_juego=False)
        e = self.estado()
        self.assertEqual((e["existe"], e["error"]), (False, None))
        self.assertEqual(self.pedir("POST", "/api/ejecutar")[0], 400)
        self.assertEqual(self.pedir("POST", "/api/nuevo")[0], 200)
        self.assertEqual(self.estado()["juego"], "Ryūsei Clash")
        self.assertEqual(self.pedir("POST", "/api/nuevo")[0], 400)  # no pisa el que hay

    def test_idear_con_claude(self):
        self.abrir(con_juego=False)
        self.assertEqual(self.pedir("POST", "/api/idear", {"idea": "  "})[0], 400)
        self.assertEqual(self.pedir("POST", "/api/idear", {"idea": "samuráis con rayos"})[0], 200)
        self.esperar_trabajo()
        e = self.estado()
        self.assertEqual(e["juego"], 'Tormenta de "Acero"')
        self.assertIn("Diseño escrito", e["mensajes"][-1])

    def test_idear_sin_clave(self):
        self.abrir(con_juego=False, claude=ClaudeFalso(aviso="Falta la clave de Claude"))
        codigo, cuerpo, _ = self.pedir("POST", "/api/idear", {"idea": "samuráis"})
        self.assertEqual((codigo, cuerpo["error"]), (400, "Falta la clave de Claude"))
        self.assertFalse((self.carpeta / "juego.toml").exists())


if __name__ == "__main__":
    unittest.main()
