"""Pruebas de integración del bucle completo del sistema (Radar -> C2 -> Actuador)."""

from __future__ import annotations

import time

import pytest

from framework.custom_markers import doors
from framework.subsystem_client import SubsystemClient
from simulator.radar_subsystem import RadarTarget
from tests.conftest import SystemFixture

LOOPBACK = "127.0.0.1"


@doors("REQ-SYS-001")
@doors("REQ-SYS-002")
@doors("REQ-ACT-001")
@doors("REQ-RADAR-001")
def test_full_closed_loop(system: SystemFixture) -> None:
    """TC-E2E-001: Verificación de bucle cerrado completo de telemetría, comando y ACK."""
    target = RadarTarget(
        azimuth_deg=123.5,
        elevation_deg=12.0,
        distance_nm=75.0,
        op_status=1,
    )
    system.radar.inject_target(target)

    client = SubsystemClient(listen_port=system.ports.c2_port)

    client.wait_for(
        condition=lambda: system.c2.telemetry_rx_count >= 1,
        description="C2 recibe telemetría de radar",
        timeout_s=2.0,
    )

    track = system.c2.last_track
    assert track is not None, "C2 no actualizó la última traza de blanco."
    assert abs(track.azimuth_deg - target.azimuth_deg) < 0.01, (
        f"Azimut de traza incorrecto: {track.azimuth_deg}° vs {target.azimuth_deg}°"
    )
    assert abs(track.elevation_deg - target.elevation_deg) < 0.01, (
        f"Elevación de traza incorrecta: {track.elevation_deg}° vs {target.elevation_deg}°"
    )
    assert abs(track.distance_nm - target.distance_nm) < 0.01, (
        f"Distancia incorrecta: {track.distance_nm} NM vs {target.distance_nm} NM"
    )

    client.wait_for(
        condition=lambda: system.c2.commands_sent_count >= 1,
        description="C2 despachó comando al actuador",
        timeout_s=2.0,
    )
    assert system.c2.commands_sent_count >= 1

    client.wait_for(
        condition=lambda: system.c2.ack_rx_count >= 1,
        description="C2 recibió ACK del actuador",
        timeout_s=2.0,
    )
    assert system.c2.ack_rx_count >= 1

    pos = system.actuator.position
    assert abs(pos.azimuth_deg - target.azimuth_deg) < 0.01, (
        f"Posición actuador azimut incorrecto: {pos.azimuth_deg}°"
    )
    assert abs(pos.elevation_deg - target.elevation_deg) < 0.01, (
        f"Posición actuador elevación incorrecta: {pos.elevation_deg}°"
    )


@doors("REQ-SYS-002")
def test_c2_updates_track_on_each_telemetry(system: SystemFixture) -> None:
    """TC-E2E-002: El C2 actualiza la traza con cada reporte de telemetría."""
    client = SubsystemClient(listen_port=system.ports.c2_port)

    target_a = RadarTarget(azimuth_deg=45.0, elevation_deg=5.0, distance_nm=30.0)
    system.radar.inject_target(target_a)
    client.wait_for(
        condition=lambda: system.c2.telemetry_rx_count >= 1,
        description="C2 recibe telemetría blanco A",
        timeout_s=2.0,
    )
    count_after_a = system.c2.telemetry_rx_count

    target_b = RadarTarget(azimuth_deg=270.0, elevation_deg=-20.0, distance_nm=200.0)
    system.radar.inject_target(target_b)
    client.wait_for(
        condition=lambda: system.c2.telemetry_rx_count > count_after_a,
        description="C2 recibe telemetría blanco B",
        timeout_s=2.0,
    )

    track = system.c2.last_track
    assert track is not None
    assert abs(track.azimuth_deg - 270.0) < 0.01, (
        f"Traza no actualizada al blanco B: azimut={track.azimuth_deg}°"
    )


@doors("REQ-SYS-001")
@doors("REQ-RADAR-001")
def test_coordinate_integrity_through_chain(system: SystemFixture) -> None:
    """TC-E2E-003: Preservación de la precisión de coordenadas a lo largo del enlace."""
    client = SubsystemClient(listen_port=system.ports.c2_port)

    target = RadarTarget(
        azimuth_deg=299.75,
        elevation_deg=-45.5,
        distance_nm=123.456,
    )
    system.radar.inject_target(target)

    client.wait_for(
        condition=lambda: system.c2.ack_rx_count >= 1,
        description="ACK del actuador tras telemetría",
        timeout_s=2.0,
    )

    pos = system.actuator.position
    assert abs(pos.azimuth_deg - target.azimuth_deg) < 0.001, (
        f"Integridad perdida en azimut: {pos.azimuth_deg}° vs {target.azimuth_deg}°"
    )
    assert abs(pos.elevation_deg - target.elevation_deg) < 0.001, (
        f"Integridad perdida en elevación: {pos.elevation_deg}° vs {target.elevation_deg}°"
    )


@doors("REQ-SYS-002")
def test_no_command_without_target(system: SystemFixture) -> None:
    """TC-E2E-004: En ausencia de blanco activo no se generan comandos al actuador."""
    time.sleep(0.2)

    assert system.c2.telemetry_rx_count == 0, (
        "El C2 recibió telemetría sin blanco activo."
    )
    assert system.c2.commands_sent_count == 0, (
        "El C2 despachó comandos sin blanco activo."
    )
