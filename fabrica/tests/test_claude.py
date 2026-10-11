import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fabrica.agentes import Contexto, ErrorAgente, Resultado, Revision, Veredicto
from fabrica.agentes.claude import BETA_RESPALDO, ESQUEMA_VEREDICTO, ClienteClaude, RevisorClaude, tipo_de_imagen
from fabrica.agentes.simulado import AgenteSimulado
from fabrica.diseno import ErrorDiseno
from fabrica.director import Director
from fabrica.plan import Tarea
from fabrica.registro import APROBADO, ESPERANDO, PENDIENTE, SIN_AGENTE

from .util import MINIMO, ConProyecto

PNG = b"\x89PNG\r\n\x1a\n" + b"imagen"
JPG = b"\xff\xd8\xff\xe0" + b"imagen"


class ClaudeFalso:
    """Imita client.beta.messages.stream(...) de la librería anthropic y apunta cada petición."""

    def __init__(self, *respuestas, stop_reason="end_turn", error=None):
        self.respuestas = list(respuestas)
        self.stop_reason = stop_reason
        self.error = error
        self.peticiones: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **peticion):
        self.peticiones.append(peticion)
        if self.error:
            raise self.error
        datos = self.respuestas.pop(0) if self.respuestas else {}
        mensaje = SimpleNamespace(
            stop_reason=self.stop_reason,
            stop_details=SimpleNamespace(explanation="motivo de seguridad") if self.stop_reason == "refusal" else None,
            content=[SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text=json.dumps(datos))],
        )
        flujo = mock.MagicMock()
        flujo.__enter__.return_value.get_final_message.return_value = mensaje
        return flujo


def bien(comentario="Coincide con la descripción."):
    return {"aprobado": True, "comentario": comentario, "problemas": [], "correccion": ""}


def mal(*problemas, correccion="make the hair red"):
    return {"aprobado": False, "comentario": "Hay fallos.", "problemas": list(problemas), "correccion": correccion}


class TestRevisorClaude(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def archivo(self, nombre, datos):
        ruta = self.base / nombre
        ruta.write_bytes(datos)
        return ruta

    def revision(self, archivos, **extra):
        tarea = Tarea(id="ren/concepto", tipo="concepto", titulo="Arte conceptual de Ren", proveedor="meshy",
                      requiere_aprobacion=True)
        return Revision(tarea=tarea, juego="Prueba", estilo="anime", archivos=archivos,
                        ficha={"nombre": "Ren", "descripcion": "Pelo rojo.", "altura": 1.78}, **extra)

    def test_aprueba(self):
        claude = ClaudeFalso(bien())
        veredicto = RevisorClaude(cliente=claude).revisar(self.revision([self.archivo("c.png", PNG)]))
        self.assertEqual(veredicto, Veredicto(aprobado=True, comentario="Coincide con la descripción."))

    def test_rechaza_con_problemas_y_correccion(self):
        claude = ClaudeFalso(mal("Tiene el pelo azul.", "Le faltan los pies."))
        veredicto = RevisorClaude(cliente=claude).revisar(self.revision([self.archivo("c.png", PNG)]))
        self.assertFalse(veredicto.aprobado)
        self.assertEqual(veredicto.problemas, ["Tiene el pelo azul.", "Le faltan los pies."])
        self.assertEqual(veredicto.correccion, "make the hair red")

    def test_rechazo_sin_detalles_lleva_el_comentario(self):
        datos = {"aprobado": False, "comentario": "No se parece.", "problemas": [], "correccion": ""}
        veredicto = RevisorClaude(cliente=ClaudeFalso(datos)).revisar(self.revision([self.archivo("c.png", PNG)]))
        self.assertEqual(veredicto.problemas, ["No se parece."])

    def test_la_peticion(self):
        claude = ClaudeFalso(bien())
        referencia = self.archivo("ref.jpg", JPG)
        revision = self.revision([self.archivo("m.glb", b"glTF"), self.archivo("c.png", PNG), self.archivo("c2.png", PNG)],
                                 referencias=[referencia], nota="Imagen de Meshy.", motivo_rechazo="más musculoso")
        RevisorClaude(cliente=claude, esfuerzo="high").revisar(revision)
        p = claude.peticiones[0]
        self.assertEqual(p["model"], "claude-opus-5-5")
        self.assertEqual(p["betas"], [BETA_RESPALDO])
        self.assertEqual(p["fallbacks"], "default")
        self.assertEqual(p["output_config"]["effort"], "high")
        self.assertEqual(p["output_config"]["format"], {"type": "json_schema", "schema": ESQUEMA_VEREDICTO})
        self.assertNotIn("thinking", p)
        self.assertIn("quality reviewer", p["system"])
        contenido = p["messages"][0]["content"]
        ficha = contenido[0]["text"]
        for texto in ("Character: Ren. Pelo rojo.", "Character height: 1.78 m", "Asset type: concepto",
                      "Generator notes: Imagen de Meshy.", "Change requested for this version: más musculoso"):
            self.assertIn(texto, ficha)
        imagenes = [b for b in contenido if b["type"] == "image"]
        self.assertEqual([i["source"]["media_type"] for i in imagenes], ["image/jpeg", "image/png"])
        self.assertEqual(base64.standard_b64decode(imagenes[1]["source"]["data"]), PNG)
        etiquetas = [b["text"] for b in contenido if b["type"] == "text"][1:]
        self.assertEqual(len(etiquetas), 2)  # solo la primera imagen: es la que sigue adelante
        self.assertTrue(etiquetas[0].startswith("REFERENCE"))
        self.assertTrue(etiquetas[1].startswith("TO REVIEW (c.png)"))

    def test_sin_imagenes_que_mirar(self):
        claude = ClaudeFalso(bien())
        svg = self.archivo("concepto.svg", b"<svg/>")
        self.assertIsNone(RevisorClaude(cliente=claude).revisar(self.revision([svg, self.archivo("m.glb", b"glTF")])))
        self.assertEqual(claude.peticiones, [])

    def test_imagen_demasiado_grande(self):
        grande = self.archivo("c.png", PNG + b"0" * (5 * 1024 * 1024))
        with self.assertRaisesRegex(ErrorAgente, "5 MB"):
            RevisorClaude(cliente=ClaudeFalso(bien())).revisar(self.revision([grande]))

    def test_se_niega(self):
        with self.assertRaisesRegex(ErrorAgente, "no quiso responder.*motivo de seguridad"):
            RevisorClaude(cliente=ClaudeFalso(bien(), stop_reason="refusal")).revisar(self.revision([self.archivo("c.png", PNG)]))

    def test_respuesta_cortada(self):
        with self.assertRaisesRegex(ErrorAgente, "se cortó"):
            RevisorClaude(cliente=ClaudeFalso(bien(), stop_reason="max_tokens")).revisar(self.revision([self.archivo("c.png", PNG)]))

    def test_errores_de_la_api_se_explican(self):
        class ErrorAPI(Exception):
            def __init__(self, codigo, mensaje):
                super().__init__(mensaje)
                self.status_code, self.message = codigo, mensaje

        casos = {401: "ANTHROPIC_API_KEY", 404: "no encuentra el modelo", 429: "pide esperar", 529: "no está disponible",
                 400: "respondió 400: credit balance is too low"}
        for codigo, texto in casos.items():
            claude = ClaudeFalso(error=ErrorAPI(codigo, "credit balance is too low"))
            with self.assertRaisesRegex(ErrorAgente, texto):
                RevisorClaude(cliente=claude).revisar(self.revision([self.archivo("c.png", PNG)]))
        with self.assertRaisesRegex(ErrorAgente, "No se pudo hablar con Claude: Connection error"):
            RevisorClaude(cliente=ClaudeFalso(error=OSError("Connection error"))).revisar(self.revision([self.archivo("c.png", PNG)]))

    def test_ajustes_invalidos(self):
        for ajustes, texto in (({"esfuerzo": "mucho"}, "esfuerzo"), ({"rehacer": 9}, "rehacer"),
                               ({"modelo": "gpt-5"}, "modelo"), ({"limite": 0}, "limite")):
            with self.assertRaisesRegex(ValueError, texto):
                RevisorClaude(**ajustes)

    def test_disponible_sin_libreria_o_sin_clave(self):
        with mock.patch.dict(sys.modules, {"anthropic": None}):
            self.assertIn("pip install anthropic", ClienteClaude().disponible())
        sin_clave = SimpleNamespace(api_key=None, auth_token=None, credentials=None)
        falso = SimpleNamespace(Anthropic=lambda **kw: sin_clave)
        with mock.patch.dict(sys.modules, {"anthropic": falso}):
            self.assertIn("ANTHROPIC_API_KEY", ClienteClaude().disponible())
        con_clave = SimpleNamespace(api_key="sk-ant-secreta", auth_token=None, credentials=None)
        falso = SimpleNamespace(Anthropic=lambda **kw: con_clave)
        with mock.patch.dict(sys.modules, {"anthropic": falso}):
            self.assertIsNone(ClienteClaude().disponible())

    def test_tipo_de_imagen(self):
        self.assertEqual(tipo_de_imagen(self.archivo("a.webp", b"RIFF\0\0\0\0WEBPVP8 ")), "image/webp")
        self.assertEqual(tipo_de_imagen(self.archivo("a.gif", b"GIF89a....")), "image/gif")
        self.assertEqual(tipo_de_imagen(self.archivo("falsa.png", b"no soy png")), None)
        self.assertIsNone(tipo_de_imagen(self.base / "no_existe.png"))


class ConceptoPNG(AgenteSimulado):
    """El simulado, pero con el concepto en PNG (el revisor no mira SVG) y apuntando lo que recibe."""

    def __init__(self):
        self.contextos: list[Contexto] = []

    def generar(self, ctx: Contexto) -> Resultado:
        self.contextos.append(ctx)
        if ctx.tarea.tipo == "concepto":
            ruta = ctx.archivo("concepto.png")
            ruta.write_bytes(PNG + str(ctx.intento).encode())
            return Resultado([ruta], "Concepto de prueba.")
        if ctx.tarea.tipo == "limpieza":
            resultado = super().generar(ctx)
            vista = ctx.archivo("vista.png")
            vista.write_bytes(PNG)
            return Resultado(resultado.archivos + [vista], resultado.nota)
        return super().generar(ctx)

    def de(self, id_):
        return [c for c in self.contextos if c.tarea.id == id_]


class RevisorFalso:
    nombre = "claude"
    tipos = frozenset()
    AJUSTES = ()

    def __init__(self, *veredictos, rehacer=2, aviso=None, error=None):
        self.veredictos = list(veredictos)
        self.rehacer = rehacer
        self.aviso = aviso
        self.error = error
        self.revisiones: list[Revision] = []

    def disponible(self):
        return self.aviso

    def revisar(self, revision):
        self.revisiones.append(revision)
        if self.error:
            raise self.error
        return self.veredictos.pop(0) if self.veredictos else Veredicto(True, "Bien.")


RECHAZO = Veredicto(False, "Fallos.", ["Tiene el pelo azul."], "make the hair red")


class TestRevisionEnElDirector(ConProyecto):
    def con_revision(self, revisar='["concepto"]', extra=""):
        self.escribir(MINIMO.replace("intentos_max = 2", f"intentos_max = 2\nrevisar = {revisar}{extra}"))

    def director(self, revisor, agente=None):
        self.agente = agente or ConceptoPNG()
        return Director(self.carpeta, agentes={"simulado": self.agente, "claude": revisor})

    def test_rechaza_y_se_rehace_con_su_correccion(self):
        self.con_revision()
        revisor = RevisorFalso(RECHAZO, Veredicto(True, "Ahora sí."))
        avisos = []
        d = self.director(revisor)
        d.ejecutar(al_revisar=lambda t, v, vez, maximo: avisos.append((t.id, vez, maximo)))
        intentos = self.agente.de("ren/concepto")
        self.assertEqual([c.motivo_rechazo for c in intentos], ["", "make the hair red"])
        self.assertEqual([c.rechazos for c in intentos], [0, 1])
        self.assertEqual(avisos, [("ren/concepto", 1, 2), ("ren/concepto", 0, 2)])  # rechazo y aprobado
        e = d.entrada("ren/concepto")
        self.assertEqual(e.estado, ESPERANDO)  # Claude no sustituye tu visto bueno
        self.assertIn("Claude: Ahora sí.", e.nota)
        self.assertEqual(revisor.revisiones[1].motivo_rechazo, "make the hair red")
        self.assertEqual(revisor.revisiones[0].ficha["nombre"], "Ren")
        self.assertEqual(len(self.agente.de("ren/voz/grito")), 1)  # lo que no se revisa, como siempre

    def test_si_sigue_mal_te_lo_pasa_a_ti(self):
        self.con_revision()
        revisor = RevisorFalso(RECHAZO, RECHAZO, rehacer=1)
        d = self.director(revisor)
        d.ejecutar()
        self.assertEqual(len(self.agente.de("ren/concepto")), 2)
        e = d.entrada("ren/concepto")
        self.assertEqual(e.estado, ESPERANDO)
        self.assertIn("Claude sigue viendo fallos: Tiene el pelo azul.", e.nota)
        d.aprobar(["ren/concepto"])
        self.assertEqual(d.entrada("ren/concepto").motivo_rechazo, "")

    def test_lo_que_no_necesita_tu_visto_bueno_pero_falla_te_llega(self):
        self.con_revision('["limpieza"]')
        revisor = RevisorFalso(RECHAZO, RECHAZO, rehacer=1)
        d = self.director(revisor)
        d.ejecutar()
        d.aprobar_todo()
        d.ejecutar()
        self.assertEqual(d.entrada("ren/limpieza").estado, ESPERANDO)
        self.assertEqual(d.entrada("ren/rig").estado, PENDIENTE)
        self.assertEqual(revisor.revisiones[0].referencias, [self.carpeta / "recursos/ren/concepto/concepto.png"])

    def test_aprobado_por_claude_sigue_solo_si_no_necesita_tu_visto_bueno(self):
        self.con_revision('["limpieza"]')
        d = self.director(RevisorFalso())
        d.ejecutar()
        d.aprobar_todo()
        d.ejecutar()
        self.assertEqual(d.entrada("ren/limpieza").estado, APROBADO)
        self.assertEqual(d.entrada("ren/rig").estado, APROBADO)

    def test_tu_motivo_no_se_pierde(self):
        self.con_revision()
        d = self.director(RevisorFalso(Veredicto(True, "Bien.")))
        d.ejecutar()
        d.rechazar("ren/concepto", "más musculoso")
        d._agentes["claude"] = RevisorFalso(RECHAZO, Veredicto(True, "Bien."))
        d.ejecutar()
        self.assertEqual([c.motivo_rechazo for c in self.agente.de("ren/concepto")][-2:],
                         ["más musculoso", "más musculoso; make the hair red"])

    def test_si_claude_falla_lo_decides_tu(self):
        self.con_revision('["limpieza"]')
        d = self.director(RevisorFalso(error=ErrorAgente("Claude pide esperar")))
        d.ejecutar()
        d.aprobar_todo()
        d.ejecutar()
        e = d.entrada("ren/limpieza")
        self.assertEqual(e.estado, ESPERANDO)
        self.assertIn("Claude no pudo revisarlo (Claude pide esperar)", e.nota)

    def test_sin_imagen_sigue_como_siempre(self):
        self.con_revision()
        revisor = RevisorFalso()
        revisor.revisar = lambda r: None  # lo que hace el de verdad con el concepto simulado, que es SVG
        d = self.director(revisor)
        d.ejecutar()
        e = d.entrada("ren/concepto")
        self.assertEqual(e.estado, ESPERANDO)
        self.assertIn("Claude no lo revisó", e.nota)

    def test_sin_clave_de_claude_no_se_genera_lo_que_hay_que_revisar(self):
        self.con_revision()
        d = self.director(RevisorFalso(aviso="Falta la clave de Claude"))
        informe = d.ejecutar()
        self.assertEqual(informe.sin_agente, ["ren/concepto"])
        self.assertEqual(d.entrada("ren/concepto").estado, SIN_AGENTE)
        self.assertEqual(d.entrada("ren/voz/grito").estado, APROBADO)

    def test_revisar_solo_imagenes(self):
        self.con_revision('["voz"]')
        with self.assertRaisesRegex(ErrorDiseno, "puede revisar: concepto, modelo3d, limpieza"):
            Director(self.carpeta)

    def test_claude_no_hace_recursos(self):
        self.escribir(MINIMO.replace("intentos_max = 2", 'intentos_max = 2\n\n[fabrica.proveedores]\nconcepto = "claude"'))
        with self.assertRaisesRegex(ErrorDiseno, "claude no hace recursos"):
            Director(self.carpeta)

    def test_ajuste_de_claude_invalido_sale_al_empezar(self):
        self.con_revision(extra='\n\n[fabrica.claude]\nesfuerzo = "mucho"')
        with self.assertRaisesRegex(ErrorDiseno, r"\[fabrica.claude\]: esfuerzo"):
            Director(self.carpeta)

    def test_revisar_no_cambia_la_huella(self):
        antes = {t.id: t.huella for t in Director(self.carpeta).tareas}
        self.con_revision('["concepto", "limpieza"]', extra='\n\n[fabrica.claude]\nrehacer = 1')
        despues = {t.id: t.huella for t in Director(self.carpeta).tareas}
        self.assertEqual(antes, despues)


if __name__ == "__main__":
    unittest.main()


def _eventos(*eventos: dict) -> bytes:
    return b"".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n".encode() for e in eventos)


def respuesta_sse(texto: str, stop_reason: str = "end_turn") -> bytes:
    """Lo que manda la API al pedir stream=True: un mensaje con un bloque de texto."""
    mensaje = {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5", "content": [],
               "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 50, "output_tokens": 1}}
    delta = {"stop_reason": stop_reason, "stop_sequence": None}
    if stop_reason == "refusal":
        delta["stop_details"] = {"type": "refusal", "category": None, "explanation": "motivo de seguridad"}
    return _eventos(
        {"type": "message_start", "message": mensaje},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": texto}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": delta, "usage": {"output_tokens": 30}},
        {"type": "message_stop"},
    )


def _hay_libreria() -> bool:
    import importlib.util

    return importlib.util.find_spec("anthropic") is not None


@unittest.skipUnless(_hay_libreria(), "sin la librería anthropic (pip install anthropic)")
class TestConLaLibreriaDeVerdad(unittest.TestCase):
    """La librería oficial contra un servidor local que responde como la API: sin clave real ni gasto."""

    def setUp(self):
        import http.server
        import threading

        self.peticiones: list[tuple[str, dict, dict]] = []
        self.respuestas: list[tuple[int, bytes]] = []
        prueba = self

        class Manejador(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                cuerpo = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                prueba.peticiones.append((self.path, {k.lower(): v for k, v in self.headers.items()}, json.loads(cuerpo)))
                codigo, datos = prueba.respuestas.pop(0)
                self.send_response(codigo)
                tipo = "text/event-stream" if codigo == 200 else "application/json"
                self.send_header("Content-Type", tipo)
                self.send_header("Content-Length", str(len(datos)))
                self.end_headers()
                self.wfile.write(datos)

            def log_message(self, *args):
                pass

        self.servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        self.addCleanup(self.servidor.server_close)
        self.addCleanup(self.servidor.shutdown)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.imagen = Path(self._tmp.name) / "concepto.png"
        self.imagen.write_bytes(PNG)

    def revisor(self) -> RevisorClaude:
        import anthropic

        cliente = anthropic.Anthropic(
            api_key="sk-ant-prueba", base_url=f"http://127.0.0.1:{self.servidor.server_address[1]}", max_retries=0
        )
        return RevisorClaude(cliente=cliente)

    def revision(self) -> Revision:
        tarea = Tarea(id="ren/concepto", tipo="concepto", titulo="", proveedor="meshy", requiere_aprobacion=True)
        return Revision(tarea=tarea, juego="Prueba", estilo="anime", archivos=[self.imagen], ficha={"nombre": "Ren"})

    def test_peticion_real_y_veredicto(self):
        self.respuestas.append((200, respuesta_sse(json.dumps(mal("Le faltan los pies.")))))
        veredicto = self.revisor().revisar(self.revision())
        self.assertEqual(veredicto.problemas, ["Le faltan los pies."])
        ruta, cabeceras, cuerpo = self.peticiones[0]
        self.assertTrue(ruta.startswith("/v1/messages"))
        self.assertIn(BETA_RESPALDO, cabeceras["anthropic-beta"])
        self.assertEqual(cabeceras["x-api-key"], "sk-ant-prueba")
        self.assertEqual(cuerpo["fallbacks"], "default")
        self.assertIs(cuerpo["stream"], True)
        self.assertEqual(cuerpo["model"], "claude-opus-5-5")
        self.assertEqual(cuerpo["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(cuerpo["output_config"]["effort"], "medium")
        imagen = next(b for b in cuerpo["messages"][0]["content"] if b["type"] == "image")
        self.assertEqual(imagen["source"]["media_type"], "image/png")

    def test_negativa(self):
        self.respuestas.append((200, respuesta_sse("", stop_reason="refusal")))
        with self.assertRaisesRegex(ErrorAgente, "no quiso responder a esta petición: motivo de seguridad"):
            self.revisor().revisar(self.revision())

    def test_error_de_la_api_sin_mostrar_la_clave(self):
        cuerpo = {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}}
        self.respuestas.append((401, json.dumps(cuerpo).encode()))
        with self.assertRaises(ErrorAgente) as error:
            self.revisor().revisar(self.revision())
        self.assertIn("ANTHROPIC_API_KEY", str(error.exception))
        self.assertNotIn("sk-ant-prueba", str(error.exception))
