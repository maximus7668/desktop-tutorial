"""Arte conceptual con ComfyUI en tu PC: tu modelo, tus LoRA y tu flujo de trabajo, gratis.

API de ComfyUI (comprobada en su server.py):
  POST /prompt                     {"prompt": <flujo en formato API>, "client_id": ...} -> {"prompt_id": ...}
  GET  /history/<prompt_id>        {} mientras trabaja; luego {id: {"outputs": ..., "status": ...}}
  GET  /view?filename=&subfolder=&type=   la imagen
El flujo lleva marcas que la fábrica rellena: {{PROMPT}}, {{NEGATIVO}}, {{SEMILLA}}, {{MODELO}},
{{ANCHO}} y {{ALTO}}.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.parse
from pathlib import Path

from . import Contexto, ErrorAgente, Resultado
from .remoto import Cliente, Transporte, clave_intento, esperar, extension_de_imagen

FLUJO_POR_DEFECTO = Path(__file__).resolve().parent.parent / "plantilla" / "flujos" / "concepto_sdxl.json"
NEGATIVO = (
    "lowres, bad anatomy, bad hands, extra fingers, missing fingers, extra limbs, cropped, worst quality,"
    " low quality, jpeg artifacts, blurry, watermark, text, signature, multiple views, busy background"
)
_MARCA = re.compile(r"\{\{(\w+)\}\}")


class AgenteComfyUI:
    nombre = "comfyui"
    tipos = frozenset({"concepto"})
    AJUSTES: tuple[str, ...] = ("servidor", "flujo", "modelo", "negativo", "ancho", "alto", "limite")

    def __init__(
        self,
        servidor: str = "http://127.0.0.1:8188",
        flujo: str = "",
        modelo: str = "",
        negativo: str = NEGATIVO,
        ancho: int = 832,
        alto: int = 1216,
        limite: float = 600.0,
        transporte: Transporte | None = None,
        dormir=time.sleep,
        reloj=time.monotonic,
    ):
        if not isinstance(servidor, str) or not servidor.startswith(("http://", "https://")):
            raise ValueError("servidor tiene que ser una dirección como http://127.0.0.1:8188")
        for nombre, valor in (("ancho", ancho), ("alto", alto)):
            if isinstance(valor, bool) or not isinstance(valor, int) or not 256 <= valor <= 4096 or valor % 8:
                raise ValueError(f"{nombre} tiene que ser un número de píxeles entre 256 y 4096, múltiplo de 8")
        self.servidor = servidor.rstrip("/")
        self.flujo = flujo
        self.modelo = modelo
        self.negativo = negativo
        self.ancho = ancho
        self.alto = alto
        self.limite = float(limite)
        self._api = Cliente("ComfyUI", self.servidor, {}, transporte)
        self._dormir = dormir
        self._reloj = reloj
        self._aviso: str | None = None
        self._comprobado = False

    def disponible(self) -> str | None:
        if not self.flujo and not self.modelo:
            return (
                "Falta el modelo de ComfyUI: pon en juego.toml [fabrica.comfyui] modelo = \"<archivo .safetensors"
                " de tu carpeta ComfyUI/models/checkpoints>\", o tu propio flujo con flujo = \"...\"."
            )
        if not self._comprobado:
            self._comprobado = True
            try:
                self._api.json("GET", "/system_stats", espera=5.0)
            except ErrorAgente:
                self._aviso = f"ComfyUI no responde en {self.servidor}: ábrelo antes de ejecutar la fábrica."
        return self._aviso

    def generar(self, ctx: Contexto) -> Resultado:
        ruta = self._ruta_flujo(ctx)
        try:
            flujo = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise ErrorAgente(f"No puedo leer el flujo de ComfyUI {ruta}: {e}") from None
        if not isinstance(flujo, dict) or "nodes" in flujo:
            raise ErrorAgente(
                f"{ruta.name} no está en formato API. En ComfyUI: menú Flujo de trabajo → Exportar (API)."
            )
        d = ctx.tarea.datos
        prompt = (
            f"{d['estilo']} {d['descripcion']} Full body character design of {d['personaje']},"
            " front view, standing in A-pose, plain white background"
        )
        if ctx.motivo_rechazo:
            prompt += f", {ctx.motivo_rechazo}"
        semilla = int(hashlib.sha256(f"{ctx.tarea.huella}|{ctx.intento}|{ctx.motivo_rechazo}".encode()).hexdigest()[:8], 16)
        valores = {
            "PROMPT": prompt, "NEGATIVO": self.negativo, "SEMILLA": semilla,
            "MODELO": self.modelo, "ANCHO": self.ancho, "ALTO": self.alto,
        }
        flujo = rellenar(flujo, valores)

        clave = clave_intento(ctx)
        memoria = ctx.memoria
        if memoria.get("tarea") and memoria.get("clave") == clave:
            id_tarea = memoria["tarea"]
        else:
            respuesta = self._api.json("POST", "/prompt", {"prompt": flujo, "client_id": "fabrica"})
            id_tarea = respuesta.get("prompt_id")
            if not id_tarea:
                raise ErrorAgente("ComfyUI no devolvió el id del trabajo.")
            memoria.update({"tarea": id_tarea, "clave": clave})
            ctx.guardar()

        historia = esperar(
            lambda: self._api.json("GET", f"/history/{id_tarea}"),
            lambda h: _situacion(h, id_tarea), "ComfyUI", 2.0, self.limite, self._dormir, self._reloj,
        )
        entrada = historia[id_tarea]
        if _situacion(historia, id_tarea) == "fallo":
            memoria.pop("tarea", None)
            raise ErrorAgente(f"ComfyUI falló: {_mensaje_error(entrada)}")
        imagenes = [
            imagen
            for salida in (entrada.get("outputs") or {}).values()
            for imagen in (salida.get("images") or [])
            if imagen.get("type", "output") == "output"
        ]
        if not imagenes:
            raise ErrorAgente("ComfyUI terminó sin guardar ninguna imagen: el flujo necesita un nodo Save Image.")
        archivos = []
        for n, imagen in enumerate(imagenes[:4]):
            consulta = urllib.parse.urlencode({
                "filename": imagen["filename"], "subfolder": imagen.get("subfolder", ""), "type": imagen.get("type", "output"),
            })
            datos = self._api.bajar(f"{self.servidor}/view?{consulta}")
            nombre = ("concepto" if n == 0 else f"concepto_{n + 1}") + extension_de_imagen(datos)
            ruta_imagen = ctx.archivo(nombre)
            ruta_imagen.write_bytes(datos)
            archivos.append(ruta_imagen)
        origen = self.modelo or ruta.name
        return Resultado(archivos, f"ComfyUI ({origen}), semilla {semilla}.")

    def _ruta_flujo(self, ctx: Contexto) -> Path:
        if not self.flujo:
            return FLUJO_POR_DEFECTO
        ruta = Path(self.flujo)
        if not ruta.is_absolute() and ctx.proyecto is not None:
            ruta = ctx.proyecto / ruta
        return ruta


def rellenar(valor, valores: dict):
    """Sustituye las marcas {{NOMBRE}}. Una marca sola conserva el tipo (la semilla queda número)."""
    if isinstance(valor, dict):
        return {k: rellenar(v, valores) for k, v in valor.items()}
    if isinstance(valor, list):
        return [rellenar(v, valores) for v in valor]
    if isinstance(valor, str):
        sola = _MARCA.fullmatch(valor)
        if sola and sola.group(1) in valores:
            return valores[sola.group(1)]
        return _MARCA.sub(lambda m: str(valores[m.group(1)]) if m.group(1) in valores else m.group(0), valor)
    return valor


def _situacion(historia: dict, id_tarea: str) -> str:
    entrada = historia.get(id_tarea)
    if not entrada:
        return "sigue"
    estado = entrada.get("status") or {}
    if estado.get("status_str") == "error":
        return "fallo"
    if estado.get("completed") or entrada.get("outputs"):
        return "ok"
    return "sigue"


def _mensaje_error(entrada: dict) -> str:
    for mensaje in (entrada.get("status") or {}).get("messages") or []:
        if isinstance(mensaje, list) and len(mensaje) == 2 and mensaje[0] == "execution_error":
            datos = mensaje[1] or {}
            return f"{datos.get('node_type', 'nodo')}: {datos.get('exception_message', 'error sin detalle')}".strip()
    return "error sin detalle"
