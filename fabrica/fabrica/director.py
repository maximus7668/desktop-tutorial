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
from .agentes import Agente, Contexto, Resultado, Revision, Revisor, Veredicto
from .diseno import REVISABLES, Diseno, ErrorDiseno, cargar
from .plan import Tarea, planificar
from .registro import APROBADO, ERROR, ESPERANDO, PENDIENTE, RECHAZADO, SIN_AGENTE, Entrada, Registro


CARPETA_MONTAJE = "recursos_fabrica"
MARCA_MONTAJE = ".fabrica"
REVISOR = "claude"


class ErrorOrden(ValueError):
    """Orden que no se puede cumplir: un id que no existe, aprobar algo que no espera aprobación..."""


@dataclass
class Montaje:
    destino: Path
    copiados: list[str] = field(default_factory=list)
    omitidos: list[str] = field(default_factory=list)  # aprobados, pero hechos por el agente simulado


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
        if self._fabricas is not None:
            nombres = set(self.diseno.proveedores.values()) | set(self.diseno.ajustes)
            if self.diseno.revisar:
                nombres.add(REVISOR)
            for nombre in sorted(nombres):
                self._agente(nombre)  # si un ajuste está mal, el error sale ya, no a mitad del trabajo

    # --- consultas -------------------------------------------------------------------------

    def entrada(self, id_: str) -> Entrada:
        return self.registro.entradas[id_]

    def carpeta_de(self, tarea: Tarea) -> Path:
        return self.carpeta / "recursos" / Path(*tarea.id.split("/"))

    def deps_sin_aprobar(self, tarea: Tarea) -> list[str]:
        return [d for d in tarea.deps if self.entrada(d).estado != APROBADO]

    # --- trabajo ---------------------------------------------------------------------------

    def ejecutar(
        self,
        maximo: int | None = None,
        al_terminar: Callable[[Tarea, Entrada], None] | None = None,
        al_revisar: Callable[[Tarea, Veredicto, int, int], None] | None = None,
    ) -> Informe:
        """Genera, en orden, todo lo que tenga sus dependencias aprobadas.

        Lo de los tipos de [fabrica] revisar pasa antes por el revisor: si ve fallos, se rehace con
        su corrección. al_revisar recibe cada veredicto: tarea, veredicto, número de la vez que se
        rehace por él (0 si no se rehace) y máximo de veces.
        """
        informe = Informe()
        for tarea in self.tareas:
            e = self.entrada(tarea.id)
            if not self._puede_intentarse(e) or self.deps_sin_aprobar(tarea):
                continue
            agente = self._agente(tarea.proveedor)
            revisor = self._revisor() if tarea.tipo in self.diseno.revisar else None
            motivo = agente.disponible() or (revisor.disponible() if revisor else None)
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
            self._producir(tarea, e, agente, revisor, al_revisar)
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
        e.rechazos += 1
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

    def montar(self, juego: Path, incluir_simulados: bool = False) -> Montaje:
        """Copia lo aprobado al proyecto de Godot, en recursos_fabrica/, con el índice que lee el juego.

        La carpeta es de la fábrica: se rehace entera cada vez. Lo hecho por el agente simulado no
        se copia salvo que se pida, porque el cuerpo provisional del juego se ve mejor que el relleno.
        """
        juego = Path(juego)
        if not (juego / "project.godot").is_file():
            raise ErrorOrden(f"{juego} no es un proyecto de Godot: no tiene project.godot.")
        destino = juego / CARPETA_MONTAJE
        if destino.exists() and not (destino / MARCA_MONTAJE).exists():
            raise ErrorOrden(
                f"{destino} ya existe y no lo creó la fábrica; no lo toco. Muévelo o bórralo a mano."
            )
        temporal = juego / f".{CARPETA_MONTAJE}.tmp"
        shutil.rmtree(temporal, ignore_errors=True)
        temporal.mkdir()
        (temporal / MARCA_MONTAJE).write_text(
            "Carpeta generada por «python -m fabrica montar». Se rehace entera cada vez: no edites aquí.\n",
            encoding="utf-8",
        )
        montaje = Montaje(destino=destino)

        def copiar(id_: str) -> list[str]:
            e = self.entrada(id_)
            if e.estado != APROBADO:
                return []
            if e.agente == "simulado" and not incluir_simulados:
                montaje.omitidos.append(id_)
                return []
            rutas = []
            for relativa in e.archivos:
                dentro = Path(relativa).relative_to("recursos")
                final = temporal / dentro
                final.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(self.carpeta / relativa, final)
                rutas.append(f"res://{CARPETA_MONTAJE}/{dentro.as_posix()}")
            montaje.copiados.append(id_)
            return rutas

        personajes: dict[str, dict] = {}
        for p in self.diseno.personajes:
            datos: dict = {"nombre": p.nombre}
            for clave, id_ in (("concepto", f"{p.id}/concepto"), ("modelo", f"{p.id}/rig")):
                rutas = copiar(id_)
                if rutas:
                    datos[clave] = rutas
            animaciones = {a: r for a in p.animaciones if (r := copiar(f"{p.id}/animacion/{a}"))}
            voces = {f: r for f, _ in p.frases if (r := copiar(f"{p.id}/voz/{f}"))}
            if animaciones:
                datos["animaciones"] = animaciones
            if voces:
                datos["voces"] = voces
            personajes[p.id] = datos
        indice = {
            "juego": self.diseno.nombre,
            "montado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "personajes": personajes,
            "sonidos": {s.id: r for s in self.diseno.sonidos if (r := copiar(f"sonido/{s.id}"))},
            "musica": {m.id: r for m in self.diseno.musica if (r := copiar(f"musica/{m.id}"))},
        }
        (temporal / "indice.json").write_text(json.dumps(indice, ensure_ascii=False, indent=2), encoding="utf-8")
        shutil.rmtree(destino, ignore_errors=True)
        temporal.rename(destino)
        return montaje

    # --- interno ---------------------------------------------------------------------------

    def _producir(
        self,
        tarea: Tarea,
        e: Entrada,
        agente: Agente,
        revisor: Revisor | None,
        al_revisar: Callable[[Tarea, Veredicto, int, int], None] | None,
    ) -> None:
        """Genera y, si toca, pasa por el revisor; lo que no aprueba se rehace con su corrección."""
        pedido = e.motivo_rechazo  # lo que pediste tú se mantiene aunque el revisor pida más
        rehechas = 0
        while True:
            motivo = e.motivo_rechazo
            self._generar(tarea, e, agente)
            if e.estado == ERROR or revisor is None:
                return
            try:
                veredicto = revisor.revisar(self._revision(tarea, e, motivo))
            except Exception as exc:  # sin revisión no se da nada por bueno: lo decides tú
                self._a_tus_manos(e, f"{e.nota} Claude no pudo revisarlo ({exc}); míralo tú.")
                return
            if veredicto is None:
                e.nota = f"{e.nota} (Claude no lo revisó: no hay imagen PNG, JPG o WEBP.)".strip()
                return
            rehace = not veredicto.aprobado and rehechas < revisor.rehacer
            if al_revisar:
                al_revisar(tarea, veredicto, rehechas + 1 if rehace else 0, revisor.rehacer)
            if veredicto.aprobado:
                e.nota = f"{e.nota} Claude: {veredicto.comentario or 'bien'}".strip()
                return
            problemas = "; ".join(veredicto.problemas)
            if not rehace:
                self._a_tus_manos(
                    e, f"Claude sigue viendo fallos: {problemas}. Decide tú: apruébalo o recházalo con tu motivo."
                )
                return
            rehechas += 1
            e.estado = RECHAZADO
            e.motivo_rechazo = "; ".join(m for m in (pedido, veredicto.correccion or problemas) if m)
            e.nota = f"Claude lo rechazó: {problemas}"
            e.rechazos += 1
            e.tocar()
            self.registro.guardar()

    @staticmethod
    def _a_tus_manos(e: Entrada, nota: str) -> None:
        e.estado, e.nota = ESPERANDO, nota
        e.tocar()

    def _revision(self, tarea: Tarea, e: Entrada, motivo: str) -> Revision:
        personaje = next((p for p in self.diseno.personajes if p.id == tarea.id.split("/", 1)[0]), None)
        ficha: dict = {}
        if personaje:
            ficha = {"nombre": personaje.nombre, "descripcion": personaje.descripcion}
            if personaje.altura:
                ficha["altura"] = personaje.altura
        return Revision(
            tarea=tarea,
            juego=self.diseno.nombre,
            estilo=self.diseno.estilo,
            archivos=[self.carpeta / a for a in e.archivos],
            referencias=self._referencias(tarea),
            ficha=ficha,
            nota=e.nota,
            motivo_rechazo=motivo,
        )

    def _referencias(self, tarea: Tarea) -> list[Path]:
        """El arte conceptual aprobado del que sale este recurso, para comparar."""
        referencias: list[Path] = []
        pila, vistas = list(tarea.deps), set()
        while pila:
            id_ = pila.pop()
            if id_ in vistas:
                continue
            vistas.add(id_)
            dep = self.por_id[id_]
            if dep.tipo == "concepto" and self.entrada(id_).estado == APROBADO:
                referencias += [self.carpeta / a for a in self.entrada(id_).archivos]
            pila.extend(dep.deps)
        return referencias

    def _revisor(self) -> Revisor:
        return self._agente(REVISOR)  # type: ignore[return-value]

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
            memoria=e.memoria,
            memorias={d: dict(self.entrada(d).memoria) for d in tarea.deps},
            proyecto=self.carpeta,
            rechazos=e.rechazos,
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
        e.memoria = {}
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
        if self.diseno.revisar and self._tipos_de(REVISOR) is None:
            raise ErrorDiseno(f"[fabrica] revisar: falta el revisor '{REVISOR}'.")
        for nombre, ajustes in self.diseno.ajustes.items():
            if self._tipos_de(nombre) is None:
                raise ErrorDiseno(f"[fabrica.{nombre}]: no existe ese proveedor. Hay: {', '.join(conocidos)}")
            if self._fabricas is not None:
                admitidos = getattr(self._fabricas[nombre], "AJUSTES", ())
                for clave in ajustes:
                    if clave not in admitidos:
                        lista = ", ".join(admitidos) if admitidos else "ninguno"
                        raise ErrorDiseno(f"[fabrica.{nombre}]: no conozco el ajuste '{clave}'. Admite: {lista}")
        for tipo, nombre in self.diseno.proveedores.items():
            tipos = self._tipos_de(nombre)
            if tipos is None:
                raise ErrorDiseno(
                    f"[fabrica.proveedores] {tipo} = '{nombre}': no existe ese proveedor. Hay: {', '.join(conocidos)}"
                )
            if not tipos:
                raise ErrorDiseno(
                    f"[fabrica.proveedores] {tipo} = '{nombre}': {nombre} no hace recursos, revisa los de los"
                    f" demás. Para eso: [fabrica] revisar = [{', '.join(repr(t) for t in REVISABLES)}]"
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
            try:
                self._agentes[nombre] = self._fabricas[nombre](**self.diseno.ajustes.get(nombre, {}))
            except (TypeError, ValueError) as e:
                raise ErrorDiseno(f"[fabrica.{nombre}]: {e}") from None
        return self._agentes[nombre]
