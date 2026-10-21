from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

from app.productora import noticias, pipeline

NOW = datetime.now(timezone.utc)
RSS = f"""<?xml version="1.0"?><rss><channel>
<item><title>OpenAI compra la startup Orchestra Bio</title><link>https://www.xataka.com/a</link>
<pubDate>{format_datetime(NOW - timedelta(hours=2))}</pubDate><description>&lt;p&gt;Texto&lt;/p&gt;</description></item>
<item><title>Noticia antigua</title><link>https://www.xataka.com/b</link>
<pubDate>{format_datetime(NOW - timedelta(days=5))}</pubDate></item>
</channel></rss>""".encode()
ATOM = f"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>OpenAI compra Orchestra Bio, startup de biotecnología</title>
<link rel="alternate" href="https://techcrunch.com/x"/><updated>{(NOW - timedelta(hours=1)).isoformat()}</updated></entry>
</feed>""".encode()


def test_parse_rss_y_atom():
    rss = noticias.parse(RSS, "Xataka", "medio")
    atom = noticias.parse(ATOM, "TechCrunch", "medio")
    assert rss[0]["resumen"] == "Texto" and rss[0]["dominio"] == "xataka.com"
    assert atom[0]["url"] == "https://techcrunch.com/x"


def test_agrupa_mismo_tema_y_descarta_viejas_y_ya_contadas():
    items = noticias.parse(RSS, "Xataka", "medio") + noticias.parse(ATOM, "TechCrunch", "medio")
    c = noticias.candidates(items, seen=[])
    assert len(c) == 1 and c[0]["medios"] == ["techcrunch.com", "xataka.com"]
    assert noticias.candidates(items, seen=[set(c[0]["tokens"])]) == []


def _guion(**over):
    segs = [{"texto": " ".join(["palabra"] * 20), "panel": "X", "afirmaciones": []} for _ in range(7)]
    segs[0] = {"texto": "Gancho corto y cierto", "panel": "X", "afirmaciones": ["a1"]}
    g = {"segmentos": segs, "fuentes": [{"url": "https://a.com"}],
         "afirmaciones": [{"id": "a1", "estado": "confirmado", "fuentes": ["https://a.com/1", "https://www.b.es/2"]}],
         "articulo": {"titulo_seo": "t", "parrafos": ["p"]}}
    g.update(over)
    return g


def test_guion_valido():
    assert pipeline.validar_guion(_guion(), {"a.com", "b.es"}) == []


def test_afirmacion_con_una_sola_fuente_o_dominio_inventado_falla():
    one = _guion(afirmaciones=[{"id": "a1", "estado": "confirmado", "fuentes": ["https://a.com/1", "https://a.com/2"]}])
    assert any("1 dominio" in e for e in pipeline.validar_guion(one, {"a.com"}))
    assert any("no vistos" in e for e in pipeline.validar_guion(_guion(), {"a.com"}))


def test_segmento_no_puede_narrar_algo_no_verificado():
    g = _guion(afirmaciones=[{"id": "a1", "estado": "no_verificado", "fuentes": []}])
    assert any("no está confirmada" in e for e in pipeline.validar_guion(g, None))
