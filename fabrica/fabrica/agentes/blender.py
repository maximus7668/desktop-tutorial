"""Limpieza del modelo con Blender (gratis, en tu PC): escala, origen en los pies, menos polígonos
si hace falta, normales coherentes y una vista previa para revisarlo."""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import Contexto, ErrorAgente, Resultado
from .remoto import primer_archivo

SCRIPT = Path(__file__).with_name("blender_limpiar.py")
VARIABLE = "BLENDER"


def buscar_blender() -> str | None:
    """La variable BLENDER manda; si no, el PATH y las rutas de instalación habituales."""
    if os.environ.get(VARIABLE):
        return os.environ[VARIABLE]
    en_path = shutil.which("blender")
    if en_path:
        return en_path
    candidatos: list[str] = []
    if sys.platform.startswith("win"):
        for raiz in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("LOCALAPPDATA", "")):
            if raiz:
                candidatos += glob.glob(os.path.join(raiz, "Blender Foundation", "Blender*", "blender.exe"))
    elif sys.platform == "darwin":
        candidatos.append("/Applications/Blender.app/Contents/MacOS/Blender")
    existentes = sorted((c for c in candidatos if os.path.isfile(c)), reverse=True)
    return existentes[0] if existentes else None


class AgenteBlender:
    nombre = "blender"
    tipos = frozenset({"limpieza"})

    def __init__(self, ejecutable: str | None = None, ejecutar=subprocess.run, max_caras: int = 60000, limite: float = 900.0):
        self._ejecutable = ejecutable if ejecutable is not None else buscar_blender()
        self._ejecutar = ejecutar
        self.max_caras = max_caras
        self.limite = limite

    def disponible(self) -> str | None:
        if not self._ejecutable:
            return (
                "No encuentro Blender: instálalo desde blender.org o define la variable"
                f" {VARIABLE} con la ruta a blender (blender.exe en Windows)."
            )
        return None

    def generar(self, ctx: Contexto) -> Resultado:
        modelo = primer_archivo(ctx, (".glb", ".gltf"))
        if modelo is None:
            raise ErrorAgente("No hay modelo que limpiar: el paso anterior no entregó un .glb ni un .gltf.")
        salida = ctx.archivo("modelo_limpio.glb")
        vista = ctx.archivo("vista.png")
        altura = float(ctx.tarea.datos.get("altura") or 1.75)
        opciones = {
            "entrada": str(modelo),
            "salida": str(salida),
            "vista": str(vista),
            "altura": altura,
            "max_caras": self.max_caras,
        }
        orden = [self._ejecutable, "--background", "--factory-startup", "--python", str(SCRIPT), "--", json.dumps(opciones)]
        try:
            proceso = self._ejecutar(orden, capture_output=True, text=True, timeout=self.limite)
        except subprocess.TimeoutExpired:
            raise ErrorAgente(f"Blender tardó más de {int(self.limite)} s y se ha cortado.") from None
        except OSError as e:
            raise ErrorAgente(f"No se pudo arrancar Blender ({self._ejecutable}): {e}") from None
        salida_texto = (proceso.stdout or "") + "\n" + (proceso.stderr or "")
        if proceso.returncode != 0 or not salida.exists():
            ultimas = " | ".join(l for l in salida_texto.strip().splitlines()[-4:] if l.strip())
            raise ErrorAgente(f"Blender no pudo limpiar el modelo: {ultimas[:400]}")
        informe = _informe(salida_texto)
        archivos = [salida] + ([vista] if vista.exists() else [])
        return Resultado(archivos, _nota(informe, altura))


def _informe(texto: str) -> dict:
    for linea in reversed(texto.splitlines()):
        if linea.startswith("INFORME: "):
            try:
                return json.loads(linea[len("INFORME: "):])
            except json.JSONDecodeError:
                return {}
    return {}


def _nota(informe: dict, altura: float) -> str:
    if informe.get("aviso"):
        return informe["aviso"]
    partes = [f"Altura {informe.get('altura_final', altura):g} m con el origen en los pies"]
    antes, despues = informe.get("caras_antes"), informe.get("caras_despues")
    if antes and despues:
        partes.append(f"{antes} → {despues} caras" if antes != despues else f"{despues} caras")
    return ", ".join(partes) + "."
