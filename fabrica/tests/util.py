from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fabrica.agentes import Contexto, Resultado
from fabrica.agentes.simulado import AgenteSimulado

MINIMO = """
[juego]
nombre = "Prueba"
estilo = "anime con cel-shading"

[fabrica]
aprobar = ["concepto"]
intentos_max = 2

[[personajes]]
id = "ren"
nombre = "Ren"
descripcion = "Luchador de fuego"
voz_id = "voz123"
animaciones = ["golpe"]

[personajes.frases]
grito = "¡Ya!"

[[sonidos]]
id = "impacto"
descripcion = "punch impact"
duracion = 0.6
"""


class ConProyecto(unittest.TestCase):
    """Cada prueba trabaja en una carpeta temporal con su propio juego.toml."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.carpeta = Path(self._tmp.name)
        self.escribir(MINIMO)

    def escribir(self, texto: str) -> None:
        (self.carpeta / "juego.toml").write_text(texto, encoding="utf-8")


class Grabador(AgenteSimulado):
    """Agente simulado que apunta cada contexto recibido y puede fallar a propósito."""

    def __init__(self, falla_en: set[str] | None = None):
        self.contextos: list[Contexto] = []
        self.falla_en = falla_en or set()

    def generar(self, ctx: Contexto) -> Resultado:
        self.contextos.append(ctx)
        if ctx.tarea.id in self.falla_en:
            raise RuntimeError("fallo provocado")
        return super().generar(ctx)

    def ids(self) -> list[str]:
        return [c.tarea.id for c in self.contextos]
