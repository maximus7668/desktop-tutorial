"""Agente de relleno: crea archivos válidos pero falsos para probar todo el flujo gratis."""

from __future__ import annotations

import base64
import json
import math
import shutil
import struct
import wave
from pathlib import Path
from xml.sax.saxutils import escape

from . import Contexto, Resultado

_FRECUENCIA = 22050
_TONOS = {"voz": 330.0, "sonido": 660.0, "musica": 220.0}
_SEGUNDOS = {"voz": 1.2, "sonido": 0.6, "musica": 4.0}
_MAX_SEGUNDOS = 8.0  # el relleno de una canción de 3 minutos no necesita durar 3 minutos


class AgenteSimulado:
    nombre = "simulado"
    tipos = frozenset({"concepto", "modelo3d", "limpieza", "rig", "animacion", "voz", "sonido", "musica"})

    def disponible(self) -> str | None:
        return None

    def generar(self, ctx: Contexto) -> Resultado:
        tarea = ctx.tarea
        personaje = tarea.datos.get("personaje", "")

        if tarea.tipo == "concepto":
            ruta = ctx.archivo("concepto.svg")
            ruta.write_text(hoja_concepto(personaje, ctx.intento, ctx.motivo_rechazo), encoding="utf-8")
            return Resultado([ruta], _nota("Hoja de personaje de relleno.", ctx))

        if tarea.tipo == "modelo3d":
            ruta = ctx.archivo("modelo.gltf")
            ruta.write_text(json.dumps(caja_gltf(personaje)), encoding="utf-8")
            return Resultado([ruta], _nota("Caja del tamaño de un personaje en lugar del modelo.", ctx))

        if tarea.tipo in ("limpieza", "rig"):
            origen = next((a for archivos in ctx.entradas.values() for a in archivos if a.suffix in (".gltf", ".glb")), None)
            extension = origen.suffix if origen is not None else ".gltf"
            ruta = ctx.archivo(("modelo_limpio" if tarea.tipo == "limpieza" else "modelo_rig") + extension)
            if origen is not None:
                shutil.copyfile(origen, ruta)
            else:
                ruta.write_text(json.dumps(caja_gltf(personaje)), encoding="utf-8")
            texto = "Copia del modelo anterior sin limpiar." if tarea.tipo == "limpieza" else "Copia del modelo sin esqueleto."
            return Resultado([ruta], _nota(texto, ctx))

        if tarea.tipo == "animacion":
            nombre = tarea.datos["animacion"]
            ruta = ctx.archivo(f"{nombre}.json")
            ruta.write_text(json.dumps(animacion_vacia(nombre), ensure_ascii=False, indent=2), encoding="utf-8")
            return Resultado([ruta], _nota("Poses clave vacías, a saltos de 2 fotogramas.", ctx))

        segundos = tarea.datos.get("duracion") or _SEGUNDOS[tarea.tipo]
        ruta = ctx.archivo(f"{tarea.nombre}.wav")
        escribir_tono(ruta, _TONOS[tarea.tipo], min(segundos, _MAX_SEGUNDOS))
        return Resultado([ruta], _nota("Pitido de relleno.", ctx))


def _nota(texto: str, ctx: Contexto) -> str:
    if ctx.motivo_rechazo:
        return f"{texto} Recibido el motivo del rechazo: «{ctx.motivo_rechazo}»."
    return texto


def hoja_concepto(personaje: str, intento: int, motivo: str) -> str:
    """Tres siluetas (frente, lado, espalda), como las hojas que se pasan al generador 3D."""
    vistas = []
    for i, vista in enumerate(("FRENTE", "LADO", "ESPALDA")):
        cuerpo = 70 if vista == "LADO" else 110
        piernas = (
            '<rect x="-14" y="250" width="28" height="150" rx="10" fill="#6e60a8"/>'
            if vista == "LADO"
            else f'<rect x="{-cuerpo / 2 + 8}" y="250" width="{cuerpo / 2 - 14}" height="150" rx="10" fill="#6e60a8"/>'
            f'<rect x="6" y="250" width="{cuerpo / 2 - 14}" height="150" rx="10" fill="#6e60a8"/>'
        )
        vistas.append(
            f'<g transform="translate({190 + i * 322} 120)">'
            f'<circle cx="0" cy="40" r="34" fill="#c9bfe6"/>'
            f'<rect x="{-cuerpo / 2}" y="84" width="{cuerpo}" height="170" rx="18" fill="#9d8fd0"/>'
            f"{piernas}"
            f'<text x="0" y="440" text-anchor="middle" font-size="20" fill="#b6abcf">{vista}</text>'
            "</g>"
        )
    pie = f"Relleno del agente simulado · intento {intento}"
    if motivo:
        pie += f" · motivo: {motivo}"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="640" viewBox="0 0 1024 640">'
        '<rect width="1024" height="640" fill="#1b1534"/>'
        f'<text x="40" y="64" font-size="36" font-family="sans-serif" fill="#f7f0e6">{escape(personaje)}</text>'
        f'{"".join(vistas)}'
        f'<text x="40" y="610" font-size="16" font-family="sans-serif" fill="#ffcf3a">{escape(pie)}</text>'
        "</svg>"
    )


def caja_gltf(nombre: str, ancho: float = 0.5, alto: float = 1.8, fondo: float = 0.3) -> dict:
    """glTF 2.0 mínimo: una caja con la base en el suelo, del tamaño aproximado de un personaje."""
    w, d, h = _f32(ancho / 2), _f32(fondo / 2), _f32(alto)
    vertices = [(-w, 0, -d), (w, 0, -d), (w, h, -d), (-w, h, -d), (-w, 0, d), (w, 0, d), (w, h, d), (-w, h, d)]
    # Triángulos en sentido antihorario vistos desde fuera: delante, detrás, derecha, izquierda, arriba, abajo.
    indices = [4, 5, 6, 4, 6, 7, 1, 0, 3, 1, 3, 2, 5, 1, 2, 5, 2, 6, 0, 4, 7, 0, 7, 3, 3, 7, 6, 3, 6, 2, 0, 1, 5, 0, 5, 4]
    datos_i = struct.pack(f"<{len(indices)}H", *indices)  # 72 bytes: ya alineado a 4
    datos_v = struct.pack(f"<{len(vertices) * 3}f", *(c for v in vertices for c in v))
    buffer = datos_i + datos_v
    return {
        "asset": {"version": "2.0", "generator": "fabrica (agente simulado)"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": nombre}],
        "meshes": [{"name": nombre, "primitives": [{"attributes": {"POSITION": 1}, "indices": 0, "material": 0}]}],
        "materials": [
            {
                "name": "relleno",
                "pbrMetallicRoughness": {"baseColorFactor": [0.8, 0.45, 0.3, 1.0], "metallicFactor": 0.0, "roughnessFactor": 0.9},
            }
        ],
        "buffers": [
            {"byteLength": len(buffer), "uri": "data:application/octet-stream;base64," + base64.b64encode(buffer).decode("ascii")}
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(datos_i), "target": 34963},
            {"buffer": 0, "byteOffset": len(datos_i), "byteLength": len(datos_v), "target": 34962},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5123, "count": len(indices), "type": "SCALAR"},
            {"bufferView": 1, "componentType": 5126, "count": len(vertices), "type": "VEC3", "min": [-w, 0, -d], "max": [w, h, d]},
        ],
    }


def _f32(x: float) -> float:
    # min/max del glTF tienen que coincidir con los valores tal como quedan guardados en float32.
    return struct.unpack("<f", struct.pack("<f", x))[0]


def animacion_vacia(nombre: str) -> dict:
    return {
        "animacion": nombre,
        "fps": 24,
        "paso": 2,
        "poses": [
            {"fotograma": 0, "nombre": "anticipacion"},
            {"fotograma": 4, "nombre": "impacto"},
            {"fotograma": 10, "nombre": "recuperacion"},
        ],
        "simulado": True,
    }


def escribir_tono(ruta: Path, hz: float, segundos: float) -> None:
    n = max(1, int(_FRECUENCIA * segundos))
    rampa = max(1, int(_FRECUENCIA * 0.01))  # entrada y salida suaves para que no chasquee
    muestras = bytearray()
    for i in range(n):
        volumen = 0.25 * min(1.0, i / rampa, (n - 1 - i) / rampa)
        muestras += struct.pack("<h", int(32767 * volumen * math.sin(2 * math.pi * hz * i / _FRECUENCIA)))
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_FRECUENCIA)
        w.writeframes(bytes(muestras))
