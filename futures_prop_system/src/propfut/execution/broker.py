"""Interfaz de broker y broker simulado con supuestos de ejecución **conservadores**.

Supuestos del simulador (documentados porque determinan la validez del backtest):

* Las órdenes enviadas al cierre de la barra ``t`` se procesan en la barra ``t+1``.
* MARKET: se llena al ``open`` + slippage adverso (base del contrato + impacto por tamaño).
* LIMIT: sólo se llena si el precio **atraviesa** el límite al menos 1 tick
  (``limit_requires_trade_through``); tocar no basta (cola desconocida). Llenado
  parcial limitado por ``max_participation_rate`` x volumen de la barra.
* STOP: se dispara si el rango toca el stop; precio = peor entre stop y open
  (gaps) + slippage adverso.
* Bracket: si stop y target se tocan en la misma barra, se asume el **stop**.
  Un target activado en la barra de entrada no puede llenarse hasta la siguiente;
  un stop sí (pesimista).

Para producción, implementa :class:`Broker` sobre la API real (Rithmic, CQG,
Tradovate, IBKR/TWS, NinjaTrader...). Usa órdenes nativas OCO/bracket en el
servidor del broker para que los stops sobrevivan a una caída del sistema.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Protocol

from propfut.contracts.specs import ContractSpec
from propfut.core.types import Bar, OrderStatus, OrderType, Side
from propfut.execution.orders import Fill, Order


class Broker(Protocol):
    def submit(self, order: Order) -> Order: ...
    def cancel(self, order_id: str) -> bool: ...
    def modify_stop(self, order_id: str, stop_price: float) -> bool: ...
    def get_order(self, order_id: str) -> Order | None: ...
    def open_orders(self, root: str | None = None) -> list[Order]: ...


class SimulatedBroker:
    """Broker de backtest/paper. ``continuous_mode`` ignora el símbolo de contrato
    (precios en espacio de serie continua ajustada)."""

    def __init__(
        self,
        specs: Mapping[str, ContractSpec],
        limit_requires_trade_through: bool = True,
        max_participation_rate: float = 0.05,
        slippage_multiplier: float = 1.0,
        continuous_mode: bool = True,
    ) -> None:
        self.specs = specs
        self.trade_through = limit_requires_trade_through
        self.participation = max_participation_rate
        self.slip_mult = slippage_multiplier
        self.continuous_mode = continuous_mode
        self.orders: dict[str, Order] = {}

    # ------------------------------------------------------------------ #
    def submit(self, order: Order) -> Order:
        spec = self.specs.get(order.root)
        if spec is None:
            order.status, order.reject_reason = OrderStatus.REJECTED, "raíz desconocida"
            return order
        if order.limit_price is not None:
            order.limit_price = spec.round_price(order.limit_price)
        if order.stop_price is not None:
            order.stop_price = spec.round_stop(order.stop_price, is_long=order.side is Side.SHORT)
        if order.status not in (OrderStatus.HELD, OrderStatus.PENDING_CONFIRMATION):
            order.status = OrderStatus.WORKING
        self.orders[order.id] = order
        return order

    def cancel(self, order_id: str) -> bool:
        o = self.orders.get(order_id)
        if o is None or o.status.is_terminal:
            return False
        o.status = OrderStatus.CANCELLED
        return True

    def modify_stop(self, order_id: str, stop_price: float) -> bool:
        o = self.orders.get(order_id)
        if o is None or o.status.is_terminal or o.type is not OrderType.STOP:
            return False
        o.stop_price = self.specs[o.root].round_stop(stop_price, is_long=o.side is Side.SHORT)
        return True

    def set_open_qty(self, order_id: str, open_qty: int, activate: bool = False) -> None:
        """Ajusta la cantidad pendiente de una orden de salida a ``open_qty``.

        Con ``activate`` una hija HELD pasa a WORKING (la entrada se ha llenado).
        ``open_qty == 0`` cancela la orden.
        """
        o = self.orders[order_id]
        if o.status.is_terminal:
            return
        if open_qty <= 0:
            o.status = OrderStatus.CANCELLED
            return
        o.qty = o.filled_qty + open_qty
        if o.status is OrderStatus.HELD and activate:
            o.status = OrderStatus.WORKING
            o.activated_this_bar = True

    def get_order(self, order_id: str) -> Order | None:
        return self.orders.get(order_id)

    def open_orders(self, root: str | None = None) -> list[Order]:
        return [
            o for o in self.orders.values()
            if not o.status.is_terminal and (root is None or o.root == root)
        ]

    # ------------------------------------------------------------------ #
    def _slip(self, spec: ContractSpec, qty: int, volume: float) -> float:
        base = spec.cfg.slippage_ticks
        if volume > 0:
            impact = max(0.0, qty / (self.participation * volume) - 1.0)
            base += min(impact, 10.0)
        return base * self.slip_mult

    def _fill(self, o: Order, qty: int, price: float, bar: Bar, slip_ticks: float) -> Fill:
        spec = self.specs[o.root]
        o.apply_fill(qty, price)
        return Fill(o.id, o.root, bar.contract if self.continuous_mode else o.contract, o.side, qty,
                    price, bar.ts, qty * spec.cfg.commission_per_side, o.tag, slip_ticks)

    def process_bar(self, bar: Bar) -> list[Fill]:
        """Procesa las órdenes de ``bar.root`` contra la barra. Devuelve fills en orden temporal."""
        spec = self.specs[bar.root]
        tick = spec.tick_size
        fills: list[Fill] = []
        orders = [o for o in self.orders.values() if o.root == bar.root and o.is_active]
        if not self.continuous_mode:
            for o in orders:
                if o.contract != bar.contract:
                    o.status, o.reject_reason = OrderStatus.REJECTED, "contrato no coincide con el mercado"
            orders = [o for o in orders if o.is_active]
        for o in orders:
            o.activated_this_bar = False

        # 1) market (entradas y salidas) a la apertura
        for o in [o for o in orders if o.type is OrderType.MARKET]:
            s = self._slip(spec, o.remaining, bar.volume)
            px = spec.round_price(bar.open + int(o.side) * s * tick, "up" if o.side is Side.LONG else "down")
            fills.append(self._fill(o, o.remaining, px, bar, s))

        # 2) limit de entrada
        for o in [o for o in orders if o.type is OrderType.LIMIT and o.tag == "entry"]:
            f = self._try_limit(o, bar, spec)
            if f:
                fills.append(f)
        return fills

    def process_exits(self, bar: Bar) -> list[Fill]:
        """Segunda fase: stops y targets (incluye hijas activadas en esta barra)."""
        spec = self.specs[bar.root]
        tick = spec.tick_size
        fills: list[Fill] = []
        active = [o for o in self.orders.values() if o.root == bar.root and o.is_active and o.tag != "entry"]
        by_group: dict[str, list[Order]] = {}
        singles: list[Order] = []
        for o in active:
            if o.oco_group:
                by_group.setdefault(o.oco_group, []).append(o)
            else:
                singles.append(o)
        for group in list(by_group.values()) + [[o] for o in singles]:
            stops = [o for o in group if o.type in (OrderType.STOP, OrderType.STOP_LIMIT)]
            targets = [o for o in group if o.type is OrderType.LIMIT and not o.activated_this_bar]
            done = False
            for o in stops:  # stop primero (pesimista)
                assert o.stop_price is not None
                hit = bar.low <= o.stop_price if o.side is Side.SHORT else bar.high >= o.stop_price
                if not hit:
                    continue
                if o.side is Side.SHORT:  # stop de un largo: vende
                    base = min(o.stop_price, bar.open)
                else:
                    base = max(o.stop_price, bar.open)
                s = self._slip(spec, o.remaining, bar.volume)
                px = spec.round_price(base + int(o.side) * s * tick, "up" if o.side is Side.LONG else "down")
                if o.side is Side.SHORT:
                    px = max(px, bar.low)
                else:
                    px = min(px, bar.high)
                fills.append(self._fill(o, o.remaining, px, bar, s))
                done = True
                break
            if done:
                for o in group:
                    if o.is_active:
                        o.status = OrderStatus.CANCELLED
                continue
            for o in targets:
                f = self._try_limit(o, bar, spec)
                if f:
                    fills.append(f)
                    if o.status is OrderStatus.FILLED:
                        for other in group:
                            if other is not o and other.is_active:
                                other.status = OrderStatus.CANCELLED
                    break
        return fills

    def _try_limit(self, o: Order, bar: Bar, spec: ContractSpec) -> Fill | None:
        assert o.limit_price is not None
        tick = spec.tick_size
        lp = o.limit_price
        need = tick if self.trade_through else 0.0
        if o.side is Side.LONG:
            if bar.open <= lp:
                px = bar.open  # mejora de precio en apertura
            elif bar.low <= lp - need + 1e-12:
                px = lp
            else:
                return None
        else:
            if bar.open >= lp:
                px = bar.open
            elif bar.high >= lp + need - 1e-12:
                px = lp
            else:
                return None
        cap = max(1, int(math.floor(self.participation * bar.volume))) if bar.volume > 0 else o.remaining
        qty = min(o.remaining, cap)
        return self._fill(o, qty, spec.round_price(px), bar, 0.0)
