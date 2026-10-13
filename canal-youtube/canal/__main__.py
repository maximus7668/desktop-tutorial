"""Órdenes del agente:  python -m canal <orden> ...   (python -m canal -h para ver todas)"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from . import config, registro


def _guion(ruta: str):
    from .guion import cargar

    p = Path(ruta)
    if not p.exists() and (config.GUIONES / ruta).exists():
        p = config.GUIONES / ruta
    if not p.exists() and (config.GUIONES / f"{ruta}.json").exists():
        p = config.GUIONES / f"{ruta}.json"
    return cargar(p)


def comprobar(a, cfg):
    ok = True
    for prog in ("ffmpeg", "ffprobe"):
        if not shutil.which(prog):
            print(f"❌ falta {prog}")
            ok = False
    filtros = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    print("✅ ffmpeg con libass" if " subtitles " in filtros else "❌ ffmpeg sin libass (subtítulos)")
    for f in ("fuente_titulos", "fuente_subtitulos", "fuente_texto"):
        nombre = cfg["estilo"][f]
        print(("✅" if (config.FUENTES / nombre).exists() else "❌") + f" fuente {nombre}")
    claves = {"voz": {"elevenlabs": "ELEVENLABS_API_KEY", "azure": "AZURE_SPEECH_KEY", "openai": "OPENAI_API_KEY"},
              "stock": {"pexels": "PEXELS_API_KEY", "pixabay": "PIXABAY_API_KEY"}}
    prov = cfg["voz"]["proveedor"]
    if prov in claves["voz"]:
        tiene = bool(config.clave(claves["voz"][prov], obligatoria=False))
        print(("✅" if tiene else "❌") + f" voz {prov} ({claves['voz'][prov]})")
        ok &= tiene
    else:
        print(f"ℹ️  voz {prov}: gratis y local, solo para pruebas (para publicar, ElevenLabs o Azure)")
    for s in cfg["visuales"]["stock"]:
        if s in claves["stock"]:
            print(("✅" if config.clave(claves["stock"][s], obligatoria=False) else "⚠️ ") + f" {s} ({claves['stock'][s]})")
    print(("✅" if config.clave("YOUTUBE_API_KEY", obligatoria=False) else "⚠️ ") + " YOUTUBE_API_KEY (tendencias)")
    from .youtube import CLIENTE, TOKEN

    print(("✅" if (TOKEN.exists() or config.clave("YT_TOKEN_JSON", obligatoria=False)) else "⚠️ ")
          + " autorización de YouTube (python -m canal autorizar)")
    print(f"💶 gasto de este mes: {registro.gasto_mes():.2f} € de {cfg['presupuesto']['mensual_eur']:.2f} €")
    return 0 if ok else 1


def validar(a, cfg):
    from .guion import anteriores, revisar

    g = _guion(a.guion)
    hallazgos, stats = revisar(g, cfg, anteriores(config.GUIONES))
    print(json.dumps(stats, ensure_ascii=False))
    for h in hallazgos:
        print(("❌ " if h.nivel == "error" else "⚠️  ") + h.texto)
    errores = [h for h in hallazgos if h.nivel == "error"]
    print("✅ sin errores" if not errores else f"{len(errores)} errores: corrígelos antes de producir")
    return 1 if errores else 0


def visuales(a, cfg):
    from .calidad import hoja_visuales

    g = _guion(a.guion)
    carpeta = config.SALIDA / g.id
    carpeta.mkdir(parents=True, exist_ok=True)
    rutas = [hoja_visuales(g, cfg, carpeta / "visuales-largo.jpg")]
    for i, s in enumerate(g.shorts):
        rutas.append(hoja_visuales(g, cfg, carpeta / f"visuales-{s.id}.jpg", short=i))
    for r in rutas:
        print(r)
    return 0


def producir(a, cfg):
    from .calidad import informe
    from .guion import anteriores, revisar
    from .montaje import producir as prod

    g = _guion(a.guion)
    hallazgos, _ = revisar(g, cfg, anteriores(config.GUIONES))
    errores = [h for h in hallazgos if h.nivel == "error"]
    if errores:
        for h in errores:
            print("❌ " + h.texto)
        return 1
    prod(g, cfg, solo=a.solo, proveedor_voz=a.voz)
    ruta, ok = informe(g, cfg, config.SALIDA / g.id)
    print(ruta.read_text(encoding="utf-8"))
    print(f"Archivos en {config.SALIDA / g.id}")
    return 0 if ok else 1


def paquete(a, cfg):
    """Instrucciones para subirlo a mano en YouTube Studio (sin API)."""
    carpeta = config.SALIDA / a.id
    meta = json.loads((carpeta / "metadatos.json").read_text(encoding="utf-8"))
    l = meta["largo"]
    pasos = [f"# Subir «{l['titulo']}» a mano", "",
             "1. YouTube Studio → Crear → Subir vídeos → `" + l["archivo"] + "`.",
             "2. Título (copia):", "", "```", l["titulo"], "```", "",
             "3. Descripción (copia):", "", "```", l["descripcion"], "```", "",
             f"4. Miniatura: `{l['miniaturas'][0] if l['miniaturas'] else '-'}`. En «Probar y comparar» añade las otras dos.",
             "5. Público: «No, no es contenido para niños».",
             f"6. Más opciones → Contenido alterado o sintético: **{'Sí' if meta['contenido_sintetico_realista'] else 'No'}**.",
             "7. Etiquetas: " + ", ".join(l["etiquetas"]),
             f"8. Idioma: español · Categoría: {meta['categoria']} · Subtítulos: sube `{l['subtitulos']}`.",
             "9. Visibilidad: **Privado** hasta que lo apruebes; luego «Programar».", ""]
    for sid, s in meta.get("shorts", {}).items():
        pasos += [f"## Short {sid}: `{s['archivo']}`", "", "```", s["titulo"], "", s["descripcion"], "```",
                  "Después, en Studio → Contenido → este Short → «Vídeo relacionado»: el largo.", ""]
    ruta = carpeta / "SUBIR.md"
    ruta.write_text("\n".join(pasos), encoding="utf-8")
    print(ruta)
    return 0


def autorizar(a, cfg):
    from .youtube import TOKEN, credenciales

    credenciales(interactivo=True)
    print(f"✅ Autorizado. Token en {TOKEN} (no lo subas al repo). En la nube, pégalo en el secreto YT_TOKEN_JSON.")
    return 0


def subir(a, cfg):
    from .youtube import subir_video_local

    if not (cfg["autonomia"]["subir_privado"] or a.confirmo):
        print("⛔ Subir está en AMARILLO: hace falta el ok del dueño para este vídeo (--confirmo) "
              "o autonomia.subir_privado: true en canal.yaml.")
        return 2
    carpeta = config.SALIDA / a.id
    calidad = (carpeta / "calidad.md").read_text(encoding="utf-8") if (carpeta / "calidad.md").exists() else ""
    if "listo para tu revisión" not in calidad:
        print("⛔ El control de calidad no está en verde. Produce y revisa antes de subir.")
        return 2
    subir_video_local(a.id, cfg, carpeta, a.cuales)
    return 0


def programar(a, cfg):
    from .youtube import programar as prog

    if not a.confirmo:
        print("⛔ Publicar es ROJO: solo con el ok expreso del dueño para este vídeo y esta fecha (--confirmo).")
        return 2
    cuando = datetime.fromisoformat(a.cuando)
    if cuando.tzinfo is None:
        cuando = cuando.astimezone()
    prog(a.youtube_id, cuando)
    print(f"✅ {a.youtube_id} se publicará el {cuando.isoformat()}")
    return 0


def metricas(a, cfg):
    from . import metricas as m

    if a.crear_informe:
        print("Trabajo de informes de CTR:", m.crear_informe(), "(los datos llegan en 48-72 h)")
    print(m.resumen(a.dias).read_text(encoding="utf-8"))
    return 0


def tendencias(a, cfg):
    from .tendencias import informe

    ruta = informe(a.terminos, a.dias, a.region, 60 if a.shorts else 240)
    print(ruta.read_text(encoding="utf-8"))
    return 0


def marca(a, cfg):
    from .marca import crear

    for r in crear(cfg):
        print(r)
    return 0


def gastos(a, cfg):
    print(f"{registro.gasto_mes():.2f} € este mes (tope {cfg['presupuesto']['mensual_eur']:.2f} €)")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m canal", description="Agente del canal de YouTube")
    p.add_argument("--config", help="otro canal.yaml")
    sub = p.add_subparsers(dest="orden", required=True)
    sub.add_parser("comprobar", help="qué está listo y qué falta (herramientas, claves, gasto)")
    s = sub.add_parser("validar", help="revisión editorial del guion")
    s.add_argument("guion")
    s = sub.add_parser("visuales", help="hoja con la imagen elegida para cada plano, para revisarla")
    s.add_argument("guion")
    s = sub.add_parser("producir", help="voz, montaje, Shorts, miniaturas, metadatos y control de calidad")
    s.add_argument("guion")
    s.add_argument("--solo", choices=["largo", "shorts"])
    s.add_argument("--voz", help="otro proveedor de voz para esta vez (p. ej. piper para un borrador)")
    s = sub.add_parser("paquete", help="instrucciones para subirlo a mano en Studio")
    s.add_argument("id")
    sub.add_parser("autorizar", help="conectar con tu canal de YouTube (en tu ordenador, una vez)")
    s = sub.add_parser("subir", help="subir en PRIVADO (amarillo)")
    s.add_argument("id")
    s.add_argument("--cuales", choices=["todo", "largo", "shorts"], default="todo")
    s.add_argument("--confirmo", action="store_true", help="el dueño ha dado el ok para este vídeo")
    s = sub.add_parser("programar", help="programar la publicación (rojo)")
    s.add_argument("youtube_id")
    s.add_argument("--cuando", required=True, help="2026-10-20T18:00 (hora local)")
    s.add_argument("--confirmo", action="store_true")
    s = sub.add_parser("metricas", help="cómo van los vídeos → memoria/metricas.md")
    s.add_argument("--dias", type=int, default=28)
    s.add_argument("--crear-informe", action="store_true", help="activar el informe de CTR (una vez)")
    s = sub.add_parser("tendencias", help="vídeos atípicos de un tema → memoria/tendencias/")
    s.add_argument("terminos", nargs="+")
    s.add_argument("--dias", type=int, default=60)
    s.add_argument("--region", help="ES, MX, US, AR, CO…")
    s.add_argument("--shorts", action="store_true", help="incluir vídeos de menos de 4 min")
    sub.add_parser("gastos", help="gasto del mes")
    sub.add_parser("marca", help="avatar y banner del canal con su nombre → salida/marca/")
    a = p.parse_args(argv)
    cfg = config.cargar(a.config)
    ordenes = {"comprobar": comprobar, "validar": validar, "visuales": visuales, "producir": producir,
               "paquete": paquete, "autorizar": autorizar, "subir": subir, "programar": programar,
               "metricas": metricas, "tendencias": tendencias, "gastos": gastos, "marca": marca}
    return ordenes[a.orden](a, cfg)


if __name__ == "__main__":
    sys.exit(main())
