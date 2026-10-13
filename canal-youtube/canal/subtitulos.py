"""Subtítulos y rótulos: ASS para quemar en el vídeo (karaoke en Shorts, rótulos y capítulos en
los largos) y SRT para subir a YouTube."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .graficos import rgb


@dataclass
class Palabra:
    texto: str
    ini: float
    fin: float
    fin_frase: bool = False
    escena: int = 0


def _t_ass(s: float) -> str:
    s = max(0.0, s)
    h, r = divmod(round(s * 100), 360000)
    m, r = divmod(r, 6000)
    return f"{h}:{m:02d}:{r // 100:02d}.{r % 100:02d}"


def _t_srt(s: float) -> str:
    ms = round(max(0.0, s) * 1000)
    h, r = divmod(ms, 3600000)
    m, r = divmod(r, 60000)
    return f"{h:02d}:{m:02d}:{r // 1000:02d},{r % 1000:03d}"


def color_ass(hexa: str, alfa: int = 0) -> str:
    r, g, b = rgb(hexa)
    return f"&H{alfa:02X}{b:02X}{g:02X}{r:02X}"


def _escapar(t: str) -> str:
    return t.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


def _limpia(t: str) -> str:
    """Para subtítulos de Short: sin comas ni puntos sueltos, que ensucian."""
    t = re.sub(r"[«»“”\"]", "", t)
    return re.sub(r"[.,;:…]+$", "", t).strip()


def cabecera(w: int, h: int, estilos: list[str]) -> str:
    return (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {w}\nPlayResY: {h}\nWrapStyle: 0\nScaledBorderAndShadow: yes\nYCbCr Matrix: TV.709\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding\n" + "\n".join(estilos) + "\n\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


def _estilo(nombre, fuente, tam, primario, borde, fondo, borde_px, sombra, alin=5, estilo_borde=1, espaciado=0,
            margen_v=0) -> str:
    return (f"Style: {nombre},{fuente},{tam},{primario},{primario},{borde},{fondo},0,0,0,0,100,100,{espaciado},0,"
            f"{estilo_borde},{borde_px},{sombra},{alin},60,60,{margen_v},1")


def _linea(ini, fin, estilo, texto, capa=0) -> str:
    return f"Dialogue: {capa},{_t_ass(ini)},{_t_ass(fin)},{estilo},,0,0,0,,{texto}\n"


def nombre_fuente(archivo: str) -> str:
    """«Montserrat-Black.ttf» → «Montserrat Black» (nombre que busca libass)."""
    base = archivo.rsplit(".", 1)[0].replace("-Regular", "")
    return base.replace("-", " ")


def agrupar(palabras: list[Palabra], max_palabras: int = 3, max_letras: int = 16) -> list[list[Palabra]]:
    grupos, actual = [], []
    for p in palabras:
        largo = sum(len(_limpia(x.texto)) + 1 for x in actual) + len(_limpia(p.texto))
        if actual and (len(actual) >= max_palabras or largo > max_letras):
            grupos.append(actual)
            actual = []
        actual.append(p)
        if p.fin_frase or re.search(r"[,;:—]$", p.texto):
            grupos.append(actual)
            actual = []
    if actual:
        grupos.append(actual)
    return grupos


def ass_short(palabras: list[Palabra], w: int, h: int, estilo: dict, max_palabras: int = 3,
              rotulos: list[tuple[float, float, str]] | None = None, mayusculas: bool = True) -> str:
    acento = color_ass(estilo["color_acento"])
    blanco = color_ass(estilo["color_texto"])
    negro = "&H00000000"
    tam = int(w * 0.107)  # en ASS el tamaño es la altura de línea: las mayúsculas ocupan ~57 %
    fuente = nombre_fuente(estilo["fuente_subtitulos"])
    estilos = [
        _estilo("Karaoke", fuente, tam, blanco, negro, "&H96000000", max(5, tam // 13), 3),
        _estilo("Gancho", nombre_fuente(estilo["fuente_titulos"]), int(w * 0.125), negro, acento, "&H00000000",
                int(w * 0.02), 0, alin=8, estilo_borde=3),
        _estilo("Aviso", "Montserrat SemiBold", int(w * 0.03), "&H40FFFFFF", "&H00000000", "&H80000000", 0, 2, alin=7),
    ]
    out = cabecera(w, h, estilos)
    y = int(h * 0.62)
    grupos = agrupar(palabras, max_palabras, max_letras=13)
    for gi, g in enumerate(grupos):
        fin_grupo = g[-1].fin
        if gi + 1 < len(grupos) and grupos[gi + 1][0].ini - fin_grupo < 0.35:
            fin_grupo = grupos[gi + 1][0].ini
        textos = [_escapar(_limpia(p.texto)) for p in g]
        if mayusculas:
            textos = [t.upper() for t in textos]
        for i, p in enumerate(g):
            ini = p.ini if i else g[0].ini
            fin = g[i + 1].ini if i + 1 < len(g) else fin_grupo
            if fin <= ini:
                continue
            partes = [(f"{{\\c{acento}\\fscx108\\fscy108}}{t}{{\\c{blanco}\\fscx100\\fscy100}}" if j == i else t)
                      for j, t in enumerate(textos)]
            pop = "\\fscx86\\fscy86\\t(0,110,\\fscx100\\fscy100)" if i == 0 else ""
            out += _linea(ini, fin, "Karaoke", f"{{\\an5\\pos({w // 2},{y}){pop}}}" + " ".join(partes))
    for ini, fin, texto in rotulos or []:
        out += _linea(ini, fin, "Gancho", f"{{\\an8\\pos({w // 2},{int(h * 0.12)})\\fad(120,200)}}{_escapar(texto.upper())}", 1)
    if estilo.get("aviso_ia"):
        out += _linea(0.3, 5.5, "Aviso", f"{{\\an7\\pos({int(w * 0.06)},{int(h * 0.035)})\\fad(200,400)}}Voz generada con IA", 1)
    return out


def ass_largo(w: int, h: int, estilo: dict, rotulos: list[tuple[float, float, str]],
              capitulos: list[tuple[float, int, str]], palabras: list[Palabra] | None = None) -> str:
    """Rótulos (texto_pantalla), cartelas de capítulo y, si se pide, subtítulos completos."""
    acento = color_ass(estilo["color_acento"])
    blanco = color_ass(estilo["color_texto"])
    oscuro = color_ass(estilo["color_fondo"])
    titulos = nombre_fuente(estilo["fuente_titulos"])
    texto = nombre_fuente(estilo["fuente_texto"])
    k = h / 1080
    estilos = [
        _estilo("Rotulo", titulos, int(96 * k), oscuro, acento, "&H00000000", int(20 * k), 0, alin=1, estilo_borde=3),
        _estilo("CapNum", texto, int(52 * k), acento, "&H00000000", "&H80000000", 0, int(2 * k), alin=4, espaciado=8),
        _estilo("CapTitulo", titulos, int(190 * k), blanco, "&H00000000", "&H80000000", 0, int(5 * k), alin=4),
        _estilo("Panel", texto, 20, "&H00000000", "&H00000000", "&H00000000", 0, 0, alin=7),
        _estilo("Sub", texto, int(58 * k), blanco, "&H00000000", "&H80000000", int(3 * k), int(1 * k), alin=2,
                margen_v=int(64 * k)),
        _estilo("Aviso", "Montserrat SemiBold", int(28 * k), "&H50FFFFFF", "&H00000000", "&H80000000", 0, 2, alin=3),
    ]
    out = cabecera(w, h, estilos)
    x0 = int(w * 0.065)
    for ini, fin, t in rotulos:
        out += _linea(ini, fin, "Rotulo",
                      f"{{\\an1\\pos({x0},{int(h * 0.86)})\\fad(160,220)\\fscx94\\fscy94\\t(0,220,\\fscx100\\fscy100)}}"
                      f"{_escapar(t.upper())}", 2)
    for ini, num, titulo in capitulos:
        fin = ini + 3.2
        panel = (f"{{\\an7\\pos(0,0)\\p1\\bord0\\shad0\\blur40\\alpha&H50&\\c&H000000&\\fad(250,350)}}"
                 f"m 0 0 l {int(w * 0.62)} 0 l {int(w * 0.48)} {h} l 0 {h}{{\\p0}}")
        out += _linea(ini, fin, "Panel", panel, 1)
        out += _linea(ini + 0.1, fin, "CapNum", f"{{\\an1\\pos({x0},{int(h * 0.40)})\\fad(250,350)}}CAPÍTULO {num}", 3)
        out += _linea(ini + 0.2, fin, "CapTitulo",
                      f"{{\\an7\\pos({x0},{int(h * 0.42)})\\fad(300,350)}}{_envolver(_escapar(titulo.upper()), 16)}", 3)
    for ini, fin, t in (_cues(palabras) if palabras else []):
        out += _linea(ini, fin, "Sub", _escapar(t).replace(" | ", "\\N"), 0)
    if estilo.get("aviso_ia"):
        out += _linea(0.5, 7.0, "Aviso", f"{{\\an3\\pos({w - int(w * 0.035)},{h - int(h * 0.04)})\\fad(300,500)}}Voz generada con IA", 1)
    return out


def _envolver(t: str, ancho: int) -> str:
    lineas, actual = [], ""
    for p in t.split():
        if actual and len(actual) + 1 + len(p) > ancho:
            lineas.append(actual)
            actual = p
        else:
            actual = f"{actual} {p}".strip()
    lineas.append(actual)
    return "\\N".join(lineas)


def _cues(palabras: list[Palabra], max_letras: int = 84, max_seg: float = 6.0) -> list[tuple[float, float, str]]:
    """Trozos de subtítulo legibles: hasta 2 líneas de 42 caracteres, cortando en fin de frase."""
    cues, actual = [], []
    for p in palabras:
        actual.append(p)
        texto = " ".join(x.texto for x in actual)
        if p.fin_frase or len(texto) >= max_letras - 8 or (actual[-1].fin - actual[0].ini) >= max_seg:
            cues.append(actual)
            actual = []
    if actual:
        cues.append(actual)
    res = []
    for c in cues:
        texto = " ".join(x.texto for x in c)
        if len(texto) > 42:
            mitad, mejor = len(texto) / 2, None
            pos = 0
            for i, x in enumerate(c[:-1]):
                pos += len(x.texto) + 1
                if mejor is None or abs(pos - mitad) < abs(mejor[0] - mitad):
                    mejor = (pos, i)
            i = mejor[1]
            texto = " ".join(x.texto for x in c[:i + 1]) + " | " + " ".join(x.texto for x in c[i + 1:])
        res.append((c[0].ini, c[-1].fin + 0.15, texto))
    return res


def srt(palabras: list[Palabra]) -> str:
    out = []
    for i, (ini, fin, t) in enumerate(_cues(palabras), 1):
        out.append(f"{i}\n{_t_srt(ini)} --> {_t_srt(fin)}\n{t.replace(' | ', chr(10))}\n")
    return "\n".join(out)
