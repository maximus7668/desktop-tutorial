"""Subtítulos, capítulos, descripción, presupuesto y subida (con la API simulada)."""
import json
from types import SimpleNamespace

import pytest

from canal import config, metadatos, registro, subtitulos, visuales
from canal.guion import Guion
from canal.subtitulos import Palabra

from .test_guion import BASE


def palabras(textos, paso=0.4):
    res, t = [], 0.0
    for i, w in enumerate(textos):
        res.append(Palabra(w, t, t + paso * 0.9, w.endswith("."), 0))
        t += paso
    return res


def test_srt_formato_y_cortes():
    p = palabras("En mil novecientos veintidós un hombre abrió una tumba. Nadie había entrado en tres mil años.".split())
    srt = subtitulos.srt(p)
    bloques = srt.strip().split("\n\n")
    assert bloques[0].startswith("1\n00:00:00,000 --> ")
    assert all(len(linea) <= 48 for b in bloques for linea in b.split("\n")[2:])
    assert "tumba." in bloques[0]


def test_ass_short_resalta_cada_palabra():
    p = palabras(["¿Qué", "verías", "si", "abrieras", "la", "puerta?"])
    ass = subtitulos.ass_short(p, 1080, 1920, config.cargar()["estilo"])
    eventos = [l for l in ass.splitlines() if l.startswith("Dialogue:") and ",Karaoke," in l]
    assert len(eventos) == 6
    assert "\\c&H0018C5F5" in eventos[0]
    assert "PUERTA?" in ass


def test_ass_escapa_llaves():
    ass = subtitulos.ass_largo(1920, 1080, config.cargar()["estilo"], [(1, 3, "texto {raro}")], [])
    assert "{raro}" not in ass


def test_capitulos_empiezan_en_cero_y_descripcion():
    g = Guion.model_validate(BASE)
    caps = metadatos.capitulos(g, [(0.0, 20.0), (20.0, 45.0), (45.0, 80.0)])
    assert caps[0] == (0.0, "Uno") and caps[1] == (20.0, "Dos")
    rec = [visuales.Recurso(config.CACHE / "x.jpg", "imagen", "wikimedia", "w-1", "https://c/x", "Ana", "CC BY 4.0", True)]
    d = metadatos.descripcion_largo(g, caps, rec)
    assert "0:00 Uno" in d and "0:45 Tres" in d
    assert "Ana — CC BY 4.0" in d
    assert "voz sintética" in d
    assert metadatos.marca_tiempo(3725) == "1:02:05"


def test_tope_de_gasto(tmp_path, monkeypatch):
    monkeypatch.setattr(registro, "MEMORIA", tmp_path)
    cfg = config.cargar()
    cfg["presupuesto"]["mensual_eur"] = 1.0
    registro.apuntar_gasto(cfg, 0.8, "prueba")
    registro.comprobar_gasto(cfg, 0.1, "ok")
    with pytest.raises(SystemExit):
        registro.comprobar_gasto(cfg, 0.5, "demasiado")


def test_miniatura_wikimedia_de_tamano_estandar():
    ii = {"thumburl": "https://upload.wikimedia.org/wikipedia/commons/a/ab/F.jpg", "width": 1500,
          "url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/F.jpg"}
    assert visuales._miniatura_wikimedia(ii) == "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/F.jpg/1280px-F.jpg"
    ii = {"thumburl": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/F.jpg/1920px-F.jpg?utm=1", "width": 4000}
    assert visuales._miniatura_wikimedia(ii).endswith("/1920px-F.jpg")
    assert visuales._miniatura_wikimedia({"url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/F.jpg",
                                          "width": 700}) is None


class _Peticion:
    def __init__(self, resp):
        self.resp = resp

    def execute(self):
        return self.resp


def test_programar_conserva_el_resto_del_estado(monkeypatch, tmp_path):
    from canal import youtube

    enviado = {}

    class Videos:
        def list(self, part, id):
            return _Peticion({"items": [{"status": {"privacyStatus": "private", "embeddable": True, "license": "youtube",
                                                    "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True,
                                                    "publicStatsViewable": True, "uploadStatus": "processed"}}]})

        def update(self, part, body):
            enviado.update(body)
            return _Peticion(body)

    monkeypatch.setattr(youtube, "servicio", lambda *a: SimpleNamespace(videos=lambda: Videos()))
    monkeypatch.setattr(youtube, "MEMORIA", tmp_path)
    monkeypatch.setattr(registro, "MEMORIA", tmp_path)
    from datetime import datetime, timezone

    youtube.programar("abc", datetime(2026, 10, 20, 16, 0, tzinfo=timezone.utc))
    st = enviado["status"]
    assert st["privacyStatus"] == "private" and st["publishAt"] == "2026-10-20T16:00:00Z"
    assert st["containsSyntheticMedia"] is True and st["selfDeclaredMadeForKids"] is False
    assert "uploadStatus" not in st


def test_subir_exige_permiso(monkeypatch, capsys):
    from canal.__main__ import main

    assert main(["subir", "no-existe"]) == 2
    assert "AMARILLO" in capsys.readouterr().out
    assert main(["programar", "abc", "--cuando", "2026-10-20T18:00"]) == 2


def test_buscador_no_evita_las_imagenes_del_propio_video(tmp_path, monkeypatch):
    monkeypatch.setattr(visuales, "MEMORIA", tmp_path)
    (tmp_path / "medios_usados.json").write_text(json.dumps({"otro": ["w-1"], "este": ["w-2"]}))
    b = visuales.Buscador(config.cargar(), (1920, 1080), "este")
    assert b._previos == {"w-1"}


def test_video_de_stock_antes_que_fotos(monkeypatch):
    llamadas = []
    monkeypatch.setitem(visuales.PROVEEDORES, "pexels", (lambda *a: llamadas.append("pv") or [], lambda *a: llamadas.append("pf") or []))
    monkeypatch.setitem(visuales.PROVEEDORES, "wikimedia", (None, lambda *a: llamadas.append("wf") or []))
    b = visuales.Buscador(config.cargar(), (1920, 1080), "x")
    assert b._buscar("q", ["pexels", "wikimedia"], video=True, duracion=3) is None
    assert llamadas == ["pv", "pf", "wf"]


def test_precarga_wikimedia_en_lotes(tmp_path, monkeypatch):
    from canal.guion import Visual

    monkeypatch.setattr(visuales, "CACHE", tmp_path)
    pedidas = []

    def falso_get(url, cfg, params, headers=None, dias=7):
        pedidas.append(params)
        if "pageids" in params:
            return {"query": {"pages": {i: {"pageid": int(i), "title": f"File:{i}.jpg"} for i in params["pageids"].split("|")}}}
        return {"query": {"normalized": [{"from": "File:a_b.jpg", "to": "File:A b.jpg"}],
                          "pages": {"7": {"pageid": 7, "title": "File:A b.jpg"}, "-1": {"title": "File:No.jpg", "missing": ""}}}}

    monkeypatch.setattr(visuales, "_get_json", falso_get)
    vs = [Visual(wikimedia=f"id:wikimedia-{i}") for i in range(60)] + [Visual(wikimedia="File:a_b.jpg"), Visual(wikimedia="File:No.jpg")]
    assert visuales.precargar_wikimedia(vs, config.cargar()) == 61
    assert len(pedidas) == 3  # 50 + 10 ids, 2 títulos en una sola llamada
    base = visuales._params_ficha()
    assert visuales._ruta_cache(visuales.API_COMMONS, {**base, "titles": "File:a_b.jpg"}).exists()
    assert not visuales._ruta_cache(visuales.API_COMMONS, {**base, "titles": "File:No.jpg"}).exists()
