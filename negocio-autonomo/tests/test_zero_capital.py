"""Arranque con 0 €: nada se gasta, nada se rompe, y aportar capital lo desbloquea."""
import pytest

from app import approvals, budget, settings_store
from app.actors import agent
from app.agents import director, operations, researcher
from app.core import bootstrap
from app.integrations.llm import FakeProvider, guarded_complete

from .fixtures import research_fixture


@pytest.fixture
def zero(settings):
    settings.initial_capital_eur = 0
    c = bootstrap(settings)
    yield c
    c.close()


def test_starts_with_zero_and_rejects_every_spend(zero, owner):
    bal = budget.balance(zero)
    assert bal["capital_cents"] == 0 and bal["available_cents"] == 0
    settings_store.set_value(zero, owner, "api_envelope_month_cents", "1000")  # ni con sobre de API
    for cat in ("api", "ads", "tool", "service"):
        r = budget.request_spend(zero, agent("director"), cat, 1, "x", f"z-{cat}")
        assert r["status"] == "rejected" and "sin capital" in r["reason"]
    assert approvals.pending(zero) == []


def test_llm_not_called_without_capital(zero, settings, owner):
    settings_store.set_value(zero, owner, "api_envelope_month_cents", "1000")
    fake = FakeProvider(lambda s, u: "x")
    with pytest.raises(budget.BudgetError, match="sin capital"):
        guarded_complete(zero, agent("investigador"), fake, settings, "s", "u", 100, "z")
    assert fake.calls == 0


def test_watch_does_not_trip_kill_switch_at_zero(zero):
    operations.watch(zero, agent("operaciones"))
    assert settings_store.get(zero, "kill_switch") == "off"


def test_free_workflow_still_runs_at_zero(zero):
    researcher.import_research(zero, agent("investigador"), research_fixture())
    out = director.cycle(zero, agent("director"))
    exp = zero.execute("SELECT max_budget_cents FROM experiments").fetchone()
    assert exp["max_budget_cents"] == 0 and any("propuesto" in a for a in out["actions"])


def test_add_capital_unlocks_spending_and_is_recorded(zero, owner, settings):
    bal = budget.add_capital(zero, owner, 30000, "aportación noviembre")
    assert bal["capital_cents"] == 30000 and bal["available_cents"] == 24000  # 20 % de suelo
    row = zero.execute("SELECT * FROM ledger WHERE kind='capital'").fetchone()
    assert row["amount_cents"] == 30000 and row["data_kind"] == "real"
    assert budget.request_spend(zero, agent("director"), "ads", 1000, "x", "after")["status"] == "pending"
    with pytest.raises(ValueError):  # el capital no se cambia por la vía genérica de ajustes
        settings_store.set_value(zero, owner, "capital_cents", "999999")
    zero.close()
    c2 = bootstrap(settings)  # reiniciar no vuelve a sumar capital inicial ni pierde la aportación
    assert budget.balance(c2)["capital_cents"] == 30000
    c2.close()
