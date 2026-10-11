"""Agentes que generan cada tipo de recurso.

Cada proveedor (simulado, elevenlabs...) es un agente intercambiable: el director no sabe cómo
trabaja por dentro, solo le pasa un Contexto y recibe los archivos que ha creado. Para conectar
una herramienta nueva basta con escribir una clase con `nombre`, `tipos`, `disponible()` y
`generar()`, y añadirla en `proveedores()`.
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

    def archivo(self, nombre: str) -> Path:
        return self.carpeta / nombre


@dataclass
class Resultado:
    archivos: list[Path]
    nota: str = ""


class ErrorAgente(RuntimeError):
    """Fallo que el agente explica en lenguaje claro."""


class Agente(Protocol):
    nombre: str
    tipos: frozenset[str]

    def disponible(self) -> str | None:
        """None si puede trabajar; si no, el motivo (por ejemplo, que falta una clave de API)."""

    def generar(self, ctx: Contexto) -> Resultado: ...


def proveedores() -> dict[str, Callable[[], Agente]]:
    from .elevenlabs import AgenteElevenLabs
    from .simulado import AgenteSimulado

    return {AgenteSimulado.nombre: AgenteSimulado, AgenteElevenLabs.nombre: AgenteElevenLabs}
