import copy

import pytest
from pydantic import ValidationError

from canal import config
from canal.guion import Guion, Visual, revisar, similitud

BASE = {
    "id": "prueba-guion",
    "tema": "Prueba",
    "titulos": ["Un título razonable"],
    "descripcion": "Descripción.",
    "fuentes": [{"titulo": f"F{i}", "url": f"https://ejemplo.org/{i}"} for i in range(3)],
    "miniatura": {"texto": "Texto", "visual": {"tarjeta": "X"}},
    "escenas": [
        {"id": "a", "capitulo": "Uno", "narracion": "Frase corta de gancho.", "visuales": [{"stock": "desert"}]},
        {"id": "b", "capitulo": "Dos", "narracion": "Otra frase.", "visuales": [{"foto": "pyramid"}]},
        {"id": "c", "capitulo": "Tres", "narracion": "Última frase.", "visuales": [{"wikimedia": "tomb"}]},
    ],
}


def niveles(d):
    hs, _ = revisar(Guion.model_validate(d), config.cargar())
    return [(h.nivel, h.texto) for h in hs]


def test_visual_exige_un_solo_tipo():
    with pytest.raises(ValidationError):
        Visual(stock="a", foto="b")
    with pytest.raises(ValidationError):
        Visual()
    assert Visual(dato="3.000", sub="años").tipo == "dato"


def test_ids_de_escena_unicos_y_referencias_validas():
    d = copy.deepcopy(BASE)
    d["escenas"][1]["id"] = "a"
    with pytest.raises(ValidationError):
        Guion.model_validate(d)
    d = copy.deepcopy(BASE)
    d["shorts"] = [{"id": "s", "titulo": "t", "escenas": [{"id": "x", "narracion": "n", "visuales": [{"de_escena": "zz"}]}]}]
    with pytest.raises(ValidationError):
        Guion.model_validate(d)


def test_errores_bloqueantes():
    d = copy.deepcopy(BASE)
    d["descripcion"] = "Usa <etiquetas>"
    d["titulos"] = ["x" * 101]
    d["fuentes"] = []
    errores = [t for n, t in niveles(d) if n == "error"]
    assert any("< ni >" in t for t in errores)
    assert any("101 caracteres" in t for t in errores)
    assert any("fuentes" in t for t in errores)


def test_muletillas_y_frases_largas():
    d = copy.deepcopy(BASE)
    d["escenas"][0]["narracion"] = "Hola a todos, en este vídeo vamos a ver algo. " + " ".join(["palabra"] * 40) + "."
    avisos = [t for n, t in niveles(d) if n == "aviso"]
    assert any("hola a todos" in t for t in avisos)
    assert any("en este vídeo" in t for t in avisos)
    assert any("pártela" in t for t in avisos)


def test_short_demasiado_largo_es_error():
    d = copy.deepcopy(BASE)
    d["shorts"] = [{"id": "s", "titulo": "t", "escenas": [
        {"id": "x", "narracion": " ".join(["palabra"] * 480), "visuales": [{"de_escena": "a"}]}]}]
    assert any(n == "error" and "short s" in t for n, t in niveles(d))


def test_repeticion_entre_guiones():
    texto = " ".join(f"palabra{i}" for i in range(200))
    assert similitud(texto, texto) == 1.0
    assert similitud(texto, "otra cosa completamente distinta sin nada en comun") == 0.0
    hs, _ = revisar(Guion.model_validate(BASE), config.cargar(), {"otro": "Frase corta de gancho. Otra frase. Última frase."})
    assert any(h.nivel == "error" and "otro" in h.texto for h in hs)
