"""Agente investigador: registra oportunidades con evidencias y fuentes.

Dos vías:
- import_research(): carga una investigación en JSON (hecha por el propietario, por otra sesión o por
  discover()). Valida el formato, limpia el texto y descarta lo que no tenga fuente válida.
- discover(): usa el modelo con la búsqueda web del servidor. Solo acepta evidencias cuya URL aparece
  en los resultados reales de búsqueda (no URLs inventadas por el modelo)."""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from .. import audit, memory, permissions
from ..actors import Actor
from ..config import Settings
from ..db import now_iso, transaction
from ..integrations.llm import LLMProvider, guarded_complete
from ..untrusted import clean, looks_like_injection, valid_public_url

AGENT = "investigador"


class EvidenceIn(BaseModel):
    url: str
    title: str = Field(min_length=3, max_length=300)
    publisher: str | None = None
    retrieved_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).date().isoformat())
    excerpt: str = Field(min_length=10, max_length=1500)
    kind: Literal["demand", "willingness_to_pay", "competition", "price", "pain", "regulation", "other"]
    reliability: Literal["high", "medium", "low"] = "medium"

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        if not valid_public_url(v):
            raise ValueError("URL no válida o no pública")
        return v


class Estimates(BaseModel):
    """Estimaciones (no datos medidos) del investigador. Escalas 0-5."""
    demand: int = Field(ge=0, le=5)
    willingness_to_pay: int = Field(ge=0, le=5)
    competition_intensity: int = Field(ge=0, le=5)
    build_cost_eur: float = Field(ge=0, le=100000)
    time_to_first_sale_days: int = Field(ge=1, le=3650)
    legal_risk: int = Field(ge=0, le=5)
    fit: int = Field(ge=0, le=5)


class OpportunityIn(BaseModel):
    title: str = Field(min_length=5, max_length=200)
    description: str = Field(min_length=20, max_length=3000)
    segment: str = Field(max_length=200)
    product_idea: str = Field(max_length=1000)
    price_hint_eur: float | None = Field(default=None, ge=0, le=10000)
    # Texto PÚBLICO para la página (beneficios para el cliente). La descripción es análisis interno.
    benefits: list[str] = Field(default_factory=list, max_length=6)
    estimates: Estimates
    evidence: list[EvidenceIn] = Field(min_length=1, max_length=30)


class ResearchIn(BaseModel):
    run_id: str = Field(min_length=3, max_length=100)
    method: str = Field(max_length=500)
    opportunities: list[OpportunityIn] = Field(min_length=1, max_length=20)


def import_research(conn: sqlite3.Connection, actor: Actor, data: dict, verified_urls: set[str] | None = None) -> dict:
    permissions.authorize(conn, actor, "research", "import", str(data.get("run_id", "")))
    research = ResearchIn.model_validate(data)
    created, skipped = [], []
    with transaction(conn):
        for opp in research.opportunities:
            dup = conn.execute("SELECT id FROM opportunities WHERE lower(title)=lower(?)", (clean(opp.title, 200),)).fetchone()
            if dup:
                skipped.append({"title": opp.title, "reason": f"ya existe (#{dup['id']})"})
                continue
            cur = conn.execute(
                "INSERT INTO opportunities (title, description, segment, product_idea, price_hint_cents, inputs,"
                " created_by, created_at, research_run) VALUES (?,?,?,?,?,?,?,?,?)",
                (clean(opp.title, 200), clean(opp.description, 3000), clean(opp.segment, 200),
                 clean(opp.product_idea, 1000),
                 None if opp.price_hint_eur is None else round(opp.price_hint_eur * 100),
                 json.dumps({**opp.estimates.model_dump(), "data_kind": "estimate",
                            "benefits": [clean(b, 200) for b in opp.benefits]}),
                 actor.label, now_iso(), research.run_id),
            )
            oid = cur.lastrowid
            for ev in opp.evidence:
                excerpt = clean(ev.excerpt, 1500)
                reliability = ev.reliability
                if looks_like_injection(excerpt) or looks_like_injection(ev.title):
                    reliability = "low"
                    excerpt = "[posible inyección de instrucciones; texto marcado como no fiable] " + excerpt
                conn.execute(
                    "INSERT INTO evidence (opportunity_id, url, title, publisher, retrieved_at, excerpt, kind,"
                    " reliability, verified) VALUES (?,?,?,?,?,?,?,?,?)",
                    (oid, ev.url, clean(ev.title, 300), clean(ev.publisher or "", 200), ev.retrieved_at, excerpt,
                     ev.kind, reliability, int(verified_urls is not None and ev.url in verified_urls)),
                )
            created.append(oid)
        audit.log(conn, actor, "research.import", research.run_id,
                  {"created": created, "skipped": skipped, "method": research.method})
    memory.remember(conn, actor, "research", f"Investigación {research.run_id}",
                    f"Método: {research.method}. Oportunidades creadas: {created}. Omitidas: {skipped}.",
                    research.run_id)
    return {"created": created, "skipped": skipped}


SYSTEM_PROMPT = """Eres el investigador de un pequeño negocio de productos digitales con 500 € de capital.
Busca en la web oportunidades de productos digitales que una sola persona pueda crear con poco dinero,
con señales reales de demanda y de disposición a pagar. Sé escéptico: separa hechos de suposiciones.
Usa solo información de las páginas que encuentres; cada evidencia debe citar la URL exacta de un resultado
de búsqueda. Responde SOLO con un objeto JSON con este formato:
{"run_id": "...", "method": "...", "opportunities": [{"title": "...", "description": "...", "segment": "...",
"product_idea": "...", "price_hint_eur": 19,
"benefits": ["beneficio para el cliente, sin afirmaciones no comprobadas"], "estimates": {"demand": 0-5, "willingness_to_pay": 0-5,
"competition_intensity": 0-5, "build_cost_eur": 0, "time_to_first_sale_days": 30, "legal_risk": 0-5, "fit": 0-5},
"evidence": [{"url": "...", "title": "...", "publisher": "...", "excerpt": "cita o resumen fiel",
"kind": "demand|willingness_to_pay|competition|price|pain|regulation|other", "reliability": "high|medium|low"}]}]}"""


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("la respuesta del modelo no contiene JSON")
    return json.loads(m.group(0))


def discover(conn: sqlite3.Connection, actor: Actor, provider: LLMProvider, settings: Settings,
             topic: str, run_id: str) -> dict:
    user = (f"Tema a investigar (dato del propietario): {clean(topic, 500)}\n"
            f"Usa run_id \"{run_id}\". Propón entre 2 y 5 oportunidades.")
    res = guarded_complete(conn, actor, provider, settings, SYSTEM_PROMPT, user, 8000, f"discover:{run_id}",
                           web_search=True)
    try:
        data = _extract_json(res.text)
        data["run_id"] = run_id
    except (ValueError, json.JSONDecodeError) as e:
        audit.log(conn, actor, "research.invalid_output", run_id, {"error": str(e)})
        raise
    verified = {s["url"] for s in res.sources}
    # Descarta evidencias con URL que no apareció en la búsqueda real.
    dropped = 0
    for opp in data.get("opportunities", []):
        before = len(opp.get("evidence", []))
        opp["evidence"] = [e for e in opp.get("evidence", []) if e.get("url") in verified]
        dropped += before - len(opp["evidence"])
    data["opportunities"] = [o for o in data.get("opportunities", []) if o.get("evidence")]
    if not data["opportunities"]:
        raise ValueError("ninguna oportunidad con evidencias verificables")
    try:
        out = import_research(conn, actor, data, verified_urls=verified)
    except ValidationError as e:
        audit.log(conn, actor, "research.invalid_output", run_id, {"error": str(e)[:500]})
        raise
    out["dropped_unverified_evidence"] = dropped
    out["data_kind"] = res.data_kind
    return out
