"""Agentes que generan cada tipo de recurso.

Cada proveedor (simulado, elevenlabs...) es un agente intercambiable: el director no sabe cómo
trabaja por dentro, solo le pasa un Contexto y recibe los archivos que ha creado. Para conectar
una herramienta nueva basta con escribir una clase con `nombre`, `tipos`, `disponible()` y
`generar()`, y añadirla en `proveedores()`.

El revisor (Claude) no genera nada: mira lo que hacen los demás y manda rehacer lo que esté mal.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ..plan import Tarea


@dataclass
class Contexto:
    tarea: Tarea
    juego: str
    estilo: str
    carpeta: Path  # donde el agente tiene que dejar sus archivos
    entradas: dict[str, list[Path]] = field(default_factory=dict)  # archivos de cada dependencia
    motivo_rechazo: str = ""  # lo que pediste cambiar la última vez
    intento: int = 1
    memoria: dict = field(default_factory=dict)  # se guarda en el registro aunque el agente falle
    memorias: dict[str, dict] = field(default_factory=dict)  # memoria de cada dependencia (solo leer)
    proyecto: Path | None = None  # carpeta del proyecto (para rutas relativas de los ajustes)
    rechazos: int = 0  # veces que se mandó rehacer (tú o el revisor): cada vez es un pedido nuevo
    # Guarda el registro ya. Quien encarga un trabajo remoto la llama al apuntar su id en memoria:
    # si la fábrica se cierra mientras espera, el encargo se recoge luego sin pagarlo otra vez.
    guardar: Callable[[], None] = lambda: None

    def archivo(self, nombre: str) -> Path:
        return self.carpeta / nombre


@dataclass
class Resultado:
    archivos: list[Path]
    nota: str = ""


@dataclass
class Revision:
    """Lo que el revisor necesita para juzgar un recurso recién hecho."""

    tarea: Tarea
    juego: str
    estilo: str
    archivos: list[Path]  # lo que hay que revisar
    referencias: list[Path] = field(default_factory=list)  # arte conceptual aprobado del personaje
    ficha: dict = field(default_factory=dict)  # personaje: nombre, descripcion, altura
    nota: str = ""  # lo que contó el agente que lo hizo
    motivo_rechazo: str = ""  # el cambio que se pidió para esta versión


@dataclass
class Veredicto:
    aprobado: bool
    comentario: str = ""  # una frase para ti
    problemas: list[str] = field(default_factory=list)  # para ti
    correccion: str = ""  # para el agente que lo rehace (le llega como motivo del rechazo)


class ErrorAgente(RuntimeError):
    """Fallo que el agente explica en lenguaje claro."""


class Agente(Protocol):
    nombre: str
    tipos: frozenset[str]
    # Ajustes que admite en [fabrica.<nombre>] de juego.toml (llegan como argumentos al crearlo).
    AJUSTES: tuple[str, ...]

    def disponible(self) -> str | None:
        """None si puede trabajar; si no, el motivo (por ejemplo, que falta una clave de API)."""

    def generar(self, ctx: Contexto) -> Resultado: ...


class Revisor(Protocol):
    nombre: str
    tipos: frozenset[str]  # vacío: no hace recursos
    AJUSTES: tuple[str, ...]
    rehacer: int  # veces que puede mandar rehacer algo antes de pasártelo a ti

    def disponible(self) -> str | None: ...

    def revisar(self, revision: Revision) -> Veredicto | None:
        """None si no hay nada que pueda mirar (por ejemplo, ninguna imagen)."""


def proveedores() -> dict[str, Callable[..., Agente | Revisor]]:
    from .blender import AgenteBlender
    from .claude import RevisorClaude
    from .comfyui import AgenteComfyUI
    from .copiar import AgenteCopiar
    from .elevenlabs import AgenteElevenLabs
    from .meshy import AgenteMeshy
    from .simulado import AgenteSimulado

    return {
        AgenteSimulado.nombre: AgenteSimulado,
        AgenteCopiar.nombre: AgenteCopiar,
        AgenteBlender.nombre: AgenteBlender,
        AgenteComfyUI.nombre: AgenteComfyUI,
        AgenteElevenLabs.nombre: AgenteElevenLabs,
        AgenteMeshy.nombre: AgenteMeshy,
        RevisorClaude.nombre: RevisorClaude,
    }
