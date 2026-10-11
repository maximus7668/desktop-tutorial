"""Meshy: arte conceptual, modelo 3D, esqueleto y animaciones con una sola clave.

Rutas según la documentación oficial (docs.meshy.ai), base https://api.meshy.ai:
  concepto   POST /openapi/v1/text-to-image   -> image_urls
  modelo3d   POST /openapi/v1/image-to-3d     -> model_urls.glb
  rig        POST /openapi/v1/rigging         -> result.rigged_character_glb_url
  animacion  POST /openapi/v1/animations      -> result.animation_glb_url
Todas responden {"result": "<id>"} y se consultan con GET <ruta>/<id> hasta status SUCCEEDED.
Cada tarea gasta créditos de tu cuenta de Meshy.
"""

from __future__ import annotations

import os
import time

from . import Contexto, ErrorAgente, Resultado
from .remoto import Cliente, Transporte, clave_intento, esperar, extension_de_imagen, primer_archivo, uri_de_datos

API = "https://api.meshy.ai"
VARIABLE_CLAVE = "MESHY_API_KEY"
BIBLIOTECA = "docs.meshy.ai/en/api/animation-library"

# Acción de la biblioteca de Meshy que se usa por defecto para cada animación del diseño.
ACCIONES = {
    "idle": 0,
    "guardia": 89,
    "volar": 89,
    "correr": 10,
    "esquivar": 156,
    "bloqueo": 138,
    "golpe_debil": 192,
    "golpe_fuerte": 194,
    "combo": 198,
    "patada": 207,
    "cargar_ki": 125,
    "teletransporte": 384,
    "recibir_golpe": 178,
    "derribado": 187,
    "victoria": 403,
}
# Si el nombre no está arriba, se busca por cómo empieza.
PREFIJOS = (("rafaga", 129), ("tecnica", 214), ("golpe", 192), ("patada", 207), ("esquiv", 156), ("carga", 125))
NOMBRES = {
    0: "Idle", 10: "ForwardRight_Run_Fight", 89: "Combat_Stance", 125: "Charged_Spell_Cast",
    129: "mage_soell_cast", 138: "Block1", 156: "Stand_Dodge", 178: "Hit_Reaction", 187: "Knock_Down",
    192: "Right_Jab_from_Guard", 194: "Right_Uppercut_from_Guard", 198: "Punch_Combo",
    207: "Roundhouse_Kick", 214: "Punch_Forward_with_Both_Fists", 384: "Quick_Step_and_Spin_Dodge",
    403: "Victory_Fist_Pump",
}


class AgenteMeshy:
    nombre = "meshy"
    tipos = frozenset({"concepto", "modelo3d", "rig", "animacion"})
    AJUSTES: tuple[str, ...] = ("modelo_imagen", "caras", "limite")

    def __init__(
        self,
        clave: str | None = None,
        transporte: Transporte | None = None,
        dormir=time.sleep,
        reloj=time.monotonic,
        intervalo: float = 5.0,
        limite: float = 900.0,
        modelo_imagen: str = "nano-banana-2",
        caras: int = 30000,
    ):
        if isinstance(caras, bool) or not isinstance(caras, int) or not 100 <= caras <= 300000:
            raise ValueError("caras tiene que ser un número entre 100 y 300000")
        if not isinstance(modelo_imagen, str) or not modelo_imagen:
            raise ValueError("modelo_imagen tiene que ser el nombre de un modelo de imagen de Meshy")
        self._clave = (clave if clave is not None else os.environ.get(VARIABLE_CLAVE, "")).strip()
        self._api = Cliente("Meshy", API, {"Authorization": f"Bearer {self._clave}"}, transporte)
        self._dormir = dormir
        self._reloj = reloj
        self.intervalo = intervalo
        self.limite = limite
        self.modelo_imagen = modelo_imagen
        self.caras = caras

    def disponible(self) -> str | None:
        if not self._clave:
            return f"Falta la clave de Meshy: define la variable de entorno {VARIABLE_CLAVE}."
        return None

    def generar(self, ctx: Contexto) -> Resultado:
        tipo = ctx.tarea.tipo
        if tipo == "concepto":
            return self._concepto(ctx)
        if tipo == "modelo3d":
            return self._modelo(ctx)
        if tipo == "rig":
            return self._rig(ctx)
        if tipo == "animacion":
            return self._animacion(ctx)
        raise ErrorAgente(f"Meshy no hace '{tipo}'.")

    # --- tipos de recurso ------------------------------------------------------------------

    def _concepto(self, ctx: Contexto) -> Resultado:
        d = ctx.tarea.datos
        prompt = (
            f"{d['estilo']} Character design of {d['personaje']}: {d['descripcion']} "
            "Full body, front view, standing in A-pose, plain white background, no text."
        )
        if ctx.motivo_rechazo:
            prompt += f" Change from the previous version: {ctx.motivo_rechazo}"
        cuerpo = {"ai_model": self.modelo_imagen, "prompt": prompt, "pose_mode": "a-pose", "aspect_ratio": "3:4"}
        datos = self._tarea(ctx, "/openapi/v1/text-to-image", cuerpo, "imagen_meshy")
        urls = datos.get("image_urls") or []
        if not urls:
            raise ErrorAgente("Meshy terminó sin devolver la imagen.")
        imagen = self._api.bajar(urls[0])
        ruta = ctx.archivo("concepto" + extension_de_imagen(imagen))
        ruta.write_bytes(imagen)
        return Resultado([ruta], f"Imagen de Meshy ({self.modelo_imagen}), de frente y en pose A para pasarla a 3D.")

    def _modelo(self, ctx: Contexto) -> Resultado:
        d = ctx.tarea.datos
        textura = d.get("descripcion", "")
        if ctx.motivo_rechazo:
            textura = f"{textura} {ctx.motivo_rechazo}"
        cuerpo: dict = {
            "ai_model": "latest",
            "should_texture": True,
            "should_remesh": True,
            "target_polycount": self.caras,
            "pose_mode": "a-pose",
            "target_formats": ["glb"],
            "texture_prompt": textura[:800],
        }
        id_imagen = next((m["imagen_meshy"] for m in ctx.memorias.values() if m.get("imagen_meshy")), None)
        if id_imagen:
            cuerpo["input_task_id"] = id_imagen  # la imagen ya está en Meshy: no hace falta subirla
        else:
            imagen = primer_archivo(ctx, (".png", ".jpg", ".jpeg", ".webp"))
            if imagen is None:
                raise ErrorAgente(
                    "Meshy necesita el arte conceptual como imagen PNG, JPG o WebP."
                    " El concepto actual no lo es (¿lo hizo el agente simulado?)."
                )
            cuerpo["image_url"] = uri_de_datos(imagen, 20)
        datos = self._tarea(ctx, "/openapi/v1/image-to-3d", cuerpo, "modelo_meshy")
        url = (datos.get("model_urls") or {}).get("glb")
        if not url:
            raise ErrorAgente("Meshy terminó sin devolver el modelo GLB.")
        ruta = ctx.archivo("modelo.glb")
        ruta.write_bytes(self._api.bajar(url))
        archivos = [ruta]
        archivos += self._miniatura(ctx, datos.get("thumbnail_url"))
        return Resultado(archivos, f"Modelo 3D de Meshy con textura, unas {self.caras} caras, en pose A.")

    def _rig(self, ctx: Contexto) -> Resultado:
        modelo = primer_archivo(ctx, (".glb",))
        if modelo is None:
            raise ErrorAgente(
                "El esqueleto de Meshy necesita un modelo .glb con textura."
                " El paso anterior no lo ha entregado (¿lo hizo el agente simulado?)."
            )
        altura = float(ctx.tarea.datos.get("altura") or 1.75)
        cuerpo = {"model_url": uri_de_datos(modelo, 100), "height_meters": altura}
        datos = self._tarea(ctx, "/openapi/v1/rigging", cuerpo, "rig_meshy")
        resultado = datos.get("result") or {}
        url = resultado.get("rigged_character_glb_url")
        if not url:
            raise ErrorAgente("Meshy terminó sin devolver el modelo con esqueleto.")
        ruta = ctx.archivo("modelo_rig.glb")
        ruta.write_bytes(self._api.bajar(url))
        archivos = [ruta]
        basicas = resultado.get("basic_animations") or {}
        for nombre, clave in (("andar", "walking_glb_url"), ("correr", "running_glb_url")):
            if basicas.get(clave):
                try:
                    extra = ctx.archivo(f"{nombre}.glb")
                    extra.write_bytes(self._api.bajar(basicas[clave]))
                    archivos.append(extra)
                except ErrorAgente:
                    pass  # las animaciones básicas son un regalo: si fallan, el esqueleto vale igual
        return Resultado(archivos, f"Esqueleto de Meshy para {altura:g} m de altura.")

    def _animacion(self, ctx: Contexto) -> Resultado:
        id_rig = next((m["rig_meshy"] for m in ctx.memorias.values() if m.get("rig_meshy")), None)
        if not id_rig:
            raise ErrorAgente(
                "Las animaciones de Meshy necesitan que el esqueleto también lo haga Meshy:"
                ' pon rig = "meshy" en [fabrica.proveedores].'
            )
        accion, origen = self._accion(ctx)
        datos = self._tarea(ctx, "/openapi/v1/animations", {"rig_task_id": id_rig, "action_id": accion}, "animacion_meshy")
        url = (datos.get("result") or {}).get("animation_glb_url")
        if not url:
            raise ErrorAgente("Meshy terminó sin devolver la animación.")
        ruta = ctx.archivo(f"{ctx.tarea.nombre}.glb")
        ruta.write_bytes(self._api.bajar(url))
        nombre = f" ({NOMBRES[accion]})" if accion in NOMBRES else ""
        return Resultado(
            [ruta],
            f"Acción {accion}{nombre} de la biblioteca de Meshy, {origen}."
            f" Para cambiarla, recházala con el número de otra acción de {BIBLIOTECA}.",
        )

    def _accion(self, ctx: Contexto) -> tuple[int, str]:
        motivo = ctx.motivo_rechazo.strip()
        if motivo.isdigit():
            return int(motivo), "la que pediste al rechazar"
        indicada = ctx.tarea.datos.get("accion")
        if isinstance(indicada, int):
            return indicada, "indicada en juego.toml"
        if isinstance(indicada, str):
            raise ErrorAgente(
                f"Para Meshy, acciones.{ctx.tarea.nombre} tiene que ser el número de una acción de {BIBLIOTECA}."
            )
        nombre = ctx.tarea.datos["animacion"]
        if nombre in ACCIONES:
            return ACCIONES[nombre], f"elegida por defecto para «{nombre}»"
        for prefijo, accion in PREFIJOS:
            if nombre.startswith(prefijo):
                return accion, f"elegida por defecto para «{nombre}»"
        raise ErrorAgente(
            f"No sé qué animación de Meshy usar para «{nombre}». Busca una en {BIBLIOTECA} y ponla en"
            f" juego.toml, dentro del personaje: [personajes.acciones] {nombre} = <número>"
        )

    # --- infraestructura ---------------------------------------------------------------------

    def _tarea(self, ctx: Contexto, ruta: str, cuerpo: dict, campo: str) -> dict:
        """Pide la tarea (o retoma la que quedó a medias) y espera a que Meshy la termine."""
        clave = clave_intento(ctx)
        memoria = ctx.memoria
        if memoria.get("tarea") and memoria.get("clave") == clave and memoria.get("ruta") == ruta:
            id_tarea = memoria["tarea"]
        else:
            respuesta = self._api.json("POST", ruta, cuerpo)
            id_tarea = respuesta.get("result")
            if not isinstance(id_tarea, str) or not id_tarea:
                raise ErrorAgente("Meshy no devolvió el id de la tarea.")
            memoria.update({"tarea": id_tarea, "clave": clave, "ruta": ruta})
        datos = esperar(
            lambda: self._api.json("GET", f"{ruta}/{id_tarea}"),
            _situacion, "Meshy", self.intervalo, self.limite, self._dormir, self._reloj,
        )
        if _situacion(datos) == "fallo":
            memoria.pop("tarea", None)  # la próxima vez se pide de nuevo
            error = (datos.get("task_error") or {}).get("message") or datos.get("status")
            raise ErrorAgente(f"Meshy no pudo hacer la tarea: {error}")
        memoria[campo] = id_tarea
        return datos

    def _miniatura(self, ctx: Contexto, url: str | None) -> list:
        if not url:
            return []
        try:
            imagen = self._api.bajar(url)
        except ErrorAgente:
            return []  # la miniatura solo sirve para revisar: no merece un fallo
        ruta = ctx.archivo("miniatura" + extension_de_imagen(imagen))
        ruta.write_bytes(imagen)
        return [ruta]


def _situacion(datos: dict) -> str:
    estado = datos.get("status")
    if estado == "SUCCEEDED":
        return "ok"
    if estado in ("FAILED", "CANCELED"):
        return "fallo"
    return "sigue"
