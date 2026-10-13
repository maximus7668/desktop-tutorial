"""Especificación de contratos: multiplicador, tick, valor del tick, márgenes.

Toda conversión precio <-> dinero del sistema pasa por :class:`ContractSpec`
para evitar errores de escala (el error más caro en futuros).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date

from propfut.core.config import ContractSpecConfig

MONTH_CODES: dict[int, str] = {
    1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M",
    7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z",
}
CODE_TO_MONTH: dict[str, int] = {v: k for k, v in MONTH_CODES.items()}

_SYMBOL_RE = re.compile(r"^(?P<root>[A-Z0-9]+?)(?P<code>[FGHJKMNQUVXZ])(?P<year>\d{1,4})$")


@dataclass(frozen=True, slots=True, order=True)
class ContractId:
    """Identificador de un contrato concreto (raíz + año + mes)."""

    year: int
    month: int
    root: str

    @property
    def code(self) -> str:
        return MONTH_CODES[self.month]

    @property
    def symbol(self) -> str:
        """Formato 'ESZ26' (año a 2 dígitos)."""
        return f"{self.root}{self.code}{self.year % 100:02d}"

    @property
    def first_day(self) -> date:
        return date(self.year, self.month, 1)

    @classmethod
    def parse(cls, symbol: str, roots: set[str] | None = None, ref_year: int = 2000) -> "ContractId":
        """Parsea 'ESZ26', 'ESZ2026' o 'ESZ6'. ``roots`` desambigua raíces con dígitos (p.ej. 6E)."""
        symbol = symbol.upper().strip()
        if roots:
            for r in sorted(roots, key=len, reverse=True):
                rest = symbol[len(r):]
                if symbol.startswith(r) and rest and rest[0] in CODE_TO_MONTH and rest[1:].isdigit():
                    return cls._build(r, rest[0], rest[1:], ref_year)
        m = _SYMBOL_RE.match(symbol)
        if not m:
            raise ValueError(f"Símbolo de contrato no reconocido: {symbol}")
        return cls._build(m["root"], m["code"], m["year"], ref_year)

    @classmethod
    def _build(cls, root: str, code: str, year_s: str, ref_year: int) -> "ContractId":
        y = int(year_s)
        if len(year_s) == 1:
            decade = ref_year - ref_year % 10
            y = decade + y if decade + y >= ref_year - 2 else decade + 10 + y
        elif len(year_s) == 2:
            y = 2000 + y
        return cls(year=y, month=CODE_TO_MONTH[code], root=root)

    def __str__(self) -> str:
        return self.symbol


@dataclass(frozen=True, slots=True)
class ContractSpec:
    """Vista inmutable y con lógica de una :class:`ContractSpecConfig`."""

    cfg: ContractSpecConfig

    # --- atajos -----------------------------------------------------------
    @property
    def root(self) -> str:
        return self.cfg.root

    @property
    def multiplier(self) -> float:
        return self.cfg.multiplier

    @property
    def tick_size(self) -> float:
        return self.cfg.tick_size

    @property
    def tick_value(self) -> float:
        return self.cfg.tick_value

    @property
    def listed_months(self) -> list[int]:
        return sorted(CODE_TO_MONTH[c] for c in self.cfg.months)

    # --- precio -----------------------------------------------------------
    def round_price(self, price: float, mode: str = "nearest") -> float:
        """Redondea a múltiplo del tick. ``mode``: 'nearest' | 'up' | 'down'."""
        q = price / self.tick_size
        eps = 1e-9
        if mode == "nearest":
            n = math.floor(q + 0.5)
        elif mode == "up":
            n = math.ceil(q - eps)
        elif mode == "down":
            n = math.floor(q + eps)
        else:
            raise ValueError(mode)
        # repetir el redondeo a decimales evita artefactos binarios (p.ej. 0.30000000004)
        decimals = max(0, -int(math.floor(math.log10(self.tick_size))) + 2)
        return round(n * self.tick_size, decimals)

    def round_stop(self, price: float, is_long: bool) -> float:
        """Redondeo conservador de un stop: hacia fuera (más lejos de la entrada)."""
        return self.round_price(price, "down" if is_long else "up")

    def is_tick_aligned(self, price: float) -> bool:
        return abs(self.round_price(price) - price) < self.tick_size * 1e-6

    def ticks(self, price_diff: float) -> float:
        return price_diff / self.tick_size

    # --- dinero -----------------------------------------------------------
    def points_to_usd(self, points: float, qty: float = 1.0) -> float:
        return points * self.multiplier * qty

    def ticks_to_usd(self, n_ticks: float, qty: float = 1.0) -> float:
        return n_ticks * self.tick_value * qty

    def pnl(self, entry: float, exit_: float, signed_qty: float) -> float:
        """PnL bruto en USD; ``signed_qty`` positivo = largo."""
        return (exit_ - entry) * signed_qty * self.multiplier

    def notional(self, price: float, qty: float = 1.0) -> float:
        return abs(price * self.multiplier * qty)

    def round_trip_cost(self, qty: float = 1.0) -> float:
        """Comisiones + slippage típico ida y vuelta."""
        return qty * (2 * self.cfg.commission_per_side + 2 * self.cfg.slippage_ticks * self.tick_value)

    def mini_equivalent(self, qty: float) -> float:
        return abs(qty) * self.cfg.mini_equivalent

    def margin(self, qty: float, intraday: bool = True) -> float:
        per = self.cfg.day_trade_margin if intraday else self.cfg.initial_margin
        return abs(qty) * per
