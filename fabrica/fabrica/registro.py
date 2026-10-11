"""Estado de cada tarea, guardado en registro.json para seguir donde se quedó."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path

PENDIENTE = "pendiente"
ESPERANDO = "esperando_aprobacion"
APROBADO = "aprobado"
RECHAZADO = "rechazado"
ERROR = "error"
SIN_AGENTE = "sin_agente"
ESTADOS = (APROBADO, ESPERANDO, PENDIENTE, RECHAZADO, ERROR, SIN_AGENTE)


class ErrorRegistro(RuntimeError):
    """registro.json no se puede leer."""


@dataclass
class Entrada:
    estado: str = PENDIENTE
    huella: str = ""
    intentos: int = 0
    errores_seguidos: int = 0
    archivos: list[str] = field(default_factory=list)  # relativos a la carpeta del proyecto
    agente: str = ""
    nota: str = ""
    motivo_rechazo: str = ""
    actualizado: str = ""
    # Lo que el agente necesita recordar entre ejecuciones (por ejemplo, el id de una tarea
    # remota para retomarla en vez de pagarla otra vez). Se borra si la tarea se rehace.
    memoria: dict = field(default_factory=dict)

    def tocar(self) -> None:
        self.actualizado = datetime.now(timezone.utc).isoformat(timespec="seconds")


class Registro:
    VERSION = 1

    def __init__(self, ruta: Path):
        self.ruta = ruta
        self.entradas: dict[str, Entrada] = {}
        if not ruta.exists():
            return
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
            conocidas = {f.name for f in fields(Entrada)}
            for id_, valores in datos["tareas"].items():
                self.entradas[id_] = Entrada(**{k: v for k, v in valores.items() if k in conocidas})
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            raise ErrorRegistro(
                f"{ruta} está dañado ({e}). Si lo borras, la fábrica empieza de cero"
                " (los archivos de recursos/ no se pierden, pero se volverán a generar)."
            ) from None

    def guardar(self) -> None:
        datos = {
            "version": self.VERSION,
            "tareas": {id_: asdict(e) for id_, e in sorted(self.entradas.items())},
        }
        # Se escribe aparte y se sustituye de golpe para no dejar el archivo a medias.
        fd, temporal = tempfile.mkstemp(dir=self.ruta.parent, prefix=".registro-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(datos, f, ensure_ascii=False, indent=2)
            os.replace(temporal, self.ruta)
        except BaseException:
            Path(temporal).unlink(missing_ok=True)
            raise
