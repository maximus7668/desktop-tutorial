"""Pasa el modelo tal cual al paso siguiente. Para cuando todavía no hay herramienta de limpieza."""

from __future__ import annotations

import shutil

from . import Contexto, ErrorAgente, Resultado


class AgenteCopiar:
    nombre = "copiar"
    tipos = frozenset({"limpieza"})
    AJUSTES: tuple[str, ...] = ()

    def disponible(self) -> str | None:
        return None

    def generar(self, ctx: Contexto) -> Resultado:
        copiados = []
        for archivos in ctx.entradas.values():
            for archivo in archivos:
                destino = ctx.archivo(archivo.name)
                shutil.copyfile(archivo, destino)
                copiados.append(destino)
        if not copiados:
            raise ErrorAgente("No hay nada que copiar: el paso anterior no entregó archivos.")
        return Resultado(copiados, "Sin limpiar: copia tal cual del paso anterior.")
