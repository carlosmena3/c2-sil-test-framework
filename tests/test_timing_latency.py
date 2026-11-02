"""Pruebas de tiempos de respuesta y latencia del sistema."""

from __future__ import annotations

import socket
import time

import pytest

from framework.custom_markers import doors
from framework.subsystem_client import SubsystemClient
from simulator.protocol import (
    MsgType,
    SubsysID,
    TacticalFrame,
    build_cmd_payload,
    build_telemetry_payload,
)
from simulator.radar_subsystem import RadarTarget
from tests.conftest import SystemFixture

LOOPBACK = "127.0.0.1"

# Umbrales según especificación
MAX_ACK_LATENCY_MS: float = 40.0    # REQ-ACT-001
MAX_C2_DISPATCH_MS: float = 50.0    # REQ-SYS-001
MAX_E2E_LOOP_MS: float = 150.0      # Margen de bucle completo


@doors("REQ-ACT-001")
def test_actuator_ack_latency_under_40ms(system: SystemFixture) -> None:
    """TC-LAT-001: Latencia CMD -> ACK del actuador inferior a 40 ms."""
    target = RadarTarget(
        azimuth_deg=180.0, elevation_deg=0.0, distance_nm=50.0
    )
    system.radar.inject_target(target)

    SubsystemClient.wait_for(
        condition=lambda: system.c2.ack_rx_count >= 1,
        description="C2 recibe ACK del actuador",
        timeout_s=2.0,
    )

    latency_s = system.c2.last_ack_latency_s
    assert latency_s is not None, "El C2 no registró latencia de ACK."
    latency_ms = latency_s * 1000.0

    assert latency_ms < MAX_ACK_LATENCY_MS, (
        f"Latencia CMD->ACK excede umbral: {latency_ms:.2f} ms "
        f"(máximo REQ-ACT-001: {MAX_ACK_LATENCY_MS} ms)"
    )


@doors("REQ-SYS-001")
def test_c2_dispatch_latency_under_50ms(system: SystemFixture) -> None:
    """TC-LAT-002: Latencia de procesamiento y despacho C2 inferior a 50 ms."""
    send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    telemetry_frame = TacticalFrame(
        src_id=SubsysID.RADAR,
        dst_id=SubsysID.C2,
        msg_type=MsgType.TELEMETRY,
        seq_num=600,
        payload=build_telemetry_payload(
            azimuth_deg=90.0,
            elevation_deg=15.0,
            distance_nm=50.0,
            op_status=1,
        ),
    )

    cmd_before = system.c2.commands_sent_count

    try:
        t_send = time.monotonic()
        send_sock.sendto(
            telemetry_frame.serialize(), (LOOPBACK, system.ports.c2_port)
        )

        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            if system.c2.commands_sent_count > cmd_before:
                break
            time.sleep(0.001)

        t_dispatch = time.monotonic()
    finally:
        send_sock.close()

    assert system.c2.commands_sent_count > cmd_before, (
        "El C2 no despachó ningún comando tras recibir telemetría."
    )

    dispatch_ms = (t_dispatch - t_send) * 1000.0
    assert dispatch_ms < MAX_C2_DISPATCH_MS, (
        f"Latencia de despacho C2 excede umbral: {dispatch_ms:.2f} ms "
        f"(máximo REQ-SYS-001: {MAX_C2_DISPATCH_MS} ms)"
    )


@doors("REQ-SYS-001")
@doors("REQ-ACT-001")
def test_end_to_end_loop_latency(system: SystemFixture) -> None:
    """TC-LAT-003: Latencia del bucle completo E2E inferior a 150 ms."""
    target = RadarTarget(
        azimuth_deg=220.0,
        elevation_deg=-5.0,
        distance_nm=80.0,
    )

    ack_before = system.c2.ack_rx_count
    t_start = time.monotonic()
    system.radar.inject_target(target)

    SubsystemClient.wait_for(
        condition=lambda: system.c2.ack_rx_count > ack_before,
        description="ACK en el C2 tras inyección de blanco",
        timeout_s=1.0,
    )
    t_ack = time.monotonic()

    e2e_ms = (t_ack - t_start) * 1000.0
    assert e2e_ms < MAX_E2E_LOOP_MS, (
        f"Latencia E2E excede umbral: {e2e_ms:.2f} ms "
        f"(máximo permitido: {MAX_E2E_LOOP_MS} ms)"
    )


@doors("REQ-ACT-001")
def test_actuator_latency_stability(system: SystemFixture) -> None:
    """TC-LAT-004: Estabilidad temporal de latencia en 5 ciclos consecutivos."""
    latencies_ms: list[float] = []

    azimuths = [30.0, 60.0, 90.0, 120.0, 150.0]
    elevations = [0.0, 5.0, 10.0, 15.0, 20.0]

    for i in range(5):
        ack_before = system.c2.ack_rx_count

        system.radar.inject_target(
            RadarTarget(
                azimuth_deg=azimuths[i],
                elevation_deg=elevations[i],
                distance_nm=50.0 + i * 10.0,
            )
        )

        SubsystemClient.wait_for(
            condition=lambda: system.c2.ack_rx_count > ack_before,
            description=f"ACK iteración {i + 1}",
            timeout_s=2.0,
        )

        lat_s = system.c2.last_ack_latency_s
        assert lat_s is not None, (
            f"Iteración {i + 1}: el C2 no registró latencia de ACK."
        )
        latencies_ms.append(lat_s * 1000.0)

        system.radar.clear_target()
        time.sleep(0.02)

    for idx, lat in enumerate(latencies_ms):
        assert lat < MAX_ACK_LATENCY_MS, (
            f"Iteración {idx + 1}: latencia {lat:.2f} ms excede "
            f"umbral de {MAX_ACK_LATENCY_MS} ms (REQ-ACT-001)"
        )

