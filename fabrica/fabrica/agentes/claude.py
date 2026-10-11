"""Claude, de Anthropic: revisa las imágenes antes que tú y escribe el diseño a partir de una idea.

Usa la librería oficial (pip install anthropic) con tu clave en la variable ANTHROPIC_API_KEY
(o un perfil de «ant auth login»). Cada petición gasta unos céntimos de tu cuenta de Anthropic.
Si los filtros de seguridad de Claude rechazan una petición, la API la repite con otro modelo de
Claude (respaldo en el servidor, fallbacks="default").
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from . import ErrorAgente, Revision, Veredicto

MODELO = "claude-opus-5-5"
ESFUERZOS = ("low", "medium", "high", "xhigh", "max")
VARIABLE_CLAVE = "ANTHROPIC_API_KEY"
BETA_RESPALDO = "server-side-fallback-2026-07-01"  # el que pide fallbacks="default"
MAX_IMAGEN = 5 * 1024 * 1024  # bytes por imagen que se envía


class ClienteClaude:
    """Una petición a Claude cuya respuesta es JSON con la forma de un esquema (salida estructurada)."""

    def __init__(self, modelo: str = MODELO, esfuerzo: str = "medium", limite: float = 300.0, cliente=None):
        if not isinstance(modelo, str) or not modelo.startswith("claude-"):
            raise ValueError("modelo tiene que ser el nombre de un modelo de Claude, por ejemplo claude-opus-5-5")
        if esfuerzo not in ESFUERZOS:
            raise ValueError(f"esfuerzo tiene que ser uno de: {', '.join(ESFUERZOS)}")
        if isinstance(limite, bool) or not isinstance(limite, (int, float)) or limite <= 0:
            raise ValueError("limite tiene que ser un número de segundos mayor que 0")
        self.modelo = modelo
        self.esfuerzo = esfuerzo
        self.limite = float(limite)
        self._cliente = cliente  # las pruebas pasan uno falso; si no, se crea al usarlo

    def disponible(self) -> str | None:
        if self._cliente is not None:
            return None
        try:
            import anthropic
        except ImportError:
            return "Falta la librería de Claude: instálala con «pip install anthropic»."
        try:
            cliente = anthropic.Anthropic(timeout=self.limite, max_retries=3)
        except Exception as e:  # configuración rota (un perfil que no existe...)
            return f"No se pudo preparar Claude: {e}"
        if not (cliente.api_key or cliente.auth_token or cliente.credentials):
            return f"Falta la clave de Claude: define la variable {VARIABLE_CLAVE} (se crea en platform.claude.com)."
        self._cliente = cliente
        return None

    def json(self, sistema: str, contenido: list[dict], esquema: dict, max_tokens: int = 16000) -> dict:
        aviso = self.disponible()
        if aviso:
            raise ErrorAgente(aviso)
        try:
            with self._cliente.beta.messages.stream(
                model=self.modelo,
                max_tokens=max_tokens,
                betas=[BETA_RESPALDO],
                fallbacks="default",
                output_config={"effort": self.esfuerzo, "format": {"type": "json_schema", "schema": esquema}},
                system=sistema,
                messages=[{"role": "user", "content": contenido}],
            ) as flujo:
                mensaje = flujo.get_final_message()
        except Exception as e:  # los errores de la librería se explican en claro
            raise ErrorAgente(_explicar(e, self.modelo)) from None
        if mensaje.stop_reason == "refusal":
            detalle = getattr(getattr(mensaje, "stop_details", None), "explanation", None)
            raise ErrorAgente("Claude no quiso responder a esta petición" + (f": {detalle}" if detalle else "."))
        if mensaje.stop_reason == "max_tokens":
            raise ErrorAgente("La respuesta de Claude se cortó por larga. Prueba con un esfuerzo menor.")
        texto = next((b.text for b in mensaje.content if b.type == "text"), "")
        try:
            datos = json.loads(texto)
        except json.JSONDecodeError:
            datos = None
        if not isinstance(datos, dict):
            raise ErrorAgente("Claude devolvió una respuesta que no tiene la forma pedida.")
        return datos


def _explicar(e: Exception, modelo: str) -> str:
    codigo = getattr(e, "status_code", None)
    mensaje = " ".join(str(getattr(e, "message", None) or e or type(e).__name__).split())[:300]
    if codigo == 401:
        return f"Claude no acepta la clave: revisa la variable {VARIABLE_CLAVE}."
    if codigo == 403:
        return f"Tu clave de Claude no tiene permiso para esto: {mensaje}"
    if codigo == 404:
        return f"Claude no encuentra el modelo «{modelo}»: revisa [fabrica.claude] modelo."
    if codigo == 429:
        return "Claude pide esperar (límite de peticiones o de gasto de tu cuenta). Vuelve a intentarlo en un rato."
    if isinstance(codigo, int) and codigo >= 500:
        return f"Claude no está disponible ahora mismo ({codigo}). Vuelve a intentarlo en un rato."
    if codigo is not None:
        return f"Claude respondió {codigo}: {mensaje}"
    return f"No se pudo hablar con Claude: {mensaje}"


# --- revisor -------------------------------------------------------------------------------

SISTEMA_REVISION = """\
You are the quality reviewer of an automated asset pipeline for a 3D anime arena fighting game.
Generators (image models, image-to-3D services, Blender scripts) make each asset and you inspect it
before the human creator sees it. Catch concrete, visible defects that would make the asset unusable
for the next step of the pipeline, or that clearly contradict the character description. You are not
the art director: matters of taste belong to the human, so approve unless you find at least one
concrete defect, and name each defect precisely (what is wrong and where).

What to check, by asset type:
- concepto (concept art that an image-to-3D service will turn into a 3D model): exactly one character;
  the whole body visible from head to feet, nothing cropped; front view; A-pose or T-pose with the arms
  away from the body; plain, uncluttered background; no text, watermark or extra views; no anatomy
  errors (hands, fingers, limbs, face); hair, colors, clothing, build and distinctive features match
  the description; the art style matches.
- modelo3d (render of the textured 3D model): the same character as the reference concept art; no
  missing, fused or melted limbs; head, hands and feet present; texture coherent with the concept
  (colors in the right places, no large smeared or blank areas); arms separated from the body.
- limpieza (render of the model after automatic clean-up): the model stands upright on the ground,
  whole, centered and not cut off; no black or inside-out patches (inverted normals); texture still
  present; proportions consistent with the reference concept art.

If a change was requested for this version, check that it was applied.
Write `comentario` and `problemas` in Spanish (Spain), plainly, for a non-technical game creator.
Write `correccion` in English as a short instruction for the generator to fix the defects (it is
appended to the generation prompt); leave it empty when you approve.
"""

ESQUEMA_VEREDICTO = {
    "type": "object",
    "properties": {
        "aprobado": {"type": "boolean"},
        "comentario": {"type": "string"},
        "problemas": {"type": "array", "items": {"type": "string"}},
        "correccion": {"type": "string"},
    },
    "required": ["aprobado", "comentario", "problemas", "correccion"],
    "additionalProperties": False,
}

QUE_ES = {
    "concepto": "concept art that an image-to-3D service will turn into a textured 3D model",
    "modelo3d": "render of the textured 3D model made from the reference concept art",
    "limpieza": "render of the 3D model after automatic clean-up (scale, origin at the feet, fewer polygons)",
}


class RevisorClaude:
    nombre = "claude"
    tipos: frozenset[str] = frozenset()  # no hace recursos: revisa los de los demás
    AJUSTES: tuple[str, ...] = ("modelo", "esfuerzo", "rehacer", "limite")

    def __init__(
        self, modelo: str = MODELO, esfuerzo: str = "medium", rehacer: int = 2, limite: float = 300.0, cliente=None
    ):
        if isinstance(rehacer, bool) or not isinstance(rehacer, int) or not 0 <= rehacer <= 5:
            raise ValueError("rehacer tiene que ser un número de 0 a 5")
        self.rehacer = rehacer
        self._claude = ClienteClaude(modelo, esfuerzo, limite, cliente)

    def disponible(self) -> str | None:
        return self._claude.disponible()

    def revisar(self, r: Revision) -> Veredicto | None:
        # Se revisa la primera imagen: es la que sigue adelante (la que pasa a 3D, la vista del modelo...).
        ruta = next((ruta for ruta in r.archivos if tipo_de_imagen(ruta)), None)
        if ruta is None:
            return None
        tamano = ruta.stat().st_size
        if tamano > MAX_IMAGEN:
            raise ErrorAgente(f"{ruta.name} ocupa {tamano / 1048576:.1f} MB y Claude admite hasta 5 MB por imagen.")
        referencias = [ref for ref in r.referencias if tipo_de_imagen(ref) and ref.stat().st_size <= MAX_IMAGEN][:2]
        contenido: list[dict] = [{"type": "text", "text": _ficha(r)}]
        for ref in referencias:
            contenido += [{"type": "text", "text": f"REFERENCE, approved concept art ({ref.name}):"}, _imagen(ref)]
        contenido += [{"type": "text", "text": f"TO REVIEW ({ruta.name}):"}, _imagen(ruta)]
        datos = self._claude.json(SISTEMA_REVISION, contenido, ESQUEMA_VEREDICTO)
        problemas = [" ".join(str(p).split()) for p in datos.get("problemas") or [] if str(p).strip()]
        comentario = " ".join(str(datos.get("comentario") or "").split())
        aprobado = datos.get("aprobado") is True
        if not aprobado and not problemas:
            problemas = [comentario or "Claude no dio detalles."]
        return Veredicto(
            aprobado=aprobado,
            comentario=comentario,
            problemas=[] if aprobado else problemas,
            correccion="" if aprobado else " ".join(str(datos.get("correccion") or "").split()),
        )


def _ficha(r: Revision) -> str:
    lineas = [f"Game: {r.juego}", f"Art style: {r.estilo}"]
    if r.ficha.get("nombre"):
        lineas.append(f"Character: {r.ficha['nombre']}. {r.ficha.get('descripcion', '')}".strip())
    if r.ficha.get("altura"):
        lineas.append(f"Character height: {r.ficha['altura']:g} m")
    lineas.append(f"Asset type: {r.tarea.tipo} ({QUE_ES.get(r.tarea.tipo, r.tarea.titulo)})")
    if r.nota:
        lineas.append(f"Generator notes: {r.nota}")
    if r.motivo_rechazo:
        lineas.append(f"Change requested for this version: {r.motivo_rechazo}")
    return "\n".join(lineas)


def tipo_de_imagen(ruta: Path) -> str | None:
    """Tipo de imagen que Claude puede ver (por su contenido, no por la extensión); None si no lo es."""
    try:
        with open(ruta, "rb") as f:
            cabecera = f.read(12)
    except OSError:
        return None
    if cabecera.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if cabecera.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if cabecera[:4] == b"RIFF" and cabecera[8:12] == b"WEBP":
        return "image/webp"
    if cabecera[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return None


def _imagen(ruta: Path) -> dict:
    datos = base64.standard_b64encode(ruta.read_bytes()).decode("ascii")
    return {"type": "image", "source": {"type": "base64", "media_type": tipo_de_imagen(ruta), "data": datos}}
