from canal.texto import frases, repartir, texto_hablado, tiempos_por_caracteres, tokenizar


def hablado(t: str) -> str:
    return texto_hablado(tokenizar(t))


def test_numeros_y_anios():
    assert hablado("En 1922 abrió la tumba.") == "En mil novecientos veintidós abrió la tumba."
    assert hablado("Tardó 3.000 años.") == "Tardó tres mil años."
    assert "tres coma cinco kilómetros" in hablado("Caminó 3,5 km.")


def test_apocope_ante_sustantivo_pero_no_ante_de():
    assert hablado("Tenía 21 años y 1 hijo.") == "Tenía veintiún años y un hijo."
    assert hablado("El 1 de enero.") == "El uno de enero."


def test_porcentaje_moneda_y_romanos():
    assert hablado("El 45% pagó 300 €.") == "El cuarenta y cinco por ciento pagó trescientos euros."
    assert hablado("Costó $20.") == "Costó veinte dólares."
    assert hablado("En el siglo XIX reinaba Felipe II.") == "En el siglo diecinueve reinaba Felipe segundo."
    assert "Alfonso trece" in hablado("Alfonso XIII huyó.")


def test_abreviaturas_y_frases():
    toks = tokenizar("Murió en el 30 a. C. Roma lo celebró. El Dr. Pérez no.")
    assert [" ".join(t.texto for t in f) for f in frases(toks)] == [
        "Murió en el 30 a. C.", "Roma lo celebró.", "El Dr. Pérez no."]
    assert "treinta antes de Cristo." in texto_hablado(toks)
    assert "doctor Pérez" in texto_hablado(toks)


def test_parentesis_y_comillas_no_se_leen():
    h = hablado("La guerra (1914-1918) acabó. Dijo «basta».")
    assert "(" not in h and "«" not in h
    assert "mil novecientos catorce a mil novecientos dieciocho," in h


def test_lo_mostrado_se_conserva():
    toks = tokenizar("En 1922, Carter llegó.")
    assert [t.texto for t in toks] == ["En", "1922,", "Carter", "llegó."]


def test_pronunciacion_personalizada():
    toks = tokenizar("Howard Carter", pronunciacion={"Howard": "Jáuard"})
    assert texto_hablado(toks) == "Jáuard Carter"


def test_repartir_ocupa_el_tramo_y_es_monotono():
    toks = tokenizar("Una frase corta, con una pausa. Y otra más.")
    t = repartir(toks, 1.0, 5.0)
    assert t[0][0] == 1.0 and abs(t[-1][1] - 5.0) < 1e-6
    assert all(a < b for a, b in t)
    assert all(t[i][1] <= t[i + 1][0] + 1e-9 for i in range(len(t) - 1))


def test_tiempos_por_caracteres():
    toks = tokenizar("Hola mundo")
    texto = texto_hablado(toks)
    ini = [i * 0.1 for i in range(len(texto))]
    fin = [x + 0.08 for x in ini]
    t = tiempos_por_caracteres(toks, ini, fin)
    assert t[0] == (0.0, ini[3] + 0.08)
    assert t[1][0] == ini[5]
