"""Decorador @doors(req_id) para trazabilidad de requisitos DOORS."""

from __future__ import annotations

from typing import Callable, TypeVar
import pytest

F = TypeVar("F", bound=Callable[..., object])


def doors(req_id: str) -> Callable[[F], F]:
    """Asocia un caso de prueba con un identificador de requisito DOORS."""
    return pytest.mark.doors(req_id=req_id)


def register_markers(config: pytest.Config) -> None:
    """Registra la marca 'doors' en pytest."""
    config.addinivalue_line(
        "markers",
        "doors(req_id): marca el test con el identificador de requisito DOORS asociado.",
    )
