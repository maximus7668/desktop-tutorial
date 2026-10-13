"""Registro de acciones y control de gasto. Los límites están aquí, no solo en las instrucciones."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import MEMORIA


def _ahora() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def accion(que: str, **datos) -> None:
    """Apunta qué se hizo, cuándo y con qué datos en memoria/registro.jsonl."""
    MEMORIA.mkdir(parents=True, exist_ok=True)
    with open(MEMORIA / "registro.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"cuando": _ahora(), "que": que, **datos}, ensure_ascii=False) + "\n")


def _gastos_path() -> Path:
    return MEMORIA / "gastos.json"


def _gastos() -> dict:
    p = _gastos_path()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def gasto_mes(mes: str | None = None) -> float:
    mes = mes or datetime.now().strftime("%Y-%m")
    return round(sum(x["eur"] for x in _gastos().get(mes, [])), 4)


def comprobar_gasto(cfg: dict, coste: float, concepto: str) -> None:
    if coste <= 0:
        return
    tope = float(cfg["presupuesto"]["mensual_eur"])
    actual = gasto_mes()
    if actual + coste > tope:
        raise SystemExit(
            f"Parado: {concepto} costaría {coste:.2f} € y este mes ya van {actual:.2f} € de {tope:.2f} €. "
            f"Sube presupuesto.mensual_eur en canal.yaml solo con el ok del dueño."
        )


def apuntar_gasto(cfg: dict, coste: float, concepto: str) -> None:
    mes = datetime.now().strftime("%Y-%m")
    g = _gastos()
    g.setdefault(mes, []).append({"cuando": _ahora(), "eur": round(coste, 4), "concepto": concepto})
    MEMORIA.mkdir(parents=True, exist_ok=True)
    _gastos_path().write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding="utf-8")
