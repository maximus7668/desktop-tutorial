"""Piezas comunes para agentes que hablan con APIs remotas que trabajan en segundo plano."""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from . import Contexto, ErrorAgente

# (método, url, cuerpo en bytes o None, cabeceras, segundos de espera) -> (código HTTP, bytes)
Transporte = Callable[[str, str, bytes | None, dict, float], tuple[int, bytes]]


def transporte_urllib(metodo: str, url: str, cuerpo: bytes | None, cabeceras: dict, espera: float) -> tuple[int, bytes]:
    peticion = urllib.request.Request(url, data=cuerpo, headers=cabeceras, method=metodo)
    try:
        with urllib.request.urlopen(peticion, timeout=espera) as respuesta:
            return respuesta.status, respuesta.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class Cliente:
    """Cliente JSON mínimo. Los errores se explican sin mostrar nunca la clave."""

    def __init__(self, nombre: str, base: str, cabeceras: dict, transporte: Transporte | None = None):
        self.nombre = nombre
        self.base = base.rstrip("/")
        self.cabeceras = cabeceras
        self._transporte = transporte or transporte_urllib

    def json(self, metodo: str, ruta: str, cuerpo: dict | None = None, espera: float = 60.0) -> dict:
        datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
        cabeceras = {**self.cabeceras, "Accept": "application/json"}
        if datos is not None:
            cabeceras["Content-Type"] = "application/json"
        codigo, respuesta = self._llamar(metodo, self.base + ruta, datos, cabeceras, espera)
        if codigo >= 400:
            raise ErrorAgente(f"{self.nombre} respondió {codigo}: {_resumen(respuesta)}")
        try:
            return json.loads(respuesta.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ErrorAgente(f"{self.nombre} devolvió algo que no es JSON: {_resumen(respuesta)}") from None

    def bajar(self, url: str, espera: float = 300.0) -> bytes:
        """Descarga un archivo de resultado (URLs firmadas: no llevan la clave)."""
        codigo, respuesta = self._llamar("GET", url, None, {}, espera)
        if codigo >= 400:
            raise ErrorAgente(f"No se pudo descargar el resultado de {self.nombre} ({codigo}).")
        if not respuesta:
            raise ErrorAgente(f"{self.nombre} entregó un archivo vacío.")
        return respuesta

    def _llamar(self, metodo: str, url: str, datos: bytes | None, cabeceras: dict, espera: float) -> tuple[int, bytes]:
        try:
            return self._transporte(metodo, url, datos, cabeceras, espera)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ErrorAgente(f"No se pudo hablar con {self.nombre}: {getattr(e, 'reason', e)}") from None


def _resumen(respuesta: bytes) -> str:
    texto = respuesta.decode("utf-8", "replace").strip()
    try:
        datos = json.loads(texto)
        if isinstance(datos, dict):
            texto = str(datos.get("message") or datos.get("detail") or datos.get("error") or texto)
    except json.JSONDecodeError:
        pass
    return texto[:300] or "(sin detalle)"


def clave_intento(ctx: Contexto) -> str:
    """Cambia si cambia lo que se pide (diseño o motivo del rechazo): entonces hay que pedir de nuevo."""
    return hashlib.sha256(f"{ctx.tarea.huella}|{ctx.motivo_rechazo}".encode("utf-8")).hexdigest()[:16]


def esperar(
    consultar: Callable[[], dict],
    estado: Callable[[dict], str],
    nombre: str,
    intervalo: float,
    limite: float,
    dormir: Callable[[float], None] = time.sleep,
    reloj: Callable[[], float] = time.monotonic,
) -> dict:
    """Consulta hasta que la tarea remota termina. estado() devuelve "ok", "fallo" o "sigue"."""
    inicio = reloj()
    while True:
        datos = consultar()
        situacion = estado(datos)
        if situacion in ("ok", "fallo"):
            return datos
        if reloj() - inicio >= limite:
            raise ErrorAgente(
                f"{nombre} sigue trabajando después de {int(limite)} s. La tarea queda apuntada:"
                " vuelve a ejecutar más tarde y se recogerá sin pagarla otra vez."
            )
        dormir(intervalo)


def uri_de_datos(ruta: Path, maximo_mb: float) -> str:
    """Archivo local como data URI (las APIs lo aceptan en lugar de una URL pública)."""
    tamano = ruta.stat().st_size
    if tamano > maximo_mb * 1024 * 1024:
        raise ErrorAgente(f"{ruta.name} ocupa {tamano / 1048576:.1f} MB; el límite es {maximo_mb:g} MB.")
    tipo = mimetypes.guess_type(ruta.name)[0] or "application/octet-stream"
    if ruta.suffix.lower() == ".glb":
        tipo = "model/gltf-binary"
    return f"data:{tipo};base64,{base64.b64encode(ruta.read_bytes()).decode('ascii')}"


def extension_de_imagen(datos: bytes) -> str:
    if datos.startswith(b"\x89PNG"):
        return ".png"
    if datos.startswith(b"\xff\xd8"):
        return ".jpg"
    if datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
        return ".webp"
    return ".png"


def primer_archivo(ctx: Contexto, extensiones: tuple[str, ...]) -> Path | None:
    for archivos in ctx.entradas.values():
        for archivo in archivos:
            if archivo.suffix.lower() in extensiones:
                return archivo
    return None
