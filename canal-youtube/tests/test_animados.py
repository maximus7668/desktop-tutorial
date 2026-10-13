import pytest
from pydantic import ValidationError

from canal import config
from canal.animados import Dibujante, _desenrollar, _num, guardar_spec
from canal.guion import Visual


def test_validacion_de_graficos_mapas_y_encuadres():
    with pytest.raises(ValidationError):
        Visual(grafico="Sin datos")
    with pytest.raises(ValidationError):
        Visual(grafico="Texto donde va un número", datos=[["a", "b"], ["c", "d"]])
    assert Visual(grafico="Cronología", forma="cronologia", datos=[["1545", "Fundación"], ["1572", "Mercurio"]]).tipo == "grafico"
    with pytest.raises(ValidationError):
        Visual(mapa="Sin puntos")
    with pytest.raises(ValidationError):
        Visual(wikimedia="x", encuadre=[0.8, 0.1, 0.5, 0.5])  # se sale por la derecha
    assert Visual(wikimedia="x", encuadre=[0.2, 0.1, 0.5, 0.5]).encuadre


def test_numeros_al_estilo_espanol():
    assert _num(160000) == "160.000"
    assert _num(45.5, "%") == "45,5%"
    assert _num(70, " t") == "70 t"


def test_ruta_por_el_pacifico_toma_el_camino_corto():
    lons = _desenrollar([{"lon": -99.9}, {"lon": 120.98}])
    assert lons[1] < -180  # Acapulco → Manila hacia el oeste


@pytest.mark.parametrize("tam", [(640, 360), (360, 640)])
def test_dibuja_grafico_y_mapa(tam):
    est = config.cargar()["estilo"]
    g = Visual(grafico="Población", forma="barras", datos=[["A", 3], ["B", 5]], destacar=["B"])
    m = Visual(mapa="Ruta", puntos=[{"n": "Potosí", "lat": -19.6, "lon": -65.8}, {"n": "Sevilla", "lat": 37.4, "lon": -6}], ruta=True)
    for v in (g, m):
        d = Dibujante(guardar_spec(v, tam, est))
        assert d.cuadro(0.0).shape == (tam[1], tam[0], 3)
        assert d.final().size == tam
