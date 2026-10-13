"""Agentes de señal y registro configurable."""

from __future__ import annotations

from propfut.agents.base import Agent, AgentSignal, MarketContext
from propfut.agents.ensemble import DynamicEnsemble, EnsembleDecision
from propfut.agents.macro import IntermarketAgent, MacroNewsAgent
from propfut.agents.microstructure import AuctionAgent, OrderFlowAgent
from propfut.agents.technical import (
    MeanReversionAgent,
    TrendMomentumAgent,
    VolatilityExpansionAgent,
)
from propfut.core.config import SystemConfig

AGENT_REGISTRY: dict[str, type[Agent]] = {
    cls.name: cls
    for cls in (
        TrendMomentumAgent, MeanReversionAgent, VolatilityExpansionAgent,
        OrderFlowAgent, AuctionAgent, MacroNewsAgent, IntermarketAgent,
    )
}


def build_agents(cfg: SystemConfig, root: str) -> list[Agent]:
    """Instancia los agentes habilitados para ``root`` (todos si no hay sección ``agents``)."""
    agents: list[Agent] = []
    for name, cls in AGENT_REGISTRY.items():
        acfg = cfg.agents.get(name)
        if acfg is not None and not acfg.enabled:
            continue
        params = dict(acfg.params) if acfg else {}
        if cls is IntermarketAgent:
            agents.append(IntermarketAgent(params, references=cfg.intermarket.get(root, [])))
        else:
            agents.append(cls(params))
    return agents


def base_weights(cfg: SystemConfig) -> dict[str, float]:
    return {name: a.base_weight for name, a in cfg.agents.items()}


__all__ = [
    "AGENT_REGISTRY", "Agent", "AgentSignal", "MarketContext", "DynamicEnsemble", "EnsembleDecision",
    "build_agents", "base_weights",
]
