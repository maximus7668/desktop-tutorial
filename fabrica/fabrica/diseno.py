"""Lee y valida juego.toml: el documento de diseño del que sale todo el trabajo de la fábrica."""

from __future__ import annotations

import difflib
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

# Cadena de producción de un personaje, más los recursos sueltos.
TIPOS = ("concepto", "modelo3d", "limpieza", "rig", "animacion", "voz", "sonido", "musica")
APROBAR_POR_DEFECTO = ("concepto", "modelo3d", "animacion", "voz")
# Son prefijos de tareas (sonido/..., musica/...): un personaje con ese id chocaría con ellas.
IDS_RESERVADOS = frozenset({"sonido", "musica"})

_ID = re.compile(r"^[a-z0-9][a-z0-9_]{0,47}$")
_CLAVES = {
    "raiz": ("juego", "fabrica", "personajes", "sonidos", "musica"),
    "juego": ("nombre", "estilo"),
    "fabrica": ("proveedores", "aprobar", "intentos_max"),
    "personaje": ("id", "nombre", "descripcion", "voz", "voz_id", "animaciones", "frases"),
    "sonido": ("id", "descripcion", "duracion", "bucle"),
    "musica": ("id", "descripcion", "duracion", "instrumental"),
}


class ErrorDiseno(ValueError):
    """juego.toml tiene algo que hay que corregir a mano; el mensaje dice qué y dónde."""


@dataclass(frozen=True)
class Personaje:
    id: str
    nombre: str
    descripcion: str
    voz: str
    voz_id: str
    animaciones: tuple[str, ...]
    frases: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Sonido:
    id: str
    descripcion: str
    duracion: float | None
    bucle: bool = False  # sonido continuo (aura, rayo...): tiene que poder repetirse sin corte


@dataclass(frozen=True)
class Pista:
    id: str
    descripcion: str
    duracion: float | None
    instrumental: bool


@dataclass(frozen=True)
class Diseno:
    nombre: str
    estilo: str
    personajes: tuple[Personaje, ...]
    sonidos: tuple[Sonido, ...]
    musica: tuple[Pista, ...]
    proveedores: dict[str, str]
    aprobar: frozenset[str]
    intentos_max: int


def cargar(ruta: Path) -> Diseno:
    try:
        with open(ruta, "rb") as f:
            datos = tomllib.load(f)
    except FileNotFoundError:
        raise ErrorDiseno(
            f"No encuentro {ruta}. Crea un proyecto con: python -m fabrica nuevo <carpeta>"
        ) from None
    except tomllib.TOMLDecodeError as e:
        raise ErrorDiseno(f"{ruta.name} no es TOML válido: {e}") from None
    return validar(datos)


def validar(datos: dict) -> Diseno:
    _sin_claves_raras(datos, "raiz", "juego.toml")
    juego = _tabla(datos.get("juego"), "[juego]", obligatoria=True)
    _sin_claves_raras(juego, "juego", "[juego]")
    fabrica = _tabla(datos.get("fabrica"), "[fabrica]")
    _sin_claves_raras(fabrica, "fabrica", "[fabrica]")

    proveedores = dict.fromkeys(TIPOS, "simulado")
    for tipo, nombre in _tabla(fabrica.get("proveedores"), "[fabrica.proveedores]").items():
        if tipo not in TIPOS:
            raise ErrorDiseno(
                f"[fabrica.proveedores] no conoce el tipo '{tipo}'.{_sugerencia(tipo, TIPOS)}"
                f" Tipos: {', '.join(TIPOS)}"
            )
        proveedores[tipo] = _texto(nombre, f"[fabrica.proveedores] {tipo}")

    aprobar = fabrica.get("aprobar", list(APROBAR_POR_DEFECTO))
    if not isinstance(aprobar, list):
        raise ErrorDiseno('[fabrica] aprobar tiene que ser una lista, por ejemplo ["concepto", "modelo3d"]')
    for tipo in aprobar:
        if tipo not in TIPOS:
            raise ErrorDiseno(
                f"[fabrica] aprobar incluye '{tipo}', que no es un tipo.{_sugerencia(tipo, TIPOS)}"
                f" Tipos: {', '.join(TIPOS)}"
            )

    intentos = fabrica.get("intentos_max", 3)
    if isinstance(intentos, bool) or not isinstance(intentos, int) or intentos < 1:
        raise ErrorDiseno("[fabrica] intentos_max tiene que ser un número entero mayor que 0")

    personajes = tuple(_personaje(p, i) for i, p in enumerate(_lista(datos, "personajes"), 1))
    _unicos([p.id for p in personajes], "[[personajes]]")
    sonidos = tuple(_sonido(s, i) for i, s in enumerate(_lista(datos, "sonidos"), 1))
    _unicos([s.id for s in sonidos], "[[sonidos]]")
    musica = tuple(_pista(m, i) for i, m in enumerate(_lista(datos, "musica"), 1))
    _unicos([m.id for m in musica], "[[musica]]")

    return Diseno(
        nombre=_texto(juego.get("nombre"), "[juego] nombre"),
        estilo=_texto(juego.get("estilo"), "[juego] estilo"),
        personajes=personajes,
        sonidos=sonidos,
        musica=musica,
        proveedores=proveedores,
        aprobar=frozenset(aprobar),
        intentos_max=intentos,
    )


def _personaje(datos: object, i: int) -> Personaje:
    donde = f"[[personajes]] número {i}"
    p = _tabla(datos, donde, obligatoria=True)
    pid = _id(p.get("id"), f"{donde}: id")
    if pid in IDS_RESERVADOS:
        raise ErrorDiseno(f"{donde}: el id '{pid}' está reservado; elige otro")
    donde = f"personaje '{pid}'"
    _sin_claves_raras(p, "personaje", donde)

    lista = p.get("animaciones", [])
    if not isinstance(lista, list):
        raise ErrorDiseno(f'{donde}: animaciones tiene que ser una lista, por ejemplo ["guardia", "patada"]')
    animaciones = tuple(_id(a, f"{donde}: animaciones") for a in lista)
    _unicos(animaciones, f"{donde}: animaciones")

    frases = tuple(
        (_id(clave, f"{donde}: frases"), _texto(texto, f"{donde}: frases.{clave}"))
        for clave, texto in _tabla(p.get("frases"), f"{donde}: frases").items()
    )
    return Personaje(
        id=pid,
        nombre=_texto(p.get("nombre"), f"{donde}: nombre"),
        descripcion=_texto(p.get("descripcion"), f"{donde}: descripcion"),
        voz=_texto(p.get("voz"), f"{donde}: voz", opcional=True),
        voz_id=_texto(p.get("voz_id"), f"{donde}: voz_id", opcional=True),
        animaciones=animaciones,
        frases=frases,
    )


def _sonido(datos: object, i: int) -> Sonido:
    donde = f"[[sonidos]] número {i}"
    s = _tabla(datos, donde, obligatoria=True)
    sid = _id(s.get("id"), f"{donde}: id")
    donde = f"sonido '{sid}'"
    _sin_claves_raras(s, "sonido", donde)
    bucle = s.get("bucle", False)
    if not isinstance(bucle, bool):
        raise ErrorDiseno(f"{donde}: bucle tiene que ser true o false")
    return Sonido(
        id=sid,
        descripcion=_texto(s.get("descripcion"), f"{donde}: descripcion"),
        duracion=_duracion(s.get("duracion"), f"{donde}: duracion"),
        bucle=bucle,
    )


def _pista(datos: object, i: int) -> Pista:
    donde = f"[[musica]] número {i}"
    m = _tabla(datos, donde, obligatoria=True)
    mid = _id(m.get("id"), f"{donde}: id")
    donde = f"música '{mid}'"
    _sin_claves_raras(m, "musica", donde)
    instrumental = m.get("instrumental", True)
    if not isinstance(instrumental, bool):
        raise ErrorDiseno(f"{donde}: instrumental tiene que ser true o false")
    return Pista(
        id=mid,
        descripcion=_texto(m.get("descripcion"), f"{donde}: descripcion"),
        duracion=_duracion(m.get("duracion"), f"{donde}: duracion"),
        instrumental=instrumental,
    )


def _tabla(valor: object, donde: str, *, obligatoria: bool = False) -> dict:
    if valor is None:
        if obligatoria:
            raise ErrorDiseno(f"Falta {donde}")
        return {}
    if not isinstance(valor, dict):
        raise ErrorDiseno(f"{donde} tiene que ser una tabla")
    return valor


def _lista(datos: dict, clave: str) -> list:
    valor = datos.get(clave, [])
    if not isinstance(valor, list):
        raise ErrorDiseno(f"{clave} tiene que escribirse como [[{clave}]]")
    return valor


def _texto(valor: object, donde: str, *, opcional: bool = False) -> str:
    if valor is None and opcional:
        return ""
    if not isinstance(valor, str):
        raise ErrorDiseno(f"{donde}: falta o no es un texto")
    # Las descripciones largas van en varias líneas; los agentes las reciben en una.
    valor = " ".join(valor.split())
    if not valor and not opcional:
        raise ErrorDiseno(f"{donde}: está vacío")
    return valor


def _id(valor: object, donde: str) -> str:
    texto = _texto(valor, donde)
    if not _ID.match(texto):
        raise ErrorDiseno(
            f"{donde}: '{texto}' no vale como id. Usa minúsculas sin acentos, números y _"
            " (por ejemplo 'golpe_fuerte')"
        )
    return texto


def _duracion(valor: object, donde: str) -> float | None:
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or valor <= 0:
        raise ErrorDiseno(f"{donde} tiene que ser un número de segundos mayor que 0")
    return float(valor)


def _unicos(ids: list[str] | tuple[str, ...], donde: str) -> None:
    vistos: set[str] = set()
    for i in ids:
        if i in vistos:
            raise ErrorDiseno(f"{donde}: el id '{i}' está repetido")
        vistos.add(i)


def _sin_claves_raras(tabla: dict, tipo: str, donde: str) -> None:
    for clave in tabla:
        if clave not in _CLAVES[tipo]:
            raise ErrorDiseno(f"{donde}: no conozco la clave '{clave}'.{_sugerencia(clave, _CLAVES[tipo])}")


def _sugerencia(valor: object, opciones: tuple[str, ...]) -> str:
    if not isinstance(valor, str):
        return ""
    parecidas = difflib.get_close_matches(valor, opciones, n=1)
    return f" ¿Querías decir '{parecidas[0]}'?" if parecidas else ""
