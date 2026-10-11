"""Línea de comandos de la fábrica: python -m fabrica <orden>."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from importlib import resources
from pathlib import Path

from .agentes import ErrorAgente, Veredicto
from .agentes.claude import ESFUERZOS, MODELO, ClienteClaude
from .diseno import ErrorDiseno, cargar
from .director import Director, ErrorOrden
from .idear import idear
from .plan import Tarea
from .registro import (
    APROBADO,
    ERROR,
    ESPERANDO,
    ESTADOS,
    PENDIENTE,
    RECHAZADO,
    SIN_AGENTE,
    Entrada,
    ErrorRegistro,
)

ETIQUETAS = {
    APROBADO: "aprobado",
    ESPERANDO: "espera visto bueno",
    PENDIENTE: "pendiente",
    RECHAZADO: "rechazado",
    ERROR: "error",
    SIN_AGENTE: "sin agente",
}


RESUMEN = {
    APROBADO: "aprobadas",
    ESPERANDO: "esperan tu visto bueno",
    PENDIENTE: "pendientes",
    RECHAZADO: "rechazadas",
    ERROR: "con error",
    SIN_AGENTE: "sin agente",
}


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # consolas de Windows sin UTF-8

    comun = argparse.ArgumentParser(add_help=False)
    comun.add_argument(
        "-p", "--proyecto", default=".", type=Path,
        help="carpeta del proyecto, la que tiene juego.toml (por defecto, la actual)",
    )
    parser = argparse.ArgumentParser(
        prog="fabrica",
        description="Fábrica de recursos para tu juego: un director reparte el trabajo entre agentes de IA.",
    )
    ordenes = parser.add_subparsers(dest="orden", required=True, metavar="orden")
    nuevo = ordenes.add_parser("nuevo", help="crea un proyecto con un juego.toml de ejemplo")
    nuevo.add_argument("carpeta", type=Path)
    idear = ordenes.add_parser(
        "idear", help="Claude escribe el juego.toml a partir de tu idea (necesita ANTHROPIC_API_KEY)"
    )
    idear.add_argument("carpeta", type=Path, help="carpeta del proyecto nuevo")
    idear.add_argument("idea", nargs="*", help="tu idea, con tus palabras (las comillas son opcionales)")
    idear.add_argument("--archivo", type=Path, help="lee la idea de un archivo de texto")
    idear.add_argument("--modelo", default=MODELO, help=f"modelo de Claude (por defecto {MODELO})")
    idear.add_argument("--esfuerzo", default="high", choices=ESFUERZOS, help="cuánto piensa Claude (por defecto high)")
    ordenes.add_parser("plan", parents=[comun], help="muestra todas las tareas y de qué dependen")
    ejecutar = ordenes.add_parser("ejecutar", parents=[comun], help="genera todo lo que se pueda hacer ya")
    ejecutar.add_argument("--max", type=int, metavar="N", help="como mucho N tareas en esta vuelta")
    ordenes.add_parser("estado", parents=[comun], help="muestra cómo va cada tarea")
    aprobar = ordenes.add_parser(
        "aprobar", parents=[comun], help="das el visto bueno a recursos generados (ids o grupos como 'ren')"
    )
    aprobar.add_argument("ids", nargs="*")
    aprobar.add_argument("--todo", action="store_true", help="aprueba todo lo que espera tu visto bueno")
    rechazar = ordenes.add_parser("rechazar", parents=[comun], help="pides que se rehaga un recurso")
    rechazar.add_argument("id")
    rechazar.add_argument("--motivo", required=True, help="qué hay que cambiar; el agente lo recibe")
    ordenes.add_parser(
        "exportar", parents=[comun], help="escribe el índice de lo aprobado para importarlo en el motor"
    )
    montar = ordenes.add_parser(
        "montar", parents=[comun], help="copia lo aprobado al proyecto de Godot (recursos_fabrica/)"
    )
    montar.add_argument("--juego", required=True, type=Path, help="carpeta del proyecto de Godot (la que tiene project.godot)")
    montar.add_argument(
        "--incluir-simulados", action="store_true", help="copia también el relleno del agente simulado"
    )
    args = parser.parse_args(argv)

    try:
        if args.orden == "nuevo":
            return _nuevo(args.carpeta)
        if args.orden == "idear":
            return _idear(args.carpeta, " ".join(args.idea), args.archivo, args.modelo, args.esfuerzo)
        director = Director(args.proyecto)
        if args.orden == "plan":
            return _plan(director)
        if args.orden == "ejecutar":
            return _ejecutar(director, args.max)
        if args.orden == "estado":
            return _estado(director)
        if args.orden == "aprobar":
            return _aprobar(director, args.ids, args.todo)
        if args.orden == "rechazar":
            afectadas = director.rechazar(args.id, args.motivo)
            print(f"{args.id} se rehará en la próxima ejecución con tu motivo.")
            if afectadas:
                print(f"También se rehará lo que dependía de él: {', '.join(afectadas)}")
            return 0
        if args.orden == "exportar":
            ruta = director.exportar()
            pendientes = sum(director.entrada(t.id).estado != APROBADO for t in director.tareas)
            print(f"Índice escrito en {ruta}")
            if pendientes:
                print(f"Ojo: {pendientes} tareas aún no están aprobadas y no aparecen en el índice.")
            return 0
        if args.orden == "montar":
            montaje = director.montar(args.juego, args.incluir_simulados)
            print(f"Copiados {len(montaje.copiados)} recursos a {montaje.destino}")
            if montaje.omitidos:
                print(
                    f"Sin copiar {len(montaje.omitidos)} recursos de relleno del agente simulado"
                    " (el juego usa los suyos). Para copiarlos igualmente: --incluir-simulados"
                )
            print("Abre el proyecto en Godot para que importe los archivos nuevos.")
            return 0
    except (ErrorDiseno, ErrorRegistro, ErrorOrden, ErrorAgente) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 2


def _nuevo(carpeta: Path) -> int:
    destino = carpeta / "juego.toml"
    if destino.exists():
        raise ErrorOrden(f"{destino} ya existe; no lo sobrescribo.")
    carpeta.mkdir(parents=True, exist_ok=True)
    plantilla = resources.files("fabrica").joinpath("plantilla/juego.toml").read_text(encoding="utf-8")
    destino.write_text(plantilla, encoding="utf-8")
    print(f"Proyecto creado en {carpeta}")
    print("Siguientes pasos:")
    print(f"  1. Edita {destino} con tus personajes, sonidos y música.")
    print(f"  2. python -m fabrica plan -p {carpeta}")
    print(f"  3. python -m fabrica ejecutar -p {carpeta}")
    return 0


def _idear(carpeta: Path, idea: str, archivo: Path | None, modelo: str, esfuerzo: str) -> int:
    destino = carpeta / "juego.toml"
    if destino.exists():
        raise ErrorOrden(f"{destino} ya existe; no lo sobrescribo. Elige una carpeta nueva.")
    if archivo is not None:
        if idea:
            raise ErrorOrden("Da la idea escrita o con --archivo, pero no las dos cosas.")
        try:
            idea = archivo.read_text(encoding="utf-8")
        except OSError as e:
            raise ErrorOrden(f"No puedo leer {archivo}: {e.strerror or e}") from None
    if not idea.strip():
        raise ErrorOrden('Cuenta tu idea, por ejemplo: idear mi_juego "lucha de samuráis con poderes de rayo"')
    try:
        claude = ClienteClaude(modelo=modelo, esfuerzo=esfuerzo)
    except ValueError as e:
        raise ErrorOrden(str(e)) from None
    aviso = claude.disponible()
    if aviso:
        raise ErrorOrden(aviso)
    print(f"Claude ({modelo}) está escribiendo el diseño. Puede tardar unos minutos...")
    texto = idear(idea, claude)
    carpeta.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    diseno = cargar(destino)
    print(f"«{diseno.nombre}» escrito en {destino}")
    print(f"  Personajes: {', '.join(p.nombre for p in diseno.personajes)}")
    print(f"  {len(diseno.sonidos)} efectos de sonido y {len(diseno.musica)} pistas de música")
    print("Siguientes pasos:")
    print(f"  1. Léelo y cambia lo que quieras: {destino}")
    print(f"  2. python -m fabrica plan -p {carpeta}")
    print(f"  3. python -m fabrica ejecutar -p {carpeta}")
    return 0


def _plan(director: Director) -> int:
    print(f"Plan de «{director.diseno.nombre}»: {len(director.tareas)} tareas\n")
    for titulo, tareas in _grupos(director):
        print(titulo)
        for t in tareas:
            marcas = t.proveedor + (", con visto bueno" if t.requiere_aprobacion else "")
            despues = f"  después de {', '.join(t.deps)}" if t.deps else ""
            print(f"  {t.id:<34} {t.tipo:<10} {marcas:<28}{despues}".rstrip())
        print()
    return 0


def _ejecutar(director: Director, maximo: int | None) -> int:
    def al_terminar(t: Tarea, e: Entrada) -> None:
        if e.estado == ERROR:
            print(f"  error   {t.id}: {e.nota}")
        else:
            espera = " -> espera tu visto bueno" if e.estado == ESPERANDO else ""
            print(f"  hecho   {t.id} ({e.agente}){espera}")

    def al_revisar(t: Tarea, veredicto: Veredicto, vez: int, maximo_veces: int) -> None:
        if veredicto.aprobado:
            print(f"  Claude  {t.id}: {veredicto.comentario or 'bien'}")
        elif vez:
            print(f"  Claude  {t.id}: {'; '.join(veredicto.problemas)} -> se rehace ({vez}/{maximo_veces})")
        else:
            print(f"  Claude  {t.id}: {'; '.join(veredicto.problemas)} -> te lo paso a ti")

    print(f"Ejecutando «{director.diseno.nombre}»")
    informe = director.ejecutar(maximo, al_terminar, al_revisar)
    if not informe.hechas and not informe.errores and not informe.sin_agente:
        print("  No hay nada que se pueda hacer ahora mismo.")
    for motivo, n in Counter(director.entrada(i).nota for i in informe.sin_agente).items():
        print(f"  {n} tarea(s) sin agente: {motivo}")
    if informe.limite_alcanzado:
        print(f"  Parado al llegar al máximo de {maximo} tareas.")
    print()
    _resumen(director)
    return 1 if informe.errores else 0


def _estado(director: Director) -> int:
    for titulo, tareas in _grupos(director):
        print(titulo)
        for t in tareas:
            e = director.entrada(t.id)
            detalle = e.nota
            if e.estado == PENDIENTE and director.deps_sin_aprobar(t):
                detalle = f"espera a {', '.join(director.deps_sin_aprobar(t))}"
            archivos = f"  [{', '.join(e.archivos)}]" if e.archivos and e.estado == ESPERANDO else ""
            print(f"  {ETIQUETAS[e.estado]:<19} {t.id:<34} {detalle}{archivos}".rstrip())
        print()
    _resumen(director)
    return 0


def _aprobar(director: Director, ids: list[str], todo: bool) -> int:
    if todo == bool(ids):
        raise ErrorOrden("Indica qué aprobar (por ejemplo: aprobar ren/concepto) o usa --todo, pero no las dos cosas.")
    aprobadas = director.aprobar_todo() if todo else director.aprobar(ids)
    if not aprobadas:
        print("Nada esperaba tu visto bueno.")
        return 0
    print(f"Aprobado: {', '.join(aprobadas)}")
    print("Ejecuta otra vez para seguir con lo que dependía de esto.")
    return 0


def _resumen(director: Director) -> None:
    cuenta = Counter(director.entrada(t.id).estado for t in director.tareas)
    print("Resumen: " + ", ".join(f"{cuenta[s]} {RESUMEN[s]}" for s in ESTADOS if cuenta[s]))
    if cuenta[ESPERANDO]:
        print("Revisa los archivos en recursos/ y luego usa: aprobar <id> (o --todo), o rechazar <id> --motivo \"...\"")
    elif cuenta[APROBADO] == len(director.tareas):
        print("Todo aprobado. El siguiente paso es: exportar")


def _grupos(director: Director) -> list[tuple[str, list[Tarea]]]:
    titulos = {p.id: p.nombre for p in director.diseno.personajes}
    titulos.update({"sonido": "Efectos de sonido", "musica": "Música"})
    grupos: dict[str, list[Tarea]] = {}
    for t in director.tareas:
        grupos.setdefault(t.id.split("/", 1)[0], []).append(t)
    return [(titulos[clave], tareas) for clave, tareas in grupos.items()]
