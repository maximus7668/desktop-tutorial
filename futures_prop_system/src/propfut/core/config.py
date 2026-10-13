"""Configuración tipada del sistema (pydantic v2) cargada desde YAML.

Toda regla de la prop firm y todo límite interno vive aquí: el código nunca
debe contener umbrales de riesgo "mágicos".
"""

from __future__ import annotations

from datetime import time
from enum import Enum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from propfut.core.types import RunMode


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --------------------------------------------------------------------------- #
# Contratos
# --------------------------------------------------------------------------- #
class ExpiryRule(str, Enum):
    EQUITY_INDEX = "equity_index"  # 3er viernes del mes del contrato
    FX_IMM = "fx_imm"  # 2 días hábiles antes del 3er miércoles
    CRUDE_OIL = "crude_oil"  # 3 d.h. antes del día 25 del mes previo
    NATURAL_GAS = "natural_gas"  # 3 d.h. antes del 1er día del mes del contrato
    METALS = "metals"  # 3er último día hábil del mes del contrato
    TREASURY = "treasury"  # 7º d.h. antes del último d.h. del mes


class RollMethod(str, Enum):
    CALENDAR = "calendar"
    VOLUME = "volume"
    OPEN_INTEREST = "open_interest"


class RollConfig(_Strict):
    method: RollMethod = RollMethod.CALENDAR
    #: días hábiles antes de la fecha de referencia (expiración o first notice)
    days_before: int = Field(default=8, ge=0, le=30)
    #: en contratos con entrega física, usar first notice day como referencia
    use_first_notice: bool = True
    #: días consecutivos que el siguiente contrato debe superar al actual (volume/OI)
    confirm_days: int = Field(default=2, ge=1)
    #: ventana máxima (días hábiles antes de la referencia) en la que se permite rolar antes
    max_days_before: int = Field(default=15, ge=1)
    #: qué hacer con posiciones abiertas al rolar: cerrar o rolar al siguiente contrato
    position_policy: Literal["flatten", "roll"] = "flatten"


class SessionConfig(_Strict):
    timezone: str = "America/Chicago"
    eth_open: time = time(17, 0)  # apertura Globex (día de trading siguiente)
    eth_close: time = time(16, 0)
    rth_open: time = time(8, 30)
    rth_close: time = time(15, 0)


class ContractSpecConfig(_Strict):
    root: str
    name: str
    exchange: str
    asset_class: Literal["equity_index", "energy", "metals", "fx", "rates", "ags", "other"]
    multiplier: float = Field(gt=0)
    tick_size: float = Field(gt=0)
    tick_value: float = Field(gt=0)
    currency: str = "USD"
    months: str = Field(description="Códigos de meses listados, p.ej. 'HMUZ'")
    expiry_rule: ExpiryRule
    physical_delivery: bool = False
    session: SessionConfig = SessionConfig()
    roll: RollConfig = RollConfig()
    initial_margin: float = Field(ge=0, description="Margen de exchange (overnight) en USD")
    day_trade_margin: float = Field(ge=0, description="Margen intradía del broker en USD")
    commission_per_side: float = Field(default=2.5, ge=0)
    slippage_ticks: float = Field(default=1.0, ge=0, description="Slippage típico por lado")
    #: equivalencia en "minis" para límites de contratos de la prop firm (MES = 0.1)
    mini_equivalent: float = Field(default=1.0, gt=0)
    correlation_group: str = "default"

    @model_validator(mode="after")
    def _check_tick_value(self) -> "ContractSpecConfig":
        implied = self.multiplier * self.tick_size
        if abs(implied - self.tick_value) > 1e-6 * max(1.0, self.tick_value):
            raise ValueError(
                f"{self.root}: tick_value {self.tick_value} != multiplier*tick_size {implied}"
            )
        valid = set("FGHJKMNQUVXZ")
        if not self.months or set(self.months) - valid:
            raise ValueError(f"{self.root}: códigos de mes inválidos '{self.months}'")
        return self


# --------------------------------------------------------------------------- #
# Reglas de la prop firm (lo que dicta la firma) y límites internos (más estrictos)
# --------------------------------------------------------------------------- #
class TrailingMode(str, Enum):
    STATIC = "static"
    INTRADAY = "intraday"  # el umbral sigue al máximo de equity (incluye no realizado)
    END_OF_DAY = "end_of_day"  # el umbral sigue al balance de cierre diario


class PropFirmRules(_Strict):
    name: str
    account_size: float = Field(gt=0)
    profit_target: float = Field(ge=0)
    max_loss: float = Field(gt=0, description="Drawdown máximo (trailing o estático) en USD")
    trailing_mode: TrailingMode = TrailingMode.END_OF_DAY
    #: el umbral deja de subir al alcanzar este nivel de equity (p.ej. balance inicial)
    trailing_lock_level: float | None = None
    daily_loss_limit: float | None = Field(default=None, gt=0)
    #: "breach": romper el DLL suspende la cuenta; "pause": sólo bloquea el día
    daily_loss_mode: Literal["breach", "pause"] = "pause"
    max_contracts_mini_equiv: float = Field(gt=0, description="Máximo de contratos en minis")
    #: proporción máxima del beneficio total que puede venir del mejor día
    consistency_max_day_share: float | None = Field(default=None, gt=0, le=1)
    min_trading_days: int = Field(default=0, ge=0)
    timezone: str = "America/Chicago"
    day_reset_time: time = time(17, 0)
    flatten_time: time = time(15, 10)
    no_overnight: bool = True
    news_restricted: bool = False
    news_blackout_minutes_before: int = Field(default=2, ge=0)
    news_blackout_minutes_after: int = Field(default=2, ge=0)
    allowed_roots: list[str] = Field(default_factory=list)

    @property
    def initial_threshold(self) -> float:
        return self.account_size - self.max_loss


class DrawdownTier(_Strict):
    """Si la utilización del drawdown supera ``utilization``, multiplicar riesgo por ``risk_multiplier``."""

    utilization: float = Field(ge=0, le=1)
    risk_multiplier: float = Field(ge=0, le=1)


class InternalRiskConfig(_Strict):
    """Límites propios del sistema, SIEMPRE más estrictos que los de la firma."""

    max_risk_per_trade_usd: float = Field(gt=0)
    #: fracción máxima del colchón restante hasta el umbral trailing por operación
    max_risk_fraction_of_dd_room: float = Field(default=0.10, gt=0, le=0.5)
    #: fracción máxima del colchón diario restante por operación
    max_risk_fraction_of_daily_room: float = Field(default=0.35, gt=0, le=1)
    daily_loss_soft_stop_usd: float = Field(gt=0, description="Pérdida diaria que detiene nuevas entradas")
    daily_loss_flatten_usd: float = Field(gt=0, description="Pérdida diaria que obliga a cerrar todo")
    daily_profit_lock_usd: float | None = Field(default=None, gt=0)
    max_trades_per_day: int = Field(default=6, ge=1)
    max_consecutive_losses: int = Field(default=3, ge=1)
    cooldown_minutes_after_loss: int = Field(default=15, ge=0)
    max_open_positions: int = Field(default=2, ge=1)
    max_mini_equiv_contracts: float = Field(gt=0)
    max_contracts_per_root: dict[str, int] = Field(default_factory=dict)
    max_portfolio_risk_usd: float = Field(gt=0, description="Riesgo a stop agregado con correlaciones")
    max_margin_utilization: float = Field(default=0.5, gt=0, le=1)
    min_trailing_room_usd: float = Field(default=300.0, ge=0, description="Por debajo, se detiene el día")
    stop_slippage_buffer_ticks: int = Field(default=2, ge=0)
    min_stop_ticks: int = Field(default=4, ge=1)
    min_reward_risk: float = Field(default=1.2, gt=0)
    no_entry_minutes_before_flatten: int = Field(default=20, ge=0)
    no_entry_minutes_after_open: int = Field(default=5, ge=0, description="Evita el ruido de la apertura RTH")
    flatten_buffer_minutes: int = Field(default=3, ge=0)
    rth_only_entries: bool = True
    flatten_before_high_impact_news: bool = True
    news_blackout_minutes_before: int = Field(default=10, ge=0)
    news_blackout_minutes_after: int = Field(default=5, ge=0)
    drawdown_tiers: list[DrawdownTier] = Field(
        default_factory=lambda: [
            DrawdownTier(utilization=0.25, risk_multiplier=0.75),
            DrawdownTier(utilization=0.50, risk_multiplier=0.50),
            DrawdownTier(utilization=0.70, risk_multiplier=0.25),
        ]
    )
    correlations: dict[str, float] = Field(
        default_factory=dict, description="Pares 'ES-NQ': 0.9; dentro del mismo grupo por defecto 0.8"
    )
    same_group_default_correlation: float = Field(default=0.8, ge=-1, le=1)
    max_slippage_ticks_alert: float = Field(default=4.0, gt=0)

    @field_validator("drawdown_tiers")
    @classmethod
    def _sort_tiers(cls, v: list[DrawdownTier]) -> list[DrawdownTier]:
        return sorted(v, key=lambda t: t.utilization)

    @model_validator(mode="after")
    def _coherent(self) -> "InternalRiskConfig":
        if self.daily_loss_flatten_usd < self.daily_loss_soft_stop_usd:
            raise ValueError("daily_loss_flatten_usd debe ser >= daily_loss_soft_stop_usd")
        return self


# --------------------------------------------------------------------------- #
# Señales, régimen, política, ejecución
# --------------------------------------------------------------------------- #
class RegimeConfig(_Strict):
    er_window: int = 20
    trend_er_threshold: float = 0.35
    range_er_threshold: float = 0.25
    high_vol_percentile: float = 0.85
    squeeze_percentile: float = 0.15
    hysteresis_bars: int = 3
    use_hmm: bool = True
    hmm_states: int = 2
    risk_multipliers: dict[str, float] = Field(
        default_factory=lambda: {
            "TREND_UP": 1.0,
            "TREND_DOWN": 1.0,
            "RANGE": 0.8,
            "SQUEEZE": 0.7,
            "HIGH_VOL": 0.5,
            "NEWS_DRIVEN": 0.0,
            "UNKNOWN": 0.0,
        }
    )


class AgentConfig(_Strict):
    enabled: bool = True
    base_weight: float = Field(default=1.0, ge=0)
    params: dict[str, Any] = Field(default_factory=dict)


class EnsembleConfig(_Strict):
    min_confidence: float = Field(default=0.30, ge=0, le=1)
    min_agreement: float = Field(default=0.60, ge=0.5, le=1)
    exit_threshold: float = Field(default=0.35, ge=0, le=1)
    performance_halflife: int = Field(default=40, ge=1, description="En señales resueltas")
    performance_min_samples: int = Field(default=20, ge=1)
    performance_sensitivity: float = Field(default=1.5, ge=0)
    default_stop_atr: float = Field(default=1.5, gt=0)
    default_target_rr: float = Field(default=2.0, gt=0)


class PolicyConfig(_Strict):
    kind: Literal["heuristic", "rl"] = "heuristic"
    model_path: str | None = None
    min_size_fraction: float = Field(default=0.25, ge=0, le=1)
    breakeven_at_r: float = Field(default=1.0, gt=0)
    trail_after_r: float = Field(default=1.5, gt=0)
    trail_atr: float = Field(default=1.2, gt=0)
    max_holding_bars: int = Field(default=48, ge=1)


class ExecutionConfig(_Strict):
    mode: RunMode = RunMode.BACKTEST
    default_entry: Literal["market", "limit"] = "market"
    limit_offset_ticks: int = Field(default=1, ge=0)
    entry_timeout_bars: int = Field(default=3, ge=1)
    proposal_ttl_seconds: int = Field(default=120, ge=5)
    max_orders_per_minute: int = Field(default=10, ge=1)
    limit_requires_trade_through: bool = True
    max_participation_rate: float = Field(default=0.05, gt=0, le=1)


class MonitoringConfig(_Strict):
    log_dir: str = "logs"
    decision_log: bool = True
    state_file: str = "logs/state.json"
    dd_alert_levels: list[float] = Field(default_factory=lambda: [0.5, 0.75, 0.9])
    webhook_url: str | None = None


class SystemConfig(_Strict):
    account: PropFirmRules
    risk: InternalRiskConfig
    instruments: list[str] = Field(description="Raíces a operar (deben existir en la librería)")
    contract_library: dict[str, ContractSpecConfig] = Field(default_factory=dict)
    regime: RegimeConfig = RegimeConfig()
    agents: dict[str, AgentConfig] = Field(default_factory=dict)
    ensemble: EnsembleConfig = EnsembleConfig()
    policy: PolicyConfig = PolicyConfig()
    execution: ExecutionConfig = ExecutionConfig()
    monitoring: MonitoringConfig = MonitoringConfig()
    #: relaciones intermarket: raíz -> raíces de referencia
    intermarket: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate(self) -> "SystemConfig":
        missing = [r for r in self.instruments if r not in self.contract_library]
        if missing:
            raise ValueError(f"Instrumentos sin especificación de contrato: {missing}")
        if self.account.allowed_roots:
            forbidden = [r for r in self.instruments if r not in self.account.allowed_roots]
            if forbidden:
                raise ValueError(f"Instrumentos no permitidos por la prop firm: {forbidden}")
        r, a = self.risk, self.account
        if r.max_mini_equiv_contracts > a.max_contracts_mini_equiv:
            raise ValueError("risk.max_mini_equiv_contracts supera el límite de la prop firm")
        if a.daily_loss_limit is not None and r.daily_loss_flatten_usd >= a.daily_loss_limit:
            raise ValueError("risk.daily_loss_flatten_usd debe ser < daily_loss_limit de la firma")
        if r.daily_loss_flatten_usd >= a.max_loss:
            raise ValueError("risk.daily_loss_flatten_usd debe ser < max_loss de la firma")
        if r.max_risk_per_trade_usd >= r.daily_loss_soft_stop_usd:
            raise ValueError("max_risk_per_trade_usd debe ser < daily_loss_soft_stop_usd")
        return self

    def spec(self, root: str) -> ContractSpecConfig:
        return self.contract_library[root]


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: se esperaba un mapping YAML")
    return data


def load_contract_library(path: str | Path) -> dict[str, ContractSpecConfig]:
    raw = _read_yaml(Path(path))
    return {root: ContractSpecConfig(root=root, **spec) for root, spec in raw["contracts"].items()}


def load_config(path: str | Path, library_path: str | Path | None = None) -> SystemConfig:
    """Carga la configuración del sistema.

    Si el YAML contiene ``contract_library_file`` (relativo al propio YAML) o se
    pasa ``library_path``, se carga la librería de contratos desde allí; las
    entradas en ``contract_library`` del YAML principal la sobrescriben.
    """
    path = Path(path)
    raw = _read_yaml(path)
    lib_file = library_path or raw.pop("contract_library_file", None)
    library: dict[str, Any] = {}
    if lib_file is not None:
        lib_path = Path(lib_file)
        if not lib_path.is_absolute():
            lib_path = path.parent / lib_path
        library = {k: v.model_dump() for k, v in load_contract_library(lib_path).items()}
    for root, spec in (raw.pop("contract_library", None) or {}).items():
        library[root] = {**library.get(root, {}), **spec, "root": root}
    raw["contract_library"] = library
    return SystemConfig.model_validate(raw)
