"""De una idea en tus palabras a un juego.toml completo, con Claude como director creativo."""

from __future__ import annotations

import json
import re
import textwrap
import tomllib
import unicodedata
from importlib import resources

from .agentes import ErrorAgente
from .agentes.claude import ClienteClaude
from .diseno import IDS_RESERVADOS, ErrorDiseno, validar

SISTEMA = """\
You are the creative director of an AI asset factory for a 3D anime arena fighting game. The user
describes the game they want in their own words (usually in Spanish). Turn the idea into the design
document the factory works from. For every character the factory generates concept art, a 3D model, a
skeleton, animations and voice lines; it also generates sound effects and music. Everything you write
is sent to generative tools as a prompt, so be concrete and visual.

Rules:
- Original creations only: invent new names, characters, techniques and titles. If the idea mentions an
  existing franchise (anime, games, films), use it only as a reference for tone and art style; never
  reuse its characters, names, signature moves or trademarks.
- Follow the user's idea: number of characters, themes, setting and tone. If they don't say how many
  characters, make 4.
- nombre: the game's title.
- estilo: the shared visual style, in Spanish, 2 to 4 sentences: rendering (for example cel-shading and
  outlines), palette, proportions, effects. It goes in front of every concept-art prompt.
- personajes:
  - id: short lowercase ASCII identifier (letters, digits and _), for example "ren".
  - nombre: full name.
  - descripcion: in Spanish, purely visual and concrete, 3 to 5 sentences: age, build, hair (style and
    colors), eyes, outfit (pieces, colors, materials), accessories and the color of their aura. Describe
    the whole body so an image model can draw it from head to toe. Avoid what breaks image-to-3D
    conversion or rigging: very long capes or loose cloth, floating objects, wings, tails, weapons fused
    to the body. Make the characters easy to tell apart by silhouette and palette.
  - voz: in Spanish, the voice for casting: age, timbre and attitude.
  - altura: height in meters (1.4 to 2.3 for human-like fighters).
  - animaciones: first the base set every fighter needs, in this order: guardia, correr, volar,
    esquivar, golpe_debil, golpe_fuerte, patada, cargar_ki, recibir_golpe, derribado. Then 1 to 3
    signature moves: an energy blast named "rafaga_<word>" and/or a special technique named
    "tecnica_<word>" (lowercase ASCII), plus "teletransporte" if it suits the character.
  - frases: 5 voice lines in Spanish with these ids: entrada (entering the fight), cargar (powering up),
    tecnica (shouting the name of the special technique), victoria, derrota. Short, punchy, in character.
- sonidos: sound effects described in English (sound models understand English best), each with a
  duration in seconds (0.5 to 30); bucle=true only for continuous sounds that must loop seamlessly.
  Include this standard set with exactly these ids, adapted to the game's theme: golpe, golpe_fuerte,
  bloqueo, aire, rafaga, explosion, impacto, paso, teletransporte, super and ko (one-shot), and carga,
  rayo and choque (loops). Add others only if the idea needs them.
- musica: tracks described in English (genre, instruments, mood, tempo in bpm), 60 to 180 seconds,
  instrumental=true unless the user asks for vocals. At least tema_combate (battle theme) and menu (menu
  theme); add more if the idea suggests them (for example one theme per arena or a final boss).
"""


def _objeto(propiedades: dict) -> dict:
    return {"type": "object", "properties": propiedades, "required": list(propiedades), "additionalProperties": False}


_TEXTO = {"type": "string"}
ESQUEMA = _objeto({
    "nombre": _TEXTO,
    "estilo": _TEXTO,
    "personajes": {"type": "array", "items": _objeto({
        "id": _TEXTO,
        "nombre": _TEXTO,
        "descripcion": _TEXTO,
        "voz": _TEXTO,
        "altura": {"type": "number"},
        "animaciones": {"type": "array", "items": _TEXTO},
        "frases": {"type": "array", "items": _objeto({"id": _TEXTO, "texto": _TEXTO})},
    })},
    "sonidos": {"type": "array", "items": _objeto({
        "id": _TEXTO, "descripcion": _TEXTO, "duracion": {"type": "number"}, "bucle": {"type": "boolean"},
    })},
    "musica": {"type": "array", "items": _objeto({
        "id": _TEXTO, "descripcion": _TEXTO, "duracion": {"type": "number"}, "instrumental": {"type": "boolean"},
    })},
})


def idear(idea: str, claude: ClienteClaude) -> str:
    """Pide el diseño a Claude y devuelve el texto de un juego.toml que la fábrica acepta."""
    idea = idea.strip()
    if not idea:
        raise ErrorAgente("Cuenta tu idea: de qué va el juego, cuántos personajes, cómo son...")
    datos = claude.json(SISTEMA, [{"type": "text", "text": idea}], ESQUEMA, max_tokens=32000)
    return escribir(datos, idea)


def escribir(datos: dict, idea: str) -> str:
    """Convierte la respuesta de Claude en juego.toml, con los id arreglados y comprobado."""
    personajes = [p for p in _lista(datos, "personajes") if _limpio(p.get("nombre")) and _limpio(p.get("descripcion"))]
    if not personajes:
        raise ErrorAgente("Claude no propuso ningún personaje. Describe un poco más la idea y vuelve a probar.")
    lineas = _cabecera(idea)
    lineas += [
        "[juego]",
        f"nombre = {_cadena(_limpio(datos.get('nombre')) or 'Juego sin nombre')}",
        f"estilo = {_texto_largo(_limpio(datos.get('estilo')) or 'Anime 3D con cel-shading.')}",
        "",
        _seccion_fabrica(),
    ]

    ids_personajes: set[str] = set()
    for p in personajes:
        pid = _id(p.get("id") or p.get("nombre"), ids_personajes, IDS_RESERVADOS)
        lineas += [
            "[[personajes]]",
            f"id = {_cadena(pid)}",
            f"nombre = {_cadena(_limpio(p.get('nombre')))}",
            f"descripcion = {_texto_largo(_limpio(p.get('descripcion')))}",
            f"voz = {_cadena(_limpio(p.get('voz')))}",
            'voz_id = ""  # ID de una voz de tu biblioteca de ElevenLabs',
        ]
        altura = p.get("altura")
        if isinstance(altura, (int, float)) and not isinstance(altura, bool) and 0.3 <= altura <= 10:
            lineas.append(f"altura = {round(float(altura), 2):g}  # metros")
        animaciones = list(dict.fromkeys(_id(a, set()) for a in p.get("animaciones") or [] if _limpio(a)))
        lineas.append(f"animaciones = {_lista_toml(animaciones)}")  # sin repetidas: cada una es trabajo
        usadas: set[str] = set()
        frases = [(_id(f.get("id"), usadas), _limpio(f.get("texto"))) for f in p.get("frases") or []
                  if isinstance(f, dict) and _limpio(f.get("id")) and _limpio(f.get("texto"))]
        if frases:
            lineas += ["", "[personajes.frases]"] + [f"{clave} = {_cadena(texto)}" for clave, texto in frases]
        lineas.append("")

    lineas.append("# Efectos de sonido (salen mejor descritos en inglés). «bucle = true» para los que suenan sin parar.")
    usados: set[str] = set()
    for s in _lista(datos, "sonidos"):
        if not _limpio(s.get("id")) or not _limpio(s.get("descripcion")):
            continue
        lineas += [
            "[[sonidos]]",
            f"id = {_cadena(_id(s['id'], usados))}",
            f"descripcion = {_cadena(_limpio(s['descripcion']))}",
            f"duracion = {_segundos(s.get('duracion'), 0.5, 30, 1.0)}",
        ]
        if s.get("bucle") is True:
            lineas.append("bucle = true")
        lineas.append("")

    usados = set()
    for m in _lista(datos, "musica"):
        if not _limpio(m.get("id")) or not _limpio(m.get("descripcion")):
            continue
        lineas += [
            "[[musica]]",
            f"id = {_cadena(_id(m['id'], usados))}",
            f"descripcion = {_cadena(_limpio(m['descripcion']))}",
            f"duracion = {_segundos(m.get('duracion'), 10, 600, 90)}",
            f"instrumental = {'false' if m.get('instrumental') is False else 'true'}",
            "",
        ]

    texto = "\n".join(lineas).rstrip() + "\n"
    try:
        validar(tomllib.loads(texto))
    except (tomllib.TOMLDecodeError, ErrorDiseno) as e:
        raise ErrorAgente(f"El diseño que propuso Claude no es válido ({e}). Vuelve a intentarlo.") from None
    return texto


def _cabecera(idea: str) -> list[str]:
    lineas = ["# juego.toml escrito por Claude («python -m fabrica idear») a partir de esta idea:"]
    for parrafo in idea.splitlines():
        if _limpio(parrafo):
            lineas += ["#   " + l for l in textwrap.wrap(_limpio(parrafo), 92)]
    return lineas + [
        "#",
        "# Es un punto de partida: cámbialo a tu gusto antes de ejecutar. Cada vez que cambies algo",
        "# y ejecutes, la fábrica rehace solo lo afectado.",
        '# Los id usan minúsculas sin acentos, números y _ (por ejemplo "golpe_fuerte").',
        "",
    ]


def _seccion_fabrica() -> str:
    """La parte [fabrica] de la plantilla, con sus explicaciones de proveedores y ajustes."""
    plantilla = resources.files("fabrica").joinpath("plantilla/juego.toml").read_text(encoding="utf-8")
    inicio = plantilla.find("\n[fabrica]\n")
    fin = plantilla.find("\n[[personajes]]")
    if inicio < 0 or fin < inicio:
        return '[fabrica]\naprobar = ["concepto", "modelo3d", "animacion", "voz"]\nintentos_max = 3\n'
    return plantilla[inicio + 1 : fin].rstrip() + "\n"


def _lista(datos: dict, clave: str) -> list[dict]:
    valor = datos.get(clave)
    return [x for x in valor if isinstance(x, dict)] if isinstance(valor, list) else []


def _limpio(valor: object) -> str:
    return " ".join(valor.split()) if isinstance(valor, str) else ""


def _id(valor: object, usados: set[str], reservados: frozenset[str] = frozenset()) -> str:
    """Un id válido y único: sin acentos, en minúsculas, con _ en lugar de espacios."""
    texto = unicodedata.normalize("NFKD", _limpio(valor)).encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9]+", "_", texto).strip("_")[:40] or "elemento"
    candidato, n = base, 2
    while candidato in usados or candidato in reservados:
        candidato, n = f"{base}_{n}", n + 1
    usados.add(candidato)
    return candidato


def _cadena(texto: str) -> str:
    # Una cadena JSON es una cadena básica de TOML válida, salvo el carácter DEL.
    return json.dumps(texto, ensure_ascii=False).replace("\x7f", "\\u007f")


def _texto_largo(texto: str) -> str:
    if len(texto) <= 90:
        return _cadena(texto)
    lineas = textwrap.wrap(texto, 96, break_long_words=False, break_on_hyphens=False)
    return '"""\n' + "\n".join(_cadena(l)[1:-1] for l in lineas) + '\n"""'


def _lista_toml(valores: list[str]) -> str:
    if not valores:
        return "[]"
    filas = [", ".join(_cadena(v) for v in valores[i : i + 6]) for i in range(0, len(valores), 6)]
    return "[\n  " + ",\n  ".join(filas) + ",\n]"


def _segundos(valor: object, minimo: float, maximo: float, defecto: float) -> str:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        valor = defecto
    return f"{round(min(max(float(valor), minimo), maximo), 1):g}"
