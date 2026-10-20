"""Quién realiza una acción. Las operaciones sensibles comprueban el tipo de actor en el servidor."""
from __future__ import annotations

from dataclasses import dataclass


class PermissionDenied(Exception):
    pass


@dataclass(frozen=True)
class Actor:
    name: str
    kind: str  # agent | human | system | public

    @property
    def label(self) -> str:
        return f"{self.kind}:{self.name}"


def agent(name: str) -> Actor:
    return Actor(name, "agent")


SYSTEM = Actor("system", "system")
PUBLIC = Actor("visitante", "public")


def human(username: str) -> Actor:
    """Solo lo crean la capa web tras autenticar y la CLI local del propietario."""
    return Actor(username, "human")


def require_human(actor: Actor, what: str) -> None:
    if actor.kind != "human":
        raise PermissionDenied(f"'{what}' requiere una persona autenticada; actor={actor.label}")
