"""Proveedor de modelos configurable (LLM_PROVIDER) y llamada protegida por permisos y presupuesto."""
from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from .. import budget, permissions, settings_store
from ..actors import Actor
from ..config import Settings
from ..db import now_iso, transaction
from . import IntegrationError, IntegrationInfo, IntegrationNotConfigured

WEB_SEARCH_USD_PER_SEARCH = 0.01  # 10 $ por 1.000 búsquedas (comprobar precio vigente)
WEB_SEARCH_MAX_USES = 5


@dataclass
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    data_kind: str  # real | simulation
    web_searches: int = 0
    sources: list[dict] = field(default_factory=list)  # URLs devueltas por la búsqueda real


class LLMProvider:
    name = "none"
    data_kind = "real"

    def info(self) -> IntegrationInfo:
        return IntegrationInfo("llm", False, "llm.complete",
                               "Sin proveedor de modelos. Define LLM_PROVIDER=anthropic y ANTHROPIC_API_KEY.")

    def complete(self, system: str, user: str, max_tokens: int, web_search: bool = False) -> LLMResult:
        raise IntegrationNotConfigured(self.info().setup)


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, model: str):
        import anthropic  # dependencia opcional

        self._anthropic = anthropic
        self.client = anthropic.Anthropic(max_retries=2, timeout=300.0)
        self.model = model

    def info(self) -> IntegrationInfo:
        return IntegrationInfo("llm", True, "llm.complete, web.search (búsqueda del servidor de Anthropic)",
                               f"Anthropic Messages API, modelo {self.model}")

    def complete(self, system: str, user: str, max_tokens: int, web_search: bool = False) -> LLMResult:
        a = self._anthropic
        tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": WEB_SEARCH_MAX_USES}] if web_search else []
        messages: list = [{"role": "user", "content": user}]
        text_parts: list[str] = []
        sources: list[dict] = []
        tin = tout = searches = 0
        try:
            for _ in range(4):  # pause_turn: la búsqueda del servidor puede pedir continuar
                kwargs = dict(model=self.model, max_tokens=max_tokens, system=system, messages=messages,
                              output_config={"effort": "medium"},
                              betas=["server-side-fallback-2026-07-01"], fallbacks="default")
                if tools:
                    kwargs["tools"] = tools
                resp = self.client.beta.messages.create(**kwargs)
                tin += resp.usage.input_tokens
                tout += resp.usage.output_tokens
                stu = getattr(resp.usage, "server_tool_use", None)
                searches += getattr(stu, "web_search_requests", 0) or 0
                if resp.stop_reason == "refusal":
                    raise IntegrationError("el modelo rechazó la petición (refusal)")
                for block in resp.content:
                    if block.type == "text":
                        text_parts.append(block.text)
                    elif block.type == "web_search_tool_result" and isinstance(block.content, list):
                        for r in block.content:
                            sources.append({"url": r.url, "title": r.title, "page_age": r.page_age})
                if resp.stop_reason != "pause_turn":
                    break
                messages = [{"role": "user", "content": user}, {"role": "assistant", "content": resp.content}]
        except a.APIStatusError as e:
            raise IntegrationError(f"error de API de Anthropic: HTTP {e.status_code}") from e
        except a.APIConnectionError as e:
            raise IntegrationError("no se pudo conectar con la API de Anthropic") from e
        if not text_parts:
            raise IntegrationError("respuesta vacía del modelo")
        return LLMResult("".join(text_parts), tin, tout, self.model, "real", searches, sources)


class GeminiProvider(LLMProvider):
    """Gemini por su API REST con el nivel gratuito de Google AI Studio (GEMINI_API_KEY). En el nivel
    gratuito Google puede usar las peticiones para mejorar sus productos: no mandar datos personales."""
    name = "gemini"
    free = True
    API = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, model: str):
        import os

        self.key = os.environ.get("GEMINI_API_KEY", "").strip()
        self.model = model if model.startswith("gemini") else "gemini-2.5-flash"

    def info(self) -> IntegrationInfo:
        if not self.key:
            return IntegrationInfo("llm", False, "llm.complete",
                                   "Falta GEMINI_API_KEY (gratis en aistudio.google.com → Get API key)")
        return IntegrationInfo("llm", True, "llm.complete, web.search (Google Search de Gemini)",
                               f"Gemini API (nivel gratuito), modelo {self.model}")

    def complete(self, system: str, user: str, max_tokens: int, web_search: bool = False) -> LLMResult:
        import json
        import urllib.error
        import urllib.request

        body: dict = {"system_instruction": {"parts": [{"text": system}]},
                      "contents": [{"role": "user", "parts": [{"text": user}]}],
                      "generationConfig": {"maxOutputTokens": max_tokens}}
        if web_search:
            body["tools"] = [{"google_search": {}}]
        req = urllib.request.Request(f"{self.API}/{self.model}:generateContent", data=json.dumps(body).encode(),
                                     headers={"x-goog-api-key": self.key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise IntegrationError(f"error de API de Gemini: HTTP {e.code}") from e
        except urllib.error.URLError as e:
            raise IntegrationError("no se pudo conectar con la API de Gemini") from e
        cand = (data.get("candidates") or [{}])[0]
        text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
        if not text:
            raise IntegrationError(f"respuesta vacía de Gemini ({cand.get('finishReason', 'sin motivo')})")
        meta = cand.get("groundingMetadata") or {}
        sources = [{"url": c["web"].get("uri"), "title": c["web"].get("title"), "page_age": None}
                   for c in meta.get("groundingChunks", []) if c.get("web")]
        usage = data.get("usageMetadata", {})
        return LLMResult(text, usage.get("promptTokenCount", 0), usage.get("candidatesTokenCount", 0), self.model,
                         "real", len(meta.get("webSearchQueries", [])), sources)


class FakeProvider(LLMProvider):
    """Solo para pruebas. Sus resultados se marcan como simulación."""
    name = "fake"
    data_kind = "simulation"

    def __init__(self, responder: Callable[[str, str], str] | None = None, fail: Exception | None = None,
                 sources: list[dict] | None = None):
        self.responder = responder or (lambda s, u: "{}")
        self.fail = fail
        self.sources = sources or []
        self.calls = 0

    def info(self) -> IntegrationInfo:
        return IntegrationInfo("llm", True, "llm.complete (simulado)", "Proveedor simulado para pruebas")

    def complete(self, system: str, user: str, max_tokens: int, web_search: bool = False) -> LLMResult:
        self.calls += 1
        if self.fail:
            raise self.fail
        return LLMResult(self.responder(system, user), 100, 200, "fake", "simulation",
                         1 if web_search else 0, list(self.sources))


def build_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "anthropic":
        return AnthropicProvider(settings.llm_model)
    if settings.llm_provider == "gemini":
        return GeminiProvider(settings.llm_model)
    if settings.llm_provider == "fake":
        return FakeProvider()
    return LLMProvider()


def _cost_cents(settings: Settings, tin: int, tout: int, searches: int) -> int:
    usd = (tin * settings.llm_price_in_usd_mtok + tout * settings.llm_price_out_usd_mtok) / 1e6
    usd += searches * WEB_SEARCH_USD_PER_SEARCH
    return max(1, math.ceil(usd * settings.usd_to_eur * 100))


def guarded_complete(conn: sqlite3.Connection, actor: Actor, provider: LLMProvider, settings: Settings,
                     system: str, user: str, max_tokens: int, idempotency_key: str,
                     web_search: bool = False) -> LLMResult:
    """Llama al modelo solo si: hay permiso, no se supera el límite de llamadas, y el gasto estimado
    cabe en el sobre de API preautorizado (o lo aprobó una persona). Registra el coste real estimado."""
    if not provider.info().configured:
        raise IntegrationNotConfigured(provider.info().setup)
    permissions.authorize(conn, actor, "llm", "complete", idempotency_key)
    if web_search:
        permissions.authorize(conn, actor, "web", "search", idempotency_key)
    day = datetime.now(timezone.utc).date().isoformat()
    calls = conn.execute("SELECT COUNT(*) c FROM llm_usage WHERE agent=? AND ts >= ?", (actor.name, day)).fetchone()["c"]
    if calls >= settings_store.get_int(conn, "llm_max_calls_per_agent_day"):
        raise budget.BudgetError("límite diario de llamadas al modelo alcanzado")

    if getattr(provider, "free", False):
        # Nivel gratuito: no hay gasto que reservar; se registra el uso a 0 céntimos.
        res = provider.complete(system, user, max_tokens, web_search)
        with transaction(conn):
            conn.execute(
                "INSERT INTO llm_usage (ts, agent, provider, model, input_tokens, output_tokens, cost_cents, data_kind)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (now_iso(), actor.name, provider.name, res.model, res.input_tokens, res.output_tokens, 0, res.data_kind),
            )
        return res

    # Reserva prudente: los resultados de búsqueda entran como tokens de entrada (decenas de miles).
    est_in = (len(system) + len(user)) // 3 + 500 + (60000 if web_search else 0)
    est_searches = WEB_SEARCH_MAX_USES if web_search else 0
    estimate = _cost_cents(settings, est_in, max_tokens, est_searches)
    sr = budget.request_spend(conn, actor, "api", estimate, f"LLM {provider.name}: {idempotency_key}",
                              f"llm:{idempotency_key}")
    if sr["status"] == "rejected":
        raise budget.BudgetError(sr["reason"])
    if sr["status"] == "pending":
        raise budget.BudgetError("gasto de API pendiente de aprobación humana (sin sobre preautorizado)")
    if sr["status"] == "executed":
        raise budget.BudgetError("esta llamada ya se ejecutó (idempotencia); no se repite")

    holder: dict = {}

    def run(max_cents: int) -> tuple[int, str]:
        res = provider.complete(system, user, max_tokens, web_search)
        holder["res"] = res
        cost = _cost_cents(settings, res.input_tokens, res.output_tokens, res.web_searches)
        return cost, ("estimate" if res.data_kind == "real" else "simulation")

    done = budget.execute(conn, actor, sr["id"], run)
    res: LLMResult = holder["res"]
    with transaction(conn):
        conn.execute(
            "INSERT INTO llm_usage (ts, agent, provider, model, input_tokens, output_tokens, cost_cents, data_kind)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (now_iso(), actor.name, provider.name, res.model, res.input_tokens, res.output_tokens,
             done["actual_cents"], res.data_kind),
        )
    return res
