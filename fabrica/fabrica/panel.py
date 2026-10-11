"""Panel visual: la fábrica en el navegador, sin escribir órdenes.

    python -m fabrica panel -p mi_juego        (se abre http://127.0.0.1:8765)

Muestra cada tarea con su imagen, su audio o su modelo 3D, y deja ejecutar, parar, aprobar,
rechazar, editar el diseño, crear el proyecto (con Claude o con el ejemplo) y llevarlo a Godot.
Solo escucha en tu PC (127.0.0.1) y solo sirve archivos de la carpeta recursos/ del proyecto.
"""

from __future__ import annotations

import json
import mimetypes
import os
import shutil
import tempfile
import threading
import time
from collections import Counter, deque
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from .agentes import ErrorAgente, Veredicto
from .agentes.claude import ClienteClaude
from .director import Director, ErrorOrden
from .diseno import ErrorDiseno
from .idear import idear
from .plan import Tarea
from .registro import ERROR, PENDIENTE, Entrada, ErrorRegistro

PUERTO = 8765
MAX_CUERPO = 2 * 1024 * 1024
CLASES = {
    ".png": "imagen", ".jpg": "imagen", ".jpeg": "imagen", ".webp": "imagen", ".gif": "imagen", ".svg": "imagen",
    ".wav": "audio", ".mp3": "audio", ".ogg": "audio", ".flac": "audio",
    ".glb": "modelo", ".gltf": "modelo",
}
TIPOS = {
    ".glb": "model/gltf-binary", ".gltf": "model/gltf+json", ".bin": "application/octet-stream",
    ".svg": "image/svg+xml", ".webp": "image/webp", ".wav": "audio/wav", ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg", ".flac": "audio/flac", ".json": "application/json", ".png": "image/png",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
}
# La página solo carga código propio y el visor 3D (model-viewer); nada de lo generado se ejecuta.
CSP_PAGINA = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval' https://cdn.jsdelivr.net https://www.gstatic.com;"
    " style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:;"
    " connect-src 'self' data: blob: https://www.gstatic.com; worker-src 'self' blob:; frame-ancestors 'none'"
)
CSP_ARCHIVO = "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; sandbox"


class Ocupado(Exception):
    """La fábrica está trabajando: hay que esperar a que termine (o pararla)."""


class Panel:
    """El proyecto que se ve en el panel y el trabajo que corre en segundo plano."""

    def __init__(self, carpeta: Path, agentes: dict | None = None, claude: Callable[[], ClienteClaude] | None = None):
        self.carpeta = Path(carpeta).resolve()
        self._agentes = agentes  # las pruebas pasan agentes falsos
        self._crear_claude = claude or (lambda: ClienteClaude(esfuerzo="high"))
        self._cerrojo = threading.RLock()
        self._director: Director | None = None
        self._firma: tuple | None = None
        self._error: str | None = None
        self.trabajo = ""  # "ejecutar", "idear" o "" si está libre
        self._parar = threading.Event()
        self.hilo: threading.Thread | None = None
        self.mensajes: deque[str] = deque(maxlen=400)

    @property
    def toml(self) -> Path:
        return self.carpeta / "juego.toml"

    # --- lectura -------------------------------------------------------------------------

    def director(self) -> Director | None:
        """El director del proyecto. Se recarga si juego.toml o el registro cambiaron por fuera."""
        with self._cerrojo:
            if self.trabajo:
                return self._director
            firma = (_firma(self.toml), _firma(self.carpeta / "registro.json"))
            if firma != self._firma:
                self._firma = firma
                self._director, self._error = None, None
                if firma[0] is not None:
                    try:
                        self._director = Director(self.carpeta, agentes=self._agentes)
                    except (ErrorDiseno, ErrorRegistro) as e:
                        self._error = str(e)
            return self._director

    def estado(self) -> dict:
        d = self.director()
        with self._cerrojo:
            base = {"carpeta": str(self.carpeta), "trabajo": self.trabajo, "mensajes": list(self.mensajes)}
            if d is None:
                return {**base, "existe": self.toml.exists(), "error": self._error}
        tareas = [self._tarea(d, t) for t in d.tareas]
        titulos = {p.id: p.nombre for p in d.diseno.personajes}
        titulos.update({"sonido": "Efectos de sonido", "musica": "Música"})
        grupos: dict[str, list[dict]] = {}
        for t in tareas:
            grupos.setdefault(t["id"].split("/", 1)[0], []).append(t)
        return {
            **base,
            "existe": True,
            "error": None,
            "juego": d.diseno.nombre,
            "resumen": dict(Counter(t["estado"] for t in tareas)),
            "revisa_claude": sorted(d.diseno.revisar),
            "grupos": [{"id": clave, "titulo": titulos.get(clave, clave), "tareas": lista} for clave, lista in grupos.items()],
        }

    def _tarea(self, d: Director, t: Tarea) -> dict:
        e = d.entrada(t.id)
        archivos = []
        for relativa in list(e.archivos):
            extension = Path(relativa).suffix.lower()
            archivos.append({
                "nombre": Path(relativa).name,
                "url": "/archivo/" + quote(relativa) + "?v=" + quote(e.actualizado),
                "clase": CLASES.get(extension, "otro"),
            })
        return {
            "id": t.id,
            "titulo": t.titulo,
            "tipo": t.tipo,
            "proveedor": t.proveedor,
            "estado": e.estado,
            "nota": e.nota,
            "motivo": e.motivo_rechazo,
            "espera_a": d.deps_sin_aprobar(t) if e.estado == PENDIENTE else [],
            "pide_visto_bueno": t.requiere_aprobacion,
            "revisa_claude": t.tipo in d.diseno.revisar,
            "archivos": archivos,
        }

    def texto_diseno(self) -> str:
        try:
            return self.toml.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise ErrorOrden("Aún no hay juego.toml en este proyecto.") from None

    # --- trabajo en segundo plano ------------------------------------------------------------

    def ejecutar(self) -> None:
        with self._cerrojo:
            d = self._para_cambiar()
            self._empezar("ejecutar", self._ejecutar, d)

    def parar(self) -> None:
        with self._cerrojo:
            if self.trabajo == "ejecutar" and not self._parar.is_set():
                self._parar.set()
                self._decir("Parando: termina la tarea en curso y se detiene.")

    def idear(self, idea: str) -> None:
        idea = idea.strip()
        if not idea:
            raise ErrorOrden("Cuenta tu idea: de qué va el juego, cuántos personajes, cómo son...")
        with self._cerrojo:
            self._libre()
            if self.toml.exists():
                raise ErrorOrden("Este proyecto ya tiene juego.toml.")
            claude = self._crear_claude()
            aviso = claude.disponible()
            if aviso:
                raise ErrorOrden(aviso)
            self._empezar("idear", self._idear, idea, claude)

    def _empezar(self, trabajo: str, funcion: Callable, *args) -> None:
        self.trabajo = trabajo
        self._parar.clear()
        self.hilo = threading.Thread(target=self._trabajar, args=(funcion, *args), daemon=True, name=f"fabrica-{trabajo}")
        self.hilo.start()

    def _trabajar(self, funcion: Callable, *args) -> None:
        try:
            funcion(*args)
        except Exception as e:  # el panel sigue vivo pase lo que pase
            self._decir(f"Error: {e}")
        finally:
            with self._cerrojo:
                self.trabajo = ""
                self._firma = None  # vuelve a leer el proyecto tal como quedó

    def _ejecutar(self, d: Director) -> None:
        self._decir(f"Ejecutando «{d.diseno.nombre}»")
        informe = d.ejecutar(None, self._al_terminar, self._al_revisar, seguir=lambda: not self._parar.is_set())
        if not (informe.hechas or informe.errores or informe.sin_agente):
            self._decir("No hay nada que se pueda hacer ahora mismo.")
        for motivo, n in Counter(d.entrada(i).nota for i in informe.sin_agente).items():
            self._decir(f"{n} tarea(s) sin agente: {motivo}")
        self._decir("Parado." if informe.detenido else "Terminado.")

    def _al_terminar(self, t: Tarea, e: Entrada) -> None:
        if e.estado == ERROR:
            self._decir(f"error   {t.id}: {e.nota}")
        else:
            self._decir(f"hecho   {t.id} ({e.agente})" + (" -> espera tu visto bueno" if e.estado == "esperando_aprobacion" else ""))

    def _al_revisar(self, t: Tarea, veredicto: Veredicto, vez: int, maximo: int) -> None:
        if veredicto.aprobado:
            self._decir(f"Claude  {t.id}: {veredicto.comentario or 'bien'}")
        elif vez:
            self._decir(f"Claude  {t.id}: {'; '.join(veredicto.problemas)} -> se rehace ({vez}/{maximo})")
        else:
            self._decir(f"Claude  {t.id}: {'; '.join(veredicto.problemas)} -> te lo paso a ti")

    def _idear(self, idea: str, claude: ClienteClaude) -> None:
        self._decir("Claude está escribiendo el diseño. Puede tardar unos minutos...")
        texto = idear(idea, claude)
        self.carpeta.mkdir(parents=True, exist_ok=True)
        _escribir(self.toml, texto)
        self._decir("Diseño escrito. Revísalo en «Diseño» y pulsa Ejecutar cuando quieras.")

    # --- cambios (solo con la fábrica parada) ------------------------------------------------

    def nuevo(self) -> None:
        with self._cerrojo:
            self._libre()
            if self.toml.exists():
                raise ErrorOrden("Este proyecto ya tiene juego.toml.")
            self.carpeta.mkdir(parents=True, exist_ok=True)
            plantilla = resources.files("fabrica").joinpath("plantilla/juego.toml").read_text(encoding="utf-8")
            _escribir(self.toml, plantilla)
            self._decir("Proyecto creado con el ejemplo: dos luchadores, sus sonidos y su música.")

    def aprobar(self, ids: list[str] | None) -> list[str]:
        with self._cerrojo:
            d = self._para_cambiar()
            hechas = d.aprobar_todo() if ids is None else d.aprobar(ids)
            if hechas:
                self._decir(f"Aprobado: {', '.join(hechas)}")
            return hechas

    def rechazar(self, id_: str, motivo: str) -> list[str]:
        with self._cerrojo:
            afectadas = self._para_cambiar().rechazar(id_, motivo)
            self._decir(f"Rechazado {id_}: se rehará con tu motivo.")
            return afectadas

    def guardar_diseno(self, texto: str) -> None:
        """Comprueba el diseño entero (también proveedores y ajustes) antes de guardarlo."""
        with self._cerrojo:
            self._libre()
            with tempfile.TemporaryDirectory() as tmp:
                (Path(tmp) / "juego.toml").write_text(texto, encoding="utf-8")
                try:
                    Director(Path(tmp), agentes=self._agentes)
                except (ErrorDiseno, ErrorRegistro) as e:
                    raise ErrorOrden(str(e)) from None
            self.carpeta.mkdir(parents=True, exist_ok=True)
            _escribir(self.toml, texto)
            self._decir("Diseño guardado: en la próxima ejecución se rehace solo lo que cambió.")

    def exportar(self) -> str:
        with self._cerrojo:
            ruta = self._para_cambiar().exportar()
            self._decir(f"Índice escrito en {ruta}")
            return str(ruta)

    def montar(self, juego: str, incluir_simulados: bool) -> dict:
        if not juego.strip():
            raise ErrorOrden("Escribe la carpeta del proyecto de Godot (la que tiene project.godot).")
        with self._cerrojo:
            montaje = self._para_cambiar().montar(Path(juego.strip()).expanduser(), incluir_simulados)
            self._decir(f"Copiados {len(montaje.copiados)} recursos a {montaje.destino}")
            return {"destino": str(montaje.destino), "copiados": len(montaje.copiados), "omitidos": len(montaje.omitidos)}

    def _libre(self) -> None:
        if self.trabajo:
            raise Ocupado("La fábrica está trabajando: espera a que termine o pulsa Parar.")

    def _para_cambiar(self) -> Director:
        self._libre()
        d = self.director()
        if d is None:
            raise ErrorOrden(self._error or "Aún no hay juego.toml en este proyecto.")
        return d

    def _decir(self, texto: str) -> None:
        with self._cerrojo:
            self.mensajes.append(f"{time.strftime('%H:%M:%S')}  {texto}")

    # --- archivos ----------------------------------------------------------------------------

    def ruta_archivo(self, relativa: str) -> Path | None:
        """Un archivo de recursos/ del proyecto, o None si la ruta se sale de ahí o no existe."""
        base = (self.carpeta / "recursos").resolve()
        try:
            ruta = (self.carpeta / relativa).resolve()
        except (OSError, ValueError):
            return None
        if not ruta.is_relative_to(base) or not ruta.is_file():
            return None
        return ruta


def _firma(ruta: Path) -> tuple | None:
    try:
        info = ruta.stat()
    except FileNotFoundError:
        return None
    return info.st_mtime_ns, info.st_size


def _escribir(ruta: Path, texto: str) -> None:
    """Escribe de golpe (archivo aparte y reemplazo) para no dejarlo nunca a medias."""
    fd, temporal = tempfile.mkstemp(dir=ruta.parent, prefix=".juego-", suffix=".toml")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(texto)
        os.replace(temporal, ruta)
    except BaseException:
        Path(temporal).unlink(missing_ok=True)
        raise


# --- servidor HTTP --------------------------------------------------------------------------

class Manejador(BaseHTTPRequestHandler):
    server_version = "Fabrica"
    server: "ServidorPanel"

    def log_message(self, formato, *args):  # sin ruido en la terminal
        pass

    def do_GET(self):
        if not self._host_valido():
            return
        ruta = urlparse(self.path).path
        if ruta in ("/", "/index.html"):
            html = resources.files("fabrica").joinpath("plantilla/panel.html").read_bytes()
            self._enviar(200, html, "text/html; charset=utf-8", {"Content-Security-Policy": CSP_PAGINA})
        elif ruta == "/api/estado":
            self._accion(lambda datos: self.server.panel.estado(), {})
        elif ruta == "/api/diseno":
            self._accion(lambda datos: {"texto": self.server.panel.texto_diseno()}, {})
        elif ruta.startswith("/archivo/"):
            self._archivo(unquote(ruta[len("/archivo/"):]))
        else:
            self._json(404, {"error": "No existe."})

    def do_POST(self):
        if not self._host_valido():
            return
        # Cabecera propia y JSON: una web ajena no puede mandarlas sin permiso del panel (CORS).
        if self.headers.get("X-Fabrica") != "1" or not (self.headers.get("Content-Type") or "").startswith("application/json"):
            self._json(403, {"error": "Petición no permitida."})
            return
        largo = int(self.headers.get("Content-Length") or 0)
        if largo > MAX_CUERPO:
            self._json(413, {"error": "Demasiado grande."})
            return
        try:
            datos = json.loads(self.rfile.read(largo) or b"{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "Petición mal formada."})
            return
        if not isinstance(datos, dict):
            self._json(400, {"error": "Petición mal formada."})
            return
        panel = self.server.panel
        acciones = {
            "/api/ejecutar": lambda d: panel.ejecutar(),
            "/api/parar": lambda d: panel.parar(),
            "/api/aprobar": lambda d: {"aprobadas": panel.aprobar(None if d.get("todo") else _lista(d.get("ids")))},
            "/api/rechazar": lambda d: {"afectadas": panel.rechazar(_texto(d.get("id")), _texto(d.get("motivo")))},
            "/api/diseno": lambda d: panel.guardar_diseno(_texto(d.get("texto"))),
            "/api/nuevo": lambda d: panel.nuevo(),
            "/api/idear": lambda d: panel.idear(_texto(d.get("idea"))),
            "/api/exportar": lambda d: {"ruta": panel.exportar()},
            "/api/montar": lambda d: panel.montar(_texto(d.get("juego")), d.get("incluir_simulados") is True),
        }
        accion = acciones.get(urlparse(self.path).path)
        if accion is None:
            self._json(404, {"error": "No existe."})
            return
        self._accion(accion, datos)

    def _accion(self, accion: Callable[[dict], object], datos: dict) -> None:
        try:
            resultado = accion(datos)
        except Ocupado as e:
            self._json(409, {"error": str(e)})
        except (ErrorOrden, ErrorDiseno, ErrorRegistro, ErrorAgente) as e:
            self._json(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001 - el panel tiene que contestar siempre
            self._json(500, {"error": f"Algo falló en el panel: {e}"})
        else:
            self._json(200, resultado if isinstance(resultado, dict) else {"ok": True})

    def _archivo(self, relativa: str) -> None:
        ruta = self.server.panel.ruta_archivo(relativa)
        if ruta is None:
            self._json(404, {"error": "No existe."})
            return
        tipo = TIPOS.get(ruta.suffix.lower()) or mimetypes.guess_type(ruta.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(ruta.stat().st_size))
        self._cabeceras_comunes({"Content-Security-Policy": CSP_ARCHIVO})
        self.end_headers()
        with open(ruta, "rb") as f:
            shutil.copyfileobj(f, self.wfile)

    def _host_valido(self) -> bool:
        # Evita que otra web use el panel engañando al navegador con su nombre (DNS rebinding).
        puerto = self.server.server_address[1]
        if self.headers.get("Host") not in (f"127.0.0.1:{puerto}", f"localhost:{puerto}"):
            self._json(403, {"error": "Abre el panel en http://127.0.0.1:%d" % puerto})
            return False
        return True

    def _json(self, codigo: int, datos: dict) -> None:
        self._enviar(codigo, json.dumps(datos, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _enviar(self, codigo: int, cuerpo: bytes, tipo: str, extra: dict | None = None) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self._cabeceras_comunes(extra or {})
        self.end_headers()
        self.wfile.write(cuerpo)

    def _cabeceras_comunes(self, extra: dict) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for clave, valor in extra.items():
            self.send_header(clave, valor)


class ServidorPanel(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, direccion, panel: Panel):
        super().__init__(direccion, Manejador)
        self.panel = panel


def _lista(valor: object) -> list[str]:
    if not isinstance(valor, list) or not all(isinstance(x, str) for x in valor):
        raise ErrorOrden("Indica qué aprobar.")
    return valor


def _texto(valor: object) -> str:
    return valor if isinstance(valor, str) else ""


def servidor(panel: Panel, puerto: int = PUERTO, intentos: int = 20) -> ServidorPanel:
    """Abre el servidor en 127.0.0.1; si el puerto está ocupado, prueba los siguientes."""
    ultimo: OSError | None = None
    for p in ([0] if puerto == 0 else range(puerto, puerto + intentos)):
        try:
            return ServidorPanel(("127.0.0.1", p), panel)
        except OSError as e:
            ultimo = e
    raise ErrorOrden(f"No hay ningún puerto libre a partir del {puerto}: {ultimo}")
