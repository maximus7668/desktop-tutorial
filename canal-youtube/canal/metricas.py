"""Lee cómo van los vídeos y lo deja escrito para que el agente aprenda (memoria/metricas.md).

- YouTube Analytics API: vistas, minutos vistos, retención media y curva de retención.
- YouTube Reporting API: impresiones y CTR de la miniatura (informe channel_reach_basic_a1,
  llega con 48-72 h de retraso; hay que crear el trabajo una vez con --crear-informe).
"""
from __future__ import annotations

import csv
import io
import json
from datetime import date, timedelta
from pathlib import Path

from .config import MEMORIA, SALIDA

METRICAS = ("views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained,"
            "likes,comments,shares")
INFORME_CTR = "channel_reach_basic_a1"


def _youtube_ids() -> dict[str, tuple[str, str]]:
    """youtube_id → (id local, pieza)."""
    p = MEMORIA / "publicados.json"
    res = {}
    if p.exists():
        for local, v in json.loads(p.read_text(encoding="utf-8")).items():
            if v.get("largo"):
                res[v["largo"]["youtube_id"]] = (local, "largo")
            for sid, s in v.get("shorts", {}).items():
                res[s["youtube_id"]] = (local, sid)
    return res


def por_video(dias: int = 28) -> list[dict]:
    from .youtube import servicio

    yta = servicio("youtubeAnalytics", "v2")
    fin = date.today()
    ini = fin - timedelta(days=dias)
    r = yta.reports().query(ids="channel==MINE", startDate=ini.isoformat(), endDate=fin.isoformat(),
                            metrics=METRICAS, dimensions="video", sort="-views", maxResults=200).execute()
    cols = [c["name"] for c in r.get("columnHeaders", [])]
    return [dict(zip(cols, fila)) for fila in r.get("rows", [])]


def retencion(youtube_id: str, dias: int = 90) -> list[tuple[float, float, float]]:
    """Curva (posición 0-1, % de espectadores que siguen, rendimiento relativo frente a vídeos similares)."""
    from .youtube import servicio

    yta = servicio("youtubeAnalytics", "v2")
    fin = date.today()
    r = yta.reports().query(ids="channel==MINE", startDate=(fin - timedelta(days=dias)).isoformat(),
                            endDate=fin.isoformat(), metrics="audienceWatchRatio,relativeRetentionPerformance",
                            dimensions="elapsedVideoTimeRatio", filters=f"video=={youtube_id}").execute()
    return [(float(a), float(b), float(c)) for a, b, c in r.get("rows", [])]


def caidas(curva: list[tuple[float, float, float]], duracion: float, linea: list[dict], n: int = 3) -> list[dict]:
    """Los tramos donde más gente se va, con la frase que sonaba en ese momento."""
    saltos = []
    for (x0, y0, _), (x1, y1, _) in zip(curva, curva[1:]):
        saltos.append((y0 - y1, x0 * duracion))
    saltos.sort(reverse=True)
    res = []
    for perdida, t in saltos[:n]:
        frase = " ".join(p["texto"] for p in linea if t - 4 <= p["ini"] <= t + 4)
        res.append({"segundo": round(t), "perdida_pct": round(perdida * 100, 1), "frase": frase[:220]})
    return res


def crear_informe() -> str:
    from .youtube import servicio

    rep = servicio("youtubereporting", "v1")
    trabajos = rep.jobs().list().execute().get("jobs", [])
    for t in trabajos:
        if t.get("reportTypeId") == INFORME_CTR:
            return t["id"]
    t = rep.jobs().create(body={"reportTypeId": INFORME_CTR, "name": "canal-ctr"}).execute()
    return t["id"]


def ctr_por_video() -> dict[str, dict]:
    """Suma impresiones y clics de miniatura de todos los informes diarios disponibles."""
    from googleapiclient.http import MediaIoBaseDownload

    from .youtube import servicio

    rep = servicio("youtubereporting", "v1")
    trabajo = next((t for t in rep.jobs().list().execute().get("jobs", []) if t.get("reportTypeId") == INFORME_CTR), None)
    if not trabajo:
        return {}
    informes = rep.jobs().reports().list(jobId=trabajo["id"]).execute().get("reports", [])
    total: dict[str, dict] = {}
    for inf in informes[:60]:
        buf = io.BytesIO()
        peticion = rep.media().download(resourceName=" ")
        peticion.uri = inf["downloadUrl"]  # así lo hace el ejemplo oficial de la Reporting API
        bajada = MediaIoBaseDownload(buf, peticion, chunksize=-1)
        hecho = False
        while not hecho:
            _, hecho = bajada.next_chunk()
        for fila in csv.DictReader(io.StringIO(buf.getvalue().decode("utf-8"))):
            v = fila.get("video_id")
            imp = float(fila.get("video_thumbnail_impressions") or 0)
            ctr = float(fila.get("video_thumbnail_impressions_ctr") or 0)
            d = total.setdefault(v, {"impresiones": 0.0, "clics": 0.0})
            d["impresiones"] += imp
            d["clics"] += imp * ctr
    for d in total.values():
        d["ctr_pct"] = round(100 * d["clics"] / d["impresiones"], 2) if d["impresiones"] else None
    return total


def resumen(dias: int = 28, con_ctr: bool = True) -> Path:
    ids = _youtube_ids()
    filas = por_video(dias)
    ctr = {}
    if con_ctr:
        try:
            ctr = ctr_por_video()
        except Exception as e:  # el informe tarda días en existir
            print(f"(CTR aún no disponible: {e})")
    datos = []
    for f in filas:
        local, pieza = ids.get(f["video"], ("(no hecho por el agente)", "-"))
        d = {"youtube_id": f["video"], "local": local, "pieza": pieza, **f, **ctr.get(f["video"], {})}
        if pieza == "largo":
            linea_p = SALIDA / local / "linea-largo.json"
            if linea_p.exists():
                try:
                    linea = json.loads(linea_p.read_text(encoding="utf-8"))
                    curva = retencion(f["video"])
                    d["caidas"] = caidas(curva, linea["duracion"], linea["palabras"])
                except Exception as e:
                    d["caidas_error"] = str(e)
        datos.append(d)
    MEMORIA.mkdir(parents=True, exist_ok=True)
    (MEMORIA / "metricas.json").write_text(json.dumps({"dias": dias, "fecha": date.today().isoformat(), "videos": datos},
                                                      ensure_ascii=False, indent=1), encoding="utf-8")
    lineas = [f"# Métricas · últimos {dias} días ({date.today().isoformat()})", "",
              "| Vídeo | Pieza | Vistas | Min. vistos | % visto | Subs | CTR % |", "|---|---|---:|---:|---:|---:|---:|"]
    for d in datos:
        lineas.append(f"| {d['local']} | {d['pieza']} | {int(d['views'])} | {int(d['estimatedMinutesWatched'])} | "
                      f"{float(d['averageViewPercentage']):.0f} | {int(d['subscribersGained'])} | {d.get('ctr_pct') or '—'} |")
    for d in datos:
        for c in d.get("caidas", []):
            lineas.append(f"- **{d['local']}** pierde {c['perdida_pct']} % en el segundo {c['segundo']}: «{c['frase']}»")
    ruta = MEMORIA / "metricas.md"
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return ruta
