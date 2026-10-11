"""El director: decide qué se puede hacer ya, se lo pide al agente que toca y lleva la cuenta."""

from __future__ import annotations

import difflib
import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn

from . import agentes as _agentes
from .agentes import Agente, Contexto, Resultado
from .diseno import Diseno, ErrorDiseno, cargar
from .plan import Tarea, planificar
from .registro import APROBADO, ERROR, ESPERANDO, PENDIENTE, RECHAZADO, SIN_AGENTE, Entrada, Registro


class ErrorOrden(ValueError):
    """Orden que no se puede cumplir: un id que no existe, aprobar algo que no espera aprobación..."""


@dataclass
class Informe:
    hechas: list[str] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)
    sin_agente: list[str] = field(default_factory=list)
    limite_alcanzado: bool = False


class Director:
    def __init__(self, carpeta: Path, agentes: dict[str, Agente] | None = None):
        """`agentes` sustituye a los proveedores reales (lo usan las pruebas)."""
        self.carpeta = Path(carpeta)
        self.diseno: Diseno = cargar(self.carpeta / "juego.toml")
        self._agentes: dict[str, Agente] = dict(agentes or {})
        self._fabricas = None if agentes is not None else _agentes.proveedores()
        self._validar_proveedores()

        self.tareas: list[Tarea] = planificar(self.diseno)
        self.por_id = {t.id: t for t in self.tareas}
        self.dependientes: dict[str, list[str]] = {t.id: [] for t in self.tareas}
        for t in self.tareas:
            for dep in t.deps:
                self.dependientes[dep].append(t.id)

        self.registro = Registro(self.carpeta / "registro.json")
        self._reconciliar()

    # --- consultas -------------------------------------------------------------------------

    def entrada(self, id_: str) -> Entrada:
        return self.registro.entradas[id_]

    def carpeta_de(self, tarea: Tarea) -> Path:
        return self.carpeta / "recursos" / Path(*tarea.id.split("/"))

    def deps_sin_aprobar(self, tarea: Tarea) -> list[str]:
        return [d for d in tarea.deps if self.entrada(d).estado != APROBADO]

    # --- trabajo ---------------------------------------------------------------------------

    def ejecutar(
        self, maximo: int | None = None, al_terminar: Callable[[Tarea, Entrada], None] | None = None
    ) -> Informe:
        """Genera, en orden, todo lo que tenga sus dependencias aprobadas."""
        informe = Informe()
        for tarea in self.tareas:
            e = self.entrada(tarea.id)
            if not self._puede_intentarse(e) or self.deps_sin_aprobar(tarea):
                continue
            agente = self._agente(tarea.proveedor)
            motivo = agente.disponible()
            if motivo:
                if (e.estado, e.nota) != (SIN_AGENTE, motivo):
                    e.estado, e.nota = SIN_AGENTE, motivo
                    e.tocar()
                    self.registro.guardar()
                informe.sin_agente.append(tarea.id)
                continue
            if maximo is not None and len(informe.hechas) + len(informe.errores) >= maximo:
                informe.limite_alcanzado = True
                break
            self._generar(tarea, e, agente)
            (informe.errores if e.estado == ERROR else informe.hechas).append(tarea.id)
            self.registro.guardar()
            if al_terminar:
                al_terminar(tarea, e)
        return informe

    def aprobar(self, ids: list[str]) -> list[str]:
        """Acepta ids exactos o grupos ("ren", "ren/voz") con lo que espera tu visto bueno dentro."""
        elegidas = self._expandir(ids)
        for id_ in elegidas:
            e = self.entrada(id_)
            if e.estado != ESPERANDO:
                raise ErrorOrden(f"{id_} no espera tu visto bueno (está {e.estado}).")
        for id_ in elegidas:
            e = self.entrada(id_)
            e.estado, e.motivo_rechazo = APROBADO, ""
            e.tocar()
        self.registro.guardar()
        return elegidas

    def aprobar_todo(self) -> list[str]:
        esperando = [t.id for t in self.tareas if self.entrada(t.id).estado == ESPERANDO]
        return self.aprobar(esperando) if esperando else []

    def rechazar(self, id_: str, motivo: str) -> list[str]:
        """Marca un recurso para rehacerlo. Devuelve las tareas que dependían de él y se rehacen."""
        motivo = " ".join(motivo.split())
        if not motivo:
            raise ErrorOrden("Escribe en --motivo qué hay que cambiar; el agente lo recibe.")
        id_ = id_.strip().strip("/")
        if id_ not in self.por_id:
            self._no_existe(id_)
        e = self.entrada(id_)
        if e.estado not in (ESPERANDO, APROBADO):
            raise ErrorOrden(f"Solo se puede rechazar algo ya generado; {id_} está {e.estado}.")
        e.estado, e.motivo_rechazo, e.nota = RECHAZADO, motivo, f"Rechazado: {motivo}"
        e.tocar()
        afectadas = self._invalidar_dependientes(id_)
        self.registro.guardar()
        return afectadas

    def exportar(self) -> Path:
        """Escribe indice_recursos.json: lo aprobado, organizado para importarlo en el motor."""

        def aprobados(id_: str) -> list[str]:
            e = self.entrada(id_)
            return list(e.archivos) if e.estado == APROBADO else []

        pendientes = [t.id for t in self.tareas if self.entrada(t.id).estado != APROBADO]
        indice = {
            "juego": self.diseno.nombre,
            "exportado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "completo": not pendientes,
            "pendientes": pendientes,
            "personajes": {
                p.id: {
                    "nombre": p.nombre,
                    "concepto": aprobados(f"{p.id}/concepto"),
                    # El modelo que usa el motor es el que ya tiene esqueleto.
                    "modelo": aprobados(f"{p.id}/rig"),
                    "animaciones": {a: aprobados(f"{p.id}/animacion/{a}") for a in p.animaciones},
                    "voces": {f: aprobados(f"{p.id}/voz/{f}") for f, _ in p.frases},
                }
                for p in self.diseno.personajes
            },
            "sonidos": {s.id: aprobados(f"sonido/{s.id}") for s in self.diseno.sonidos},
            "musica": {m.id: aprobados(f"musica/{m.id}") for m in self.diseno.musica},
        }
        ruta = self.carpeta / "indice_recursos.json"
        ruta.write_text(json.dumps(indice, ensure_ascii=False, indent=2), encoding="utf-8")
        return ruta

    # --- interno ---------------------------------------------------------------------------

    def _generar(self, tarea: Tarea, e: Entrada, agente: Agente) -> None:
        destino = self.carpeta_de(tarea)
        # El agente trabaja en una carpeta aparte: si falla, lo anterior sigue intacto.
        temporal = destino.with_name(destino.name + ".tmp")
        shutil.rmtree(temporal, ignore_errors=True)
        temporal.mkdir(parents=True)
        ctx = Contexto(
            tarea=tarea,
            juego=self.diseno.nombre,
            estilo=self.diseno.estilo,
            carpeta=temporal,
            entradas={d: [self.carpeta / a for a in self.entrada(d).archivos] for d in tarea.deps},
            motivo_rechazo=e.motivo_rechazo,
            intento=e.intentos + 1,
        )
        e.intentos += 1
        e.agente = agente.nombre
        try:
            resultado = agente.generar(ctx)
            archivos = self._comprobar(resultado, temporal)
        except Exception as exc:  # un agente que falla no puede parar al resto de la fábrica
            shutil.rmtree(temporal, ignore_errors=True)
            e.estado = ERROR
            e.errores_seguidos += 1
            e.nota = str(exc) or type(exc).__name__
            e.tocar()
            return

        shutil.rmtree(destino, ignore_errors=True)
        temporal.rename(destino)
        e.archivos = [(destino / a).relative_to(self.carpeta).as_posix() for a in archivos]
        e.errores_seguidos = 0
        e.nota = resultado.nota
        e.estado = ESPERANDO if tarea.requiere_aprobacion else APROBADO
        if e.estado == APROBADO:
            e.motivo_rechazo = ""
        e.tocar()
        self._invalidar_dependientes(tarea.id)

    @staticmethod
    def _comprobar(resultado: Resultado, carpeta: Path) -> list[Path]:
        if not resultado.archivos:
            raise RuntimeError("El agente terminó sin devolver ningún archivo.")
        relativos = []
        base = carpeta.resolve()
        for archivo in resultado.archivos:
            ruta = Path(archivo).resolve()
            if not ruta.is_file():
                raise RuntimeError(f"El agente dijo que creó {archivo}, pero no existe.")
            if not ruta.is_relative_to(base):
                raise RuntimeError(f"El agente dejó {archivo} fuera de su carpeta.")
            relativos.append(ruta.relative_to(base))
        return relativos

    def _puede_intentarse(self, e: Entrada) -> bool:
        if e.estado in (PENDIENTE, RECHAZADO, SIN_AGENTE):
            return True
        return e.estado == ERROR and e.errores_seguidos < self.diseno.intentos_max

    def _reconciliar(self) -> None:
        """Ajusta el registro al juego.toml actual: tareas nuevas, borradas o cambiadas."""
        cambiado = False
        for id_ in [i for i in self.registro.entradas if i not in self.por_id]:
            del self.registro.entradas[id_]
            cambiado = True
        # Primero las nuevas, para que existan si una tarea cambiada las invalida.
        for tarea in self.tareas:
            if tarea.id not in self.registro.entradas:
                self.registro.entradas[tarea.id] = Entrada(huella=tarea.huella)
                cambiado = True
        for tarea in self.tareas:
            e = self.entrada(tarea.id)
            if e.huella != tarea.huella:
                self._reiniciar(e, "Cambió su definición en juego.toml.")
                e.huella = tarea.huella
                self._invalidar_dependientes(tarea.id)
                cambiado = True
        if cambiado:
            self.registro.guardar()

    def _invalidar_dependientes(self, id_: str) -> list[str]:
        """Lo que se hizo a partir de una versión anterior hay que volver a hacerlo."""
        afectadas: list[str] = []
        pila = list(self.dependientes[id_])
        vistas: set[str] = set()
        while pila:
            dep = pila.pop()
            if dep in vistas:
                continue
            vistas.add(dep)
            e = self.entrada(dep)
            if e.estado != PENDIENTE or e.archivos:
                self._reiniciar(e, f"Se rehace porque cambió {id_}.")
                afectadas.append(dep)
            pila.extend(self.dependientes[dep])
        return sorted(afectadas)

    @staticmethod
    def _reiniciar(e: Entrada, nota: str) -> None:
        # motivo_rechazo se conserva: lo que pediste cambiar sigue valiendo para la próxima versión.
        e.estado = PENDIENTE
        e.archivos = []
        e.intentos = 0
        e.errores_seguidos = 0
        e.nota = nota
        e.tocar()

    def _expandir(self, ids: list[str]) -> list[str]:
        elegidas: list[str] = []
        for id_ in ids:
            id_ = id_.strip().strip("/")
            if id_ in self.por_id:
                grupo = [id_]
            else:
                grupo = [
                    t.id
                    for t in self.tareas
                    if t.id.startswith(id_ + "/") and self.entrada(t.id).estado == ESPERANDO
                ]
                if not grupo:
                    if any(t.id.startswith(id_ + "/") for t in self.tareas):
                        raise ErrorOrden(f"Nada dentro de {id_} espera tu visto bueno.")
                    self._no_existe(id_)
            elegidas.extend(g for g in grupo if g not in elegidas)
        return elegidas

    def _no_existe(self, id_: str) -> NoReturn:
        parecidas = difflib.get_close_matches(id_, list(self.por_id), n=1)
        pista = f" ¿Querías decir '{parecidas[0]}'?" if parecidas else ""
        raise ErrorOrden(f"No existe la tarea '{id_}'.{pista} Las tienes todas en: python -m fabrica plan")

    def _validar_proveedores(self) -> None:
        conocidos = sorted(self._fabricas if self._fabricas is not None else self._agentes)
        for tipo, nombre in self.diseno.proveedores.items():
            tipos = self._tipos_de(nombre)
            if tipos is None:
                raise ErrorDiseno(
                    f"[fabrica.proveedores] {tipo} = '{nombre}': no existe ese proveedor. Hay: {', '.join(conocidos)}"
                )
            if tipo not in tipos:
                raise ErrorDiseno(
                    f"[fabrica.proveedores] {tipo} = '{nombre}': ese proveedor no hace '{tipo}',"
                    f" solo {', '.join(sorted(tipos))}"
                )

    def _tipos_de(self, nombre: str) -> frozenset[str] | None:
        if self._fabricas is not None:
            fabrica = self._fabricas.get(nombre)
            return fabrica.tipos if fabrica else None
        agente = self._agentes.get(nombre)
        return agente.tipos if agente else None

    def _agente(self, nombre: str) -> Agente:
        if nombre not in self._agentes:
            self._agentes[nombre] = self._fabricas[nombre]()
        return self._agentes[nombre]
