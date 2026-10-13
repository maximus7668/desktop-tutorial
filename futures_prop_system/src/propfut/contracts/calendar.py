"""Calendario de contratos: último día de negociación, first notice day y fecha de roll.

Las reglas reproducen las especificaciones de CME/NYMEX/COMEX. Los festivos se
pasan explícitamente (``holidays``); sin ellos se asume lunes-viernes hábiles.
**Verifica siempre** contra el calendario oficial del exchange antes de operar
en real: las reglas cambian y existen excepciones puntuales.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from propfut.contracts.specs import ContractId, ContractSpec
from propfut.core.config import ExpiryRule


class BusinessCalendar:
    def __init__(self, holidays: Iterable[date] = ()) -> None:
        self.holidays = frozenset(holidays)

    def is_business_day(self, d: date) -> bool:
        return d.weekday() < 5 and d not in self.holidays

    def shift(self, d: date, n: int) -> date:
        """Desplaza ``n`` días hábiles (negativo = hacia atrás). ``n=0`` devuelve ``d``."""
        step = 1 if n >= 0 else -1
        remaining = abs(n)
        while remaining > 0:
            d += timedelta(days=step)
            if self.is_business_day(d):
                remaining -= 1
        return d

    def previous_or_same(self, d: date) -> date:
        while not self.is_business_day(d):
            d -= timedelta(days=1)
        return d

    def last_business_day(self, year: int, month: int) -> date:
        nxt = date(year + (month == 12), month % 12 + 1, 1)
        return self.previous_or_same(nxt - timedelta(days=1))

    def business_days_between(self, start: date, end: date) -> int:
        """Días hábiles en (start, end]; negativo si end < start."""
        if end < start:
            return -self.business_days_between(end, start)
        n, d = 0, start
        while d < end:
            d += timedelta(days=1)
            if self.is_business_day(d):
                n += 1
        return n


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """n-ésimo ``weekday`` (0=lunes) del mes."""
    d = date(year, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _prev_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


@dataclass(frozen=True, slots=True)
class ContractDates:
    contract: ContractId
    last_trade: date
    first_notice: date | None
    roll_date: date

    @property
    def reference(self) -> date:
        return self.first_notice or self.last_trade


class ContractCalendar:
    """Calcula fechas clave y el contrato activo (front) para una raíz."""

    def __init__(self, spec: ContractSpec, holidays: Iterable[date] = ()) -> None:
        self.spec = spec
        self.bc = BusinessCalendar(holidays)

    # ------------------------------------------------------------------ #
    def last_trade_date(self, c: ContractId) -> date:
        rule = self.spec.cfg.expiry_rule
        bc = self.bc
        if rule is ExpiryRule.EQUITY_INDEX:
            return bc.previous_or_same(nth_weekday(c.year, c.month, 4, 3))
        if rule is ExpiryRule.FX_IMM:
            return bc.shift(nth_weekday(c.year, c.month, 2, 3), -2)
        if rule is ExpiryRule.CRUDE_OIL:
            py, pm = _prev_month(c.year, c.month)
            d25 = date(py, pm, 25)
            base = d25 if bc.is_business_day(d25) else bc.previous_or_same(d25)
            return bc.shift(base, -3)
        if rule is ExpiryRule.NATURAL_GAS:
            return bc.shift(date(c.year, c.month, 1), -3)
        if rule is ExpiryRule.METALS:
            return bc.shift(bc.last_business_day(c.year, c.month), -2)
        if rule is ExpiryRule.TREASURY:
            return bc.shift(bc.last_business_day(c.year, c.month), -7)
        raise NotImplementedError(rule)

    def first_notice_date(self, c: ContractId) -> date | None:
        if not self.spec.cfg.physical_delivery:
            return None
        rule = self.spec.cfg.expiry_rule
        if rule in (ExpiryRule.METALS, ExpiryRule.TREASURY):
            py, pm = _prev_month(c.year, c.month)
            return self.bc.last_business_day(py, pm)
        if rule in (ExpiryRule.CRUDE_OIL, ExpiryRule.NATURAL_GAS):
            # La entrega en energía se produce durante el mes del contrato; los
            # especuladores deben estar fuera antes del último día de negociación.
            return None
        return None

    def dates(self, c: ContractId) -> ContractDates:
        lt = self.last_trade_date(c)
        fnd = self.first_notice_date(c)
        roll_cfg = self.spec.cfg.roll
        ref = fnd if (fnd is not None and roll_cfg.use_first_notice) else lt
        return ContractDates(c, lt, fnd, self.bc.shift(ref, -roll_cfg.days_before))

    # ------------------------------------------------------------------ #
    def contracts_between(self, start: date, end: date) -> list[ContractId]:
        """Contratos listados cuyo mes cae en [mes(start), mes(end) + 12m]."""
        out: list[ContractId] = []
        months = self.spec.listed_months
        for y in range(start.year, end.year + 2):
            for m in months:
                c = ContractId(y, m, self.spec.root)
                if date(y, m, 1) >= date(start.year, start.month, 1) and date(y, m, 1) <= date(
                    end.year + 1, end.month, 1
                ):
                    out.append(c)
        return sorted(out)

    def front_contract(self, as_of: date) -> ContractId:
        """Contrato a operar en ``as_of`` según el roll por calendario (roll_date incluido => siguiente)."""
        for c in self.contracts_between(as_of - timedelta(days=40), as_of + timedelta(days=400)):
            if self.dates(c).roll_date > as_of:
                return c
        raise RuntimeError(f"No se encontró contrato front para {self.spec.root} en {as_of}")

    def next_contract(self, c: ContractId) -> ContractId:
        months = self.spec.listed_months
        later = [m for m in months if m > c.month]
        if later:
            return ContractId(c.year, later[0], c.root)
        return ContractId(c.year + 1, months[0], c.root)

    def days_to_roll(self, as_of: date) -> int:
        front = self.front_contract(as_of)
        return self.bc.business_days_between(as_of, self.dates(front).roll_date)
