"""Del texto del guion a lo que se lee en voz alta, sin perder lo que se muestra en pantalla.

Cada palabra es un Token con dos caras: `texto` (subtítulos: «1922») y `habla` (voz: «mil
novecientos veintidós»). Así la voz pronuncia bien y los subtítulos siguen siendo legibles.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from num2words import num2words


@dataclass
class Token:
    texto: str
    habla: str
    fin_frase: bool = False
    pausa: float = 0.0  # peso de la pausa que sigue (en «letras»)


ABREV_MULTI = [  # (regex, lectura, puede cerrar frase)
    (r"a\.\s?C\.", "antes de Cristo", True),
    (r"d\.\s?C\.", "después de Cristo", True),
    (r"EE\.\s?UU\.", "Estados Unidos", True),
    (r"p\.\s?ej\.", "por ejemplo", False),
    (r"a\.\s?m\.", "de la mañana", True),
    (r"p\.\s?m\.", "de la tarde", True),
]
ABREV = {
    "sr.": ("señor", False), "sra.": ("señora", False), "dr.": ("doctor", False),
    "dra.": ("doctora", False), "etc.": ("etcétera", True), "aprox.": ("aproximadamente", False),
    "vs.": ("contra", False), "nº": ("número", False), "n.º": ("número", False),
    "km": ("kilómetros", False), "kg": ("kilos", False), "cm": ("centímetros", False),
    "km²": ("kilómetros cuadrados", False), "m²": ("metros cuadrados", False),
    "km/h": ("kilómetros por hora", False), "s.": ("siglo", False),
}
UNIDADES = {"km": "kilómetros", "kg": "kilos", "cm": "centímetros", "mm": "milímetros",
            "m": "metros", "km²": "kilómetros cuadrados", "m²": "metros cuadrados",
            "%": "por ciento", "€": "euros", "$": "dólares", "°": "grados", "ºC": "grados"}
ORDINALES = ["", "primero", "segundo", "tercero", "cuarto", "quinto", "sexto", "séptimo",
             "octavo", "noveno", "décimo"]
ROMANOS = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
APERTURA = "¿¡\"«“‘'([—"
CIERRE = ".,;:!?…\"»”’')]—"
PAUSAS = {",": 4.0, ";": 6.0, ":": 6.0, ".": 8.0, "!": 8.0, "?": 8.0, "…": 10.0, "—": 4.0, ")": 4.0, "]": 4.0}
NO_APOCOPE = {"de", "del", "y", "o", "a", "al", "en", "por", "para", "entre", "que", "e"}


def romano(s: str) -> int | None:
    if not re.fullmatch(r"M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})", s or "-"):
        return None
    total = 0
    for i, c in enumerate(s):
        v = ROMANOS[c]
        total += -v if i + 1 < len(s) and ROMANOS[s[i + 1]] > v else v
    return total or None


def _entero(n: int, siguiente: str | None) -> str:
    texto = num2words(n, lang="es")
    if siguiente and siguiente.lower() not in NO_APOCOPE and re.match(r"[a-záéíóúñ]", siguiente.lower()):
        texto = re.sub(r"veintiuno$", "veintiún", texto)
        texto = re.sub(r"\buno$", "un", texto)
    return texto


def _numero(nucleo: str, siguiente: str | None) -> str | None:
    """Convierte un número escrito al estilo español (1.500 · 3,5 · 1914-1918) en palabras."""
    m = re.fullmatch(r"(\d{1,4})[-–](\d{1,4})", nucleo)
    if m:
        return f"{_entero(int(m[1]), None)} a {_entero(int(m[2]), siguiente)}"
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", nucleo):
        nucleo = nucleo.replace(".", "")
    m = re.fullmatch(r"(\d+),(\d+)", nucleo)
    if m:
        decimales = " ".join(num2words(int(d), lang="es") for d in m[2]) if m[2].startswith("0") else num2words(int(m[2]), lang="es")
        return f"{_entero(int(m[1]), None)} coma {decimales}"
    if re.fullmatch(r"\d+", nucleo):
        return _entero(int(nucleo), siguiente)
    return None


def _normalizar(nucleo: str, anterior: str | None, siguiente: str | None) -> str:
    bajo = nucleo.lower()
    if bajo in ABREV:
        return ABREV[bajo][0]
    m = re.fullmatch(r"(\d+)([ºª])", nucleo)
    if m:
        n = int(m[1])
        if n <= 10:
            o = ORDINALES[n]
            return o[:-1] + "a" if m[2] == "ª" else o
        return num2words(n, lang="es", to="ordinal")
    m = re.fullmatch(r"([$€])([\d.,]+)", nucleo)
    if m:
        cifra = _numero(m[2], None)
        if cifra:
            return f"{cifra} {UNIDADES[m[1]]}"
    m = re.fullmatch(r"([\d.,–-]+)(%|€|\$|km²|m²|km|kg|cm|mm|ºC|°)", nucleo)
    if m:
        cifra = _numero(m[1], None)
        if cifra:
            return f"{cifra} {UNIDADES[m[2]]}"
    if nucleo in UNIDADES and anterior and re.search(r"\d", anterior):
        return UNIDADES[nucleo]
    cifra = _numero(nucleo, siguiente)
    if cifra:
        return cifra
    n = romano(nucleo)
    if n and anterior:
        ant = anterior.lower().strip(APERTURA + CIERRE)
        if ant in ("siglo", "siglos") and n <= 21:
            return num2words(n, lang="es")
        if anterior[:1].isupper() and n <= 39 and ant not in ("de", "y"):
            return ORDINALES[n] if n <= 10 else num2words(n, lang="es")
    return nucleo


def _partir(palabra: str) -> tuple[str, str, str]:
    i, j = 0, len(palabra)
    while i < j and palabra[i] in APERTURA:
        i += 1
    while j > i and palabra[j - 1] in CIERRE:
        j -= 1
    # «n.º», «etc.», «Sr.»: el punto es parte de la abreviatura
    if j < len(palabra) and palabra[j] == "." and (palabra[i:j + 1].lower() in ABREV):
        j += 1
    return palabra[:i], palabra[i:j], palabra[j:]


def _pausa(cola: str) -> float:
    return max((PAUSAS.get(c, 0.0) for c in cola), default=0.0)


def _limpiar(s: str) -> str:
    """Signos que la voz no debe leer: comillas fuera, paréntesis y rayas como comas."""
    s = re.sub(r"[«»“”‘’\"(\[]", "", s)
    s = re.sub(r"[)\]—–]", ",", s)
    s = re.sub(r",+\s*([.!?…])", r"\1", s)
    return re.sub(r",{2,}", ",", s)


def tokenizar(texto: str, normalizar: bool = True, pronunciacion: dict[str, str] | None = None) -> list[Token]:
    texto = re.sub(r"\s+", " ", texto.strip())
    patron = "|".join(f"(?:{p})" for p, _, _ in ABREV_MULTI)
    piezas: list[dict] = []
    pos = 0
    for m in re.finditer(rf"(?<![\wáéíóúñ])(?:{patron})[,;:!?…»”)\]]*", texto):
        piezas += [{"crudo": w} for w in texto[pos:m.start()].split()]
        for p, lectura, cierra in ABREV_MULTI:
            mm = re.match(p, m.group(0))
            if mm:
                piezas.append({"crudo": m.group(0), "fija": lectura, "cola": m.group(0)[mm.end():], "cierra": cierra})
                break
        pos = m.end()
    piezas += [{"crudo": w} for w in texto[pos:].split()]

    # signos sueltos («—», «…», «%») se pegan a la palabra anterior
    fusion: list[dict] = []
    for p in piezas:
        p.setdefault("mostrar", p["crudo"])
        if fusion and "fija" not in p and re.fullmatch(r"[—–\-…,;:.!?»”)\]]+", p["crudo"]):
            a = fusion[-1]
            a["mostrar"] += (" " if p["crudo"][0] in "—–-" else "") + p["crudo"]
            a["crudo"] += p["crudo"]
            if "fija" in a:
                a["cola"] += p["crudo"]
        else:
            fusion.append(p)

    pron = {k.lower(): v for k, v in (pronunciacion or {}).items()}
    tokens: list[Token] = []
    for i, p in enumerate(fusion):
        anterior = fusion[i - 1]["crudo"] if i else None
        sig = fusion[i + 1]["crudo"] if i + 1 < len(fusion) else None
        if "fija" in p:
            cola = p["cola"]
            cierra_ya = bool(re.search(r"[.!?…]", cola))
            fin = cierra_ya or (p["cierra"] and (sig is None or sig[:1].isupper() or sig[:1] in "¿¡"))
            habla = p["fija"] + _limpiar(cola) + ("." if fin and not cierra_ya else "")
            tokens.append(Token(p["mostrar"], habla, fin, _pausa(cola) or (8.0 if fin else 0.0)))
            continue
        cabeza, nucleo, cola = _partir(p["crudo"])
        sig_nucleo = _partir(sig)[1] if sig else None
        hablado = _normalizar(nucleo, anterior, sig_nucleo) if (normalizar and nucleo) else nucleo
        if nucleo.lower() in pron:
            hablado = pron[nucleo.lower()]
        abrev = ABREV.get(nucleo.lower())
        if abrev and nucleo.endswith("."):
            fin = bool(abrev[1]) and (sig is None or sig[:1].isupper() or sig[:1] in "¿¡")
            if fin and not re.search(r"[.!?…]", cola):
                cola = "." + cola
        else:
            fin = bool(re.search(r"[.!?…]", cola))
        habla = (_limpiar(cabeza) + hablado + _limpiar(cola)).strip() or p["crudo"]
        tokens.append(Token(p["mostrar"], habla, fin, _pausa(cola) if cola else 0.0))
    if tokens:
        tokens[-1].fin_frase = True
    return tokens


def frases(tokens: list[Token]) -> list[list[Token]]:
    res, actual = [], []
    for t in tokens:
        actual.append(t)
        if t.fin_frase:
            res.append(actual)
            actual = []
    if actual:
        res.append(actual)
    return res


def texto_hablado(tokens: list[Token]) -> str:
    return " ".join(t.habla for t in tokens)


def _letras(s: str) -> int:
    return len(re.findall(r"[\wáéíóúüñÁÉÍÓÚÜÑ]", s))


def repartir(tokens: list[Token], inicio: float, fin: float) -> list[tuple[float, float]]:
    """Reparte [inicio, fin] entre los tokens según lo que cuesta decirlos (letras y pausas)."""
    if not tokens:
        return []
    pesos = [_letras(t.habla) + 1.0 for t in tokens]
    pausas = [t.pausa for t in tokens[:-1]] + [0.0]
    escala = (fin - inicio) / (sum(pesos) + sum(pausas))
    res, t = [], inicio
    for p, pa in zip(pesos, pausas):
        res.append((t, t + p * escala))
        t += (p + pa) * escala
    return res


def tiempos_por_caracteres(tokens: list[Token], inicios: list[float], finales: list[float]) -> list[tuple[float, float]]:
    """Con alineación por caracteres (ElevenLabs) sobre texto_hablado(tokens)."""
    res, pos = [], 0
    n = len(inicios)
    for t in tokens:
        a, b = pos, pos + len(t.habla) - 1
        a, b = min(a, n - 1), min(max(b, a), n - 1)
        res.append((inicios[a], finales[b]))
        pos += len(t.habla) + 1
    return res
