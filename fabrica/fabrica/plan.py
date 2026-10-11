"""Convierte el diseño en tareas con dependencias, en un orden en el que se pueden hacer."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from .diseno import Diseno


@dataclass(frozen=True)
class Tarea:
    id: str
    tipo: str
    titulo: str
    proveedor: str
    requiere_aprobacion: bool
    deps: tuple[str, ...] = ()
    datos: dict = field(default_factory=dict, compare=False)

    @property
    def nombre(self) -> str:
        return self.id.rsplit("/", 1)[-1]

    @property
    def huella(self) -> str:
        """Cambia cuando cambia lo que se pide, para rehacer solo lo afectado."""
        base = json.dumps(
            {"tipo": self.tipo, "proveedor": self.proveedor, "deps": self.deps, "datos": self.datos},
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


def planificar(d: Diseno) -> list[Tarea]:
    """Devuelve las tareas en orden: cada una aparece después de las que necesita."""
    tareas: list[Tarea] = []

    def nueva(id_: str, tipo: str, titulo: str, deps: tuple[str, ...] = (), **datos: object) -> str:
        tareas.append(
            Tarea(
                id=id_,
                tipo=tipo,
                titulo=titulo,
                proveedor=d.proveedores[tipo],
                requiere_aprobacion=tipo in d.aprobar,
                deps=deps,
                datos=datos,
            )
        )
        return id_

    for p in d.personajes:
        concepto = nueva(
            f"{p.id}/concepto", "concepto", f"Arte conceptual de {p.nombre}",
            personaje=p.nombre, descripcion=p.descripcion, estilo=d.estilo,
        )
        modelo = nueva(
            f"{p.id}/modelo3d", "modelo3d", f"Modelo 3D de {p.nombre}", (concepto,),
            personaje=p.nombre, descripcion=p.descripcion,
        )
        # Los campos opcionales solo entran en los datos si se usan, para no cambiar la huella
        # (y rehacer) las tareas de proyectos que no los tienen.
        con_altura = {"altura": p.altura} if p.altura is not None else {}
        limpio = nueva(
            f"{p.id}/limpieza", "limpieza", f"Limpieza del modelo de {p.nombre}", (modelo,),
            personaje=p.nombre, **con_altura,
        )
        rig = nueva(f"{p.id}/rig", "rig", f"Esqueleto de {p.nombre}", (limpio,), personaje=p.nombre, **con_altura)
        acciones = dict(p.acciones)
        for animacion in p.animaciones:
            con_accion = {"accion": acciones[animacion]} if animacion in acciones else {}
            nueva(
                f"{p.id}/animacion/{animacion}", "animacion", f"Animación «{animacion}» de {p.nombre}", (rig,),
                personaje=p.nombre, animacion=animacion, **con_accion,
            )
        for frase, texto in p.frases:
            nueva(
                f"{p.id}/voz/{frase}", "voz", f"Voz «{frase}» de {p.nombre}",
                personaje=p.nombre, texto=texto, voz=p.voz, voz_id=p.voz_id,
            )

    for s in d.sonidos:
        datos_sonido: dict = {"descripcion": s.descripcion, "duracion": s.duracion}
        if s.bucle:
            datos_sonido["bucle"] = True  # solo si está, para no cambiar la huella de los demás
        nueva(f"sonido/{s.id}", "sonido", f"Efecto de sonido «{s.id}»", **datos_sonido)
    for m in d.musica:
        nueva(
            f"musica/{m.id}", "musica", f"Música «{m.id}»",
            descripcion=m.descripcion, duracion=m.duracion, instrumental=m.instrumental,
        )
    return tareas
