"""Fixtures de pytest para gestión de puertos y ciclo de vida de subsistemas SIL."""

from __future__ import annotations

import logging
import socket
from typing import Generator, NamedTuple

import pytest

from framework.custom_markers import register_markers
from simulator.actuator_subsystem import ActuatorSubsystem
from simulator.c2_mission_system import C2MissionSystem
from simulator.radar_subsystem import RadarSubsystem

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)


def pytest_configure(config: pytest.Config) -> None:
    register_markers(config)


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class SubsystemPorts(NamedTuple):
    c2_port: int
    radar_port: int
    actuator_port: int


class SystemFixture(NamedTuple):
    c2: C2MissionSystem
    radar: RadarSubsystem
    actuator: ActuatorSubsystem
    ports: SubsystemPorts


@pytest.fixture()
def subsystem_ports() -> SubsystemPorts:
    return SubsystemPorts(
        c2_port=_get_free_port(),
        radar_port=_get_free_port(),
        actuator_port=_get_free_port(),
    )


@pytest.fixture()
def system(subsystem_ports: SubsystemPorts) -> Generator[SystemFixture, None, None]:
    """Arranca C2, Radar y Actuador garantizando apagado limpio en finally."""
    ports = subsystem_ports

    c2 = C2MissionSystem(
        bind_port=ports.c2_port,
        actuator_port=ports.actuator_port,
    )
    radar = RadarSubsystem(
        bind_port=ports.radar_port,
        c2_port=ports.c2_port,
        update_interval_s=0.05,
    )
    actuator = ActuatorSubsystem(
        bind_port=ports.actuator_port,
        c2_port=ports.c2_port,
        movement_delay_s=0.010,
    )

    c2.start()
    actuator.start()
    radar.start()

    try:
        yield SystemFixture(c2=c2, radar=radar, actuator=actuator, ports=ports)
    finally:
        radar.stop()
        actuator.stop()
        c2.stop()


@pytest.fixture()
def c2_and_actuator(
    subsystem_ports: SubsystemPorts,
) -> Generator[tuple[C2MissionSystem, ActuatorSubsystem, SubsystemPorts], None, None]:
    """Arranca únicamente C2 y Actuador para pruebas aisladas."""
    ports = subsystem_ports
    c2 = C2MissionSystem(
        bind_port=ports.c2_port,
        actuator_port=ports.actuator_port,
    )
    actuator = ActuatorSubsystem(
        bind_port=ports.actuator_port,
        c2_port=ports.c2_port,
        movement_delay_s=0.010,
    )
    c2.start()
    actuator.start()
    try:
        yield c2, actuator, ports
    finally:
        actuator.stop()
        c2.stop()


_DOORS_COVERAGE: dict[str, list[str]] = {}


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    """Recopila requisitos DOORS asociados a tests superados."""
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.passed:
        for mark in item.iter_markers(name="doors"):
            req_id = mark.kwargs.get("req_id")
            if req_id:
                _DOORS_COVERAGE.setdefault(req_id, []).append(report.nodeid)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if _DOORS_COVERAGE:
        print("\n\n===== DOORS COVERAGE SUMMARY =====")
        for req_id, tests in sorted(_DOORS_COVERAGE.items()):
            print(f"  {req_id}: {len(tests)} test(s)")
            for t in tests:
                print(f"    - {t}")
        print("===================================\n")
