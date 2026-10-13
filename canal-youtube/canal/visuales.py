"""Consigue la imagen o el clip de cada plano: stock (Pexels, Pixabay), Wikimedia Commons, IA o rótulos.

Todo lo que se usa queda apuntado con su autor y licencia (créditos de la descripción).
Las búsquedas y descargas se guardan en caché para no gastar cuota ni ancho de banda.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import requests

from . import graficos, registro
from .config import CACHE, MEMORIA, RAIZ, clave
from .guion import Visual

LICENCIAS_LIBRES = ("public domain", "pd", "cc0", "cc by", "cc-by", "no restrictions", "attribution")


@dataclass
class Recurso:
    ruta: Path
    tipo: str            # "video" | "imagen"
    fuente: str
    id: str
    url: str = ""
    autor: str = ""
    licencia: str = ""
    atribucion: bool = False
    duracion: float = 0.0
    generado: bool = False
    ia: bool = False

    def credito(self) -> dict:
        d = asdict(self)
        d["ruta"] = str(self.ruta)
        return d


@dataclass
class _Candidato:
    id: str
    url_descarga: str
    tipo: str
    url: str
    autor: str
    licencia: str
    atribucion: bool = False
    duracion: float = 0.0
    ext: str = ".jpg"


def _ua(cfg: dict) -> str:
    contacto = cfg["canal"].get("contacto_api") or "uso personal"
    return f"CanalYouTube/1.0 ({contacto}) python-requests"


def _get_json(url: str, cfg: dict, params: dict, headers: dict | None = None, dias: int = 7) -> dict:
    """GET con caché en disco (las APIs de stock piden no repetir búsquedas)."""
    publico = {k: v for k, v in params.items() if k != "key"}
    h = hashlib.sha256(f"{url}|{json.dumps(publico, sort_keys=True)}".encode()).hexdigest()[:24]
    ruta = CACHE / "busquedas" / f"{h}.json"
    if ruta.exists() and time.time() - ruta.stat().st_mtime < dias * 86400:
        return json.loads(ruta.read_text(encoding="utf-8"))
    cab = {"User-Agent": _ua(cfg), **(headers or {})}
    for intento in range(6):
        r = requests.get(url, params=params, headers=cab, timeout=60)
        if r.status_code == 429 and intento < 5:
            time.sleep(_espera(r, intento))
            continue
        r.raise_for_status()
        break
    datos = r.json()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return datos


def _espera(r: requests.Response, intento: int) -> float:
    """Respeta Retry-After (Wikimedia limita a los programas por IP y agente)."""
    try:
        return min(90.0, float(r.headers.get("Retry-After", "")) + 1)
    except ValueError:
        return 4.0 * (intento + 1)


def _descargar(url: str, destino: Path, cfg: dict) -> Path:
    if destino.exists() and destino.stat().st_size > 0:
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(destino.suffix + ".parte")
    for intento in range(6):
        try:
            with requests.get(url, stream=True, timeout=120, headers={"User-Agent": _ua(cfg)}) as r:
                if r.status_code == 429 and intento < 5:
                    time.sleep(_espera(r, intento))
                    continue
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for trozo in r.iter_content(1 << 20):
                        f.write(trozo)
            tmp.rename(destino)
            return destino
        except requests.RequestException:
            if intento == 5:
                raise
            time.sleep(2 ** intento)
    raise RuntimeError(f"No pude descargar {url}")


# ------------------------------------------------------------------ proveedores

def _pexels_videos(q: str, orient: str, cfg: dict, tam) -> list[_Candidato]:
    k = clave("PEXELS_API_KEY", obligatoria=False)
    if not k:
        return []
    d = _get_json("https://api.pexels.com/videos/search", cfg,
                  {"query": q, "orientation": orient, "per_page": 15, "size": "medium"}, {"Authorization": k})
    return _filtrar_pexels_videos(d, orient, tam)


def _filtrar_pexels_videos(d: dict, orient: str, tam) -> list[_Candidato]:
    res = []
    for v in d.get("videos", []):
        archivos = [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("width")]
        if not archivos:
            continue
        lado = (lambda f: f["width"]) if orient == "landscape" else (lambda f: f["height"])
        objetivo = tam[0] if orient == "landscape" else tam[1]
        buenos = sorted([f for f in archivos if lado(f) >= objetivo * 0.9], key=lado)
        f = buenos[0] if buenos else max(archivos, key=lado)
        res.append(_Candidato(f"pexels-v{v['id']}", f["link"], "video", v.get("url", ""),
                              v.get("user", {}).get("name", ""), "Licencia de Pexels", False,
                              float(v.get("duration") or 0), ".mp4"))
    return res


def _pexels_fotos(q: str, orient: str, cfg: dict, tam) -> list[_Candidato]:
    k = clave("PEXELS_API_KEY", obligatoria=False)
    if not k:
        return []
    d = _get_json("https://api.pexels.com/v1/search", cfg, {"query": q, "orientation": orient, "per_page": 15},
                  {"Authorization": k})
    lado = "w" if orient == "landscape" else "h"
    return [_Candidato(f"pexels-f{p['id']}", f"{p['src']['original']}?auto=compress&cs=tinysrgb&{lado}=2400", "imagen",
                       p.get("url", ""), p.get("photographer", ""), "Licencia de Pexels") for p in d.get("photos", [])]


def _pixabay_videos(q: str, orient: str, cfg: dict, tam) -> list[_Candidato]:
    k = clave("PIXABAY_API_KEY", obligatoria=False)
    if not k:
        return []
    d = _get_json("https://pixabay.com/api/videos/", cfg, {"key": k, "q": q[:100], "per_page": 20, "safesearch": "true"})
    res = []
    for h in d.get("hits", []):
        vids = h.get("videos", {})
        f = vids.get("large") if vids.get("large", {}).get("url") else vids.get("medium")
        if not f or not f.get("url"):
            continue
        c = _Candidato(f"pixabay-v{h['id']}", f["url"], "video", h.get("pageURL", ""), h.get("user", ""),
                       "Licencia de Pixabay", False, float(h.get("duration") or 0), ".mp4")
        res.append((f.get("height", 0) > f.get("width", 1), c))
    # Pixabay no filtra vídeos por orientación: primero los que encajan sin recortar
    quiere_vertical = orient == "portrait"
    return [c for v, c in res if v == quiere_vertical] + [c for v, c in res if v != quiere_vertical]


def _pixabay_fotos(q: str, orient: str, cfg: dict, tam) -> list[_Candidato]:
    k = clave("PIXABAY_API_KEY", obligatoria=False)
    if not k:
        return []
    d = _get_json("https://pixabay.com/api/", cfg, {"key": k, "q": q[:100], "image_type": "photo", "per_page": 20,
                                                   "orientation": "horizontal" if orient == "landscape" else "vertical",
                                                   "safesearch": "true"})
    return [_Candidato(f"pixabay-f{h['id']}", h["largeImageURL"], "imagen", h.get("pageURL", ""), h.get("user", ""),
                       "Licencia de Pixabay") for h in d.get("hits", [])]


def _texto_plano(valor: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", valor or "")).strip()


ANCHOS_WIKIMEDIA = (1920, 1280, 960)  # Wikimedia solo sirve miniaturas de tamaños estándar


def _miniatura_wikimedia(ii: dict) -> str | None:
    """URL de una miniatura de tamaño estándar (los originales dan 429 a los programas)."""
    thumb = ii.get("thumburl", "")
    if "/thumb/" in thumb:
        return thumb.split("?")[0]
    ancho = int(ii.get("width") or 0)
    m = re.match(r"(https://upload\.wikimedia\.org/wikipedia/commons)/(\w/\w\w)/([^/?]+)", ii.get("url", ""))
    w = next((a for a in ANCHOS_WIKIMEDIA if a < ancho), None)
    if not m or not w:
        return None
    nombre = m[3]
    final = nombre if len(nombre) <= 160 else "thumbnail" + Path(nombre).suffix
    return f"{m[1]}/thumb/{m[2]}/{nombre}/{w}px-{final}"


def _wikimedia(q: str, orient: str, cfg: dict, tam, exacto: dict | None = None) -> list[_Candidato]:
    params = {"action": "query", "format": "json", "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata",
              "iiurlwidth": 1920, "iiextmetadatafilter": "LicenseShortName|Artist|AttributionRequired|Credit"}
    if exacto:
        params.update(exacto)
    elif re.match(r"^(File|Archivo|Fichero):", q, re.I):
        params["titles"] = "File:" + q.split(":", 1)[1].strip()
    else:
        params.update({"generator": "search", "gsrsearch": f"filetype:bitmap {q}", "gsrnamespace": 6, "gsrlimit": 25})
    d = _get_json("https://commons.wikimedia.org/w/api.php", cfg, params, dias=30)
    paginas = sorted(d.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    res = []
    for p in paginas:
        ii = (p.get("imageinfo") or [{}])[0]
        em = ii.get("extmetadata", {})
        lic = _texto_plano(em.get("LicenseShortName", {}).get("value", ""))
        if not lic or not lic.lower().startswith(LICENCIAS_LIBRES):
            continue
        if ii.get("mime") not in ("image/jpeg", "image/png", "image/webp"):
            continue
        lado_min = 900 if orient == "landscape" else 700
        if max(ii.get("width", 0), ii.get("height", 0)) < lado_min:
            continue
        atrib = em.get("AttributionRequired", {}).get("value", "false") == "true" or "by" in lic.lower()
        libre = lic.lower().startswith(("public domain", "pd", "cc0", "no restrictions"))
        url = _miniatura_wikimedia(ii)
        if not url:
            continue
        ext = ".png" if ii.get("mime") == "image/png" else ".jpg"
        if "pageid" not in p:
            continue
        res.append(_Candidato(f"wikimedia-{p['pageid']}", url, "imagen", ii.get("descriptionurl", ""),
                              _texto_plano(em.get("Artist", {}).get("value", ""))[:120], lic, atrib and not libre, ext=ext))
    # primero dominio público y CC0, luego CC BY
    return sorted(res, key=lambda c: c.atribucion)


def _por_id(ident: str, orient: str, cfg: dict, tam) -> tuple[str, list[_Candidato]]:
    """«id:pexels-v123», «id:pixabay-f456», «id:wikimedia-789»: un recurso concreto ya revisado."""
    m = re.fullmatch(r"(pexels|pixabay)-([vf])(\d+)|wikimedia-(\d+)", ident.strip())
    if not m:
        raise SystemExit(f"id de recurso no válido: {ident}")
    if m[4]:
        return "wikimedia", _wikimedia("", orient, cfg, tam, exacto={"pageids": m[4]})
    fuente, clase, num = m[1], m[2], m[3]
    if fuente == "pexels":
        k = clave("PEXELS_API_KEY")
        if clase == "v":
            v = _get_json(f"https://api.pexels.com/videos/videos/{num}", cfg, {}, {"Authorization": k}, dias=30)
            d = {"videos": [v]}
            return fuente, _filtrar_pexels_videos(d, orient, tam)
        f = _get_json(f"https://api.pexels.com/v1/photos/{num}", cfg, {}, {"Authorization": k}, dias=30)
        lado = "w" if orient == "landscape" else "h"
        return fuente, [_Candidato(f"pexels-f{f['id']}", f"{f['src']['original']}?auto=compress&cs=tinysrgb&{lado}=2400",
                                   "imagen", f.get("url", ""), f.get("photographer", ""), "Licencia de Pexels")]
    k = clave("PIXABAY_API_KEY")
    url = "https://pixabay.com/api/videos/" if clase == "v" else "https://pixabay.com/api/"
    d = _get_json(url, cfg, {"key": k, "id": num}, dias=1)
    if clase == "v":
        res = []
        for h in d.get("hits", []):
            f = h["videos"].get("large") if h["videos"].get("large", {}).get("url") else h["videos"].get("medium")
            res.append(_Candidato(f"pixabay-v{h['id']}", f["url"], "video", h.get("pageURL", ""), h.get("user", ""),
                                  "Licencia de Pixabay", False, float(h.get("duration") or 0), ".mp4"))
        return fuente, res
    return fuente, [_Candidato(f"pixabay-f{h['id']}", h["largeImageURL"], "imagen", h.get("pageURL", ""),
                               h.get("user", ""), "Licencia de Pixabay") for h in d.get("hits", [])]


PROVEEDORES = {
    "pexels": (_pexels_videos, _pexels_fotos),
    "pixabay": (_pixabay_videos, _pixabay_fotos),
    "wikimedia": (None, _wikimedia),
}


class Buscador:
    """Resuelve visuales para un vídeo concreto, sin repetir el mismo recurso dentro del vídeo."""

    def __init__(self, cfg: dict, tam: tuple[int, int]):
        self.cfg = cfg
        self.tam = tam
        self.orient = "portrait" if tam[1] > tam[0] else "landscape"
        self.usados: set[str] = set()
        self._fallidos: set[str] = set()
        self.recursos: list[Recurso] = []
        self.avisos: list[str] = []
        self._previos = self._usados_antes()

    @staticmethod
    def _usados_antes() -> set[str]:
        p = MEMORIA / "medios_usados.json"
        if not p.exists():
            return set()
        datos = json.loads(p.read_text(encoding="utf-8"))
        return {i for ids in list(datos.values())[-6:] for i in ids}  # últimos 6 vídeos

    def guardar_usados(self, video_id: str) -> None:
        p = MEMORIA / "medios_usados.json"
        datos = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        datos[video_id] = sorted(r.id for r in self.recursos if not r.generado)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")

    def _elegir(self, candidatos: list[_Candidato], duracion: float) -> _Candidato | None:
        libres = [c for c in candidatos if c.id not in self.usados]
        frescos = [c for c in libres if c.id not in self._previos] or libres
        if not frescos:
            # agotada la búsqueda: mejor repetir una imagen que encaja que poner un fondo vacío
            frescos = [c for c in candidatos if c.id not in self._fallidos]
            if not frescos:
                return None
        if duracion and frescos[0].tipo == "video":
            largos = [c for c in frescos if c.duracion >= duracion]
            if largos:
                return largos[0]
        return frescos[0]

    def _buscar(self, q: str, fuentes: list[str], video: bool, duracion: float) -> Recurso | None:
        for nombre in fuentes:
            pv, pf = PROVEEDORES.get(nombre, (None, None))
            for fn in ([pv] if video else []) + [pf]:
                if fn is None:
                    continue
                try:
                    cands = fn(q, self.orient, self.cfg, self.tam)
                except requests.RequestException as e:
                    self.avisos.append(f"{nombre}: error buscando «{q}»: {e}")
                    continue
                for _ in range(3):
                    c = self._elegir(cands, duracion)
                    if not c:
                        break
                    try:
                        return self._bajar(c, nombre)
                    except (requests.RequestException, RuntimeError) as e:
                        self.usados.add(c.id)
                        self._fallidos.add(c.id)
                        self.avisos.append(f"{nombre}: no pude descargar {c.id}: {str(e)[:120]}")
        return None

    def _bajar(self, c: _Candidato, fuente: str) -> Recurso:
        destino = CACHE / "medios" / fuente / f"{c.id}{c.ext}"
        if fuente == "wikimedia" and not destino.exists():
            time.sleep(0.4)  # norma de uso de Wikimedia: sin ráfagas
        _descargar(c.url_descarga, destino, self.cfg)
        self.usados.add(c.id)
        r = Recurso(destino, c.tipo, fuente, c.id, c.url, c.autor, c.licencia, c.atribucion, c.duracion)
        self.recursos.append(r)
        return r

    def _grafico(self, tipo: str, valor: str, extra: str | None) -> Recurso:
        ruta = graficos.generar(tipo, valor, extra, self.tam, self.cfg["estilo"])
        r = Recurso(ruta, "imagen", "rotulo", ruta.stem, generado=True)
        self.recursos.append(r)
        return r

    def _imagen_ia(self, prompt: str) -> Recurso | None:
        ia = self.cfg["visuales"]["ia"]
        if ia.get("proveedor") != "openai" or not clave("OPENAI_API_KEY", obligatoria=False):
            return None
        h = hashlib.sha256(f"{ia['modelo']}|{ia['calidad']}|{self.orient}|{prompt}".encode()).hexdigest()[:20]
        destino = CACHE / "medios" / "ia" / f"ia-{h}.png"
        if not destino.exists():
            coste = float(self.cfg["presupuesto"]["eur_por_imagen_ia"])
            registro.comprobar_gasto(self.cfg, coste, "imagen IA")
            tam = "1536x1024" if self.orient == "landscape" else "1024x1536"
            r = requests.post("https://api.openai.com/v1/images/generations", timeout=240,
                              headers={"Authorization": f"Bearer {clave('OPENAI_API_KEY')}"},
                              json={"model": ia["modelo"], "prompt": prompt, "size": tam, "quality": ia["calidad"], "n": 1})
            if r.status_code >= 400:
                self.avisos.append(f"imagen IA falló ({r.status_code}): {r.text[:200]}")
                return None
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(base64.b64decode(r.json()["data"][0]["b64_json"]))
            registro.apuntar_gasto(self.cfg, coste, f"imagen IA: {prompt[:60]}")
        rec = Recurso(destino, "imagen", "ia", destino.stem, licencia="Generada con IA", ia=True)
        self.recursos.append(rec)
        return rec

    def conseguir(self, v: Visual, duracion: float = 0.0) -> Recurso:
        stock = list(self.cfg["visuales"]["stock"])
        tipo, valor = v.tipo, v.valor
        r = None
        if tipo in ("tarjeta", "dato", "cita"):
            return self._grafico(tipo, valor, v.sub if tipo != "cita" else v.autor)
        if tipo in ("grafico", "mapa"):
            from .animados import guardar_spec

            ruta = guardar_spec(v, self.tam, self.cfg["estilo"])
            fuente = "Natural Earth" if tipo == "mapa" else "rotulo"
            r = Recurso(ruta, "animado", fuente, ruta.stem, generado=tipo == "grafico",
                        licencia="dominio público" if tipo == "mapa" else "")
            self.recursos.append(r)
            return r
        if tipo == "archivo":
            ruta = (RAIZ / valor) if not Path(valor).is_absolute() else Path(valor)
            if not ruta.exists():
                raise SystemExit(f"No existe el archivo del guion: {ruta}")
            es_video = ruta.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv")
            r = Recurso(ruta, "video" if es_video else "imagen", "propio", ruta.name, licencia="propia")
            self.recursos.append(r)
            return r
        if tipo in ("stock", "foto", "wikimedia") and valor.startswith("id:"):
            fuente, cands = _por_id(valor[3:], self.orient, self.cfg, self.tam)
            if not cands:
                raise SystemExit(f"El recurso fijado {valor} ya no está disponible; elige otro")
            self.usados.discard(cands[0].id)
            return self._bajar(cands[0], fuente)
        if tipo == "stock":
            r = self._buscar(valor, stock, video=True, duracion=duracion)
        elif tipo == "foto":
            r = self._buscar(valor, stock, video=False, duracion=0)
        elif tipo == "wikimedia":
            r = self._buscar(valor, ["wikimedia"] + [s for s in stock if s != "wikimedia"], video=False, duracion=0)
        elif tipo == "ia":
            r = self._imagen_ia(valor)
            if r is None:
                corto = " ".join(re.findall(r"[A-Za-zÀ-ÿ]+", valor)[:6])
                self.avisos.append(f"sin proveedor de imágenes IA; busco «{corto}» en stock")
                r = self._buscar(corto, stock, video=False, duracion=0)
        if r is None:
            self.avisos.append(f"sin resultados para {tipo} «{valor}»; uso un fondo de marca")
            ruta = CACHE / "graficos" / f"fondo-{hashlib.sha1(valor.encode()).hexdigest()[:10]}-{self.tam[0]}x{self.tam[1]}.png"
            if not ruta.exists():
                ruta.parent.mkdir(parents=True, exist_ok=True)
                graficos.fondo(int(self.tam[0] * 1.2), int(self.tam[1] * 1.2), self.cfg["estilo"],
                               int(hashlib.sha1(valor.encode()).hexdigest()[:6], 16)).save(ruta)
            r = Recurso(ruta, "imagen", "rotulo", ruta.stem, generado=True)
            self.recursos.append(r)
        return r
