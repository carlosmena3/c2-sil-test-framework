"""Pruebas funcionales y análisis de valores límite para el radar."""

from __future__ import annotations

import socket
import time

import pytest

from framework.custom_markers import doors
from framework.subsystem_client import SubsystemClient
from simulator.protocol import TacticalFrame
from simulator.radar_subsystem import RadarState, RadarSubsystem, RadarTarget
from tests.conftest import SystemFixture, _get_free_port


@doors("REQ-RADAR-001")
class TestRadarAzimuthRange:
    """Validación de rango de azimut [0.0, 360.0)."""

    def test_valid_azimuth_boundary_min(self, system: SystemFixture) -> None:
        """TC-RADAR-001a: Azimut en límite inferior (0.0°)."""
        target = RadarTarget(azimuth_deg=0.0, elevation_deg=0.0, distance_nm=10.0)
        system.radar.inject_target(target)
        assert system.radar.state == RadarState.DETECTING

    def test_valid_azimuth_boundary_max(self, system: SystemFixture) -> None:
        """TC-RADAR-001b: Azimut en límite superior (359.99°)."""
        target = RadarTarget(azimuth_deg=359.99, elevation_deg=0.0, distance_nm=10.0)
        system.radar.inject_target(target)
        assert system.radar.state == RadarState.DETECTING

    def test_invalid_azimuth_negative(self, system: SystemFixture) -> None:
        """TC-RADAR-001c: Azimut negativo fuera de rango."""
        target = RadarTarget(azimuth_deg=-0.01, elevation_deg=0.0, distance_nm=10.0)
        with pytest.raises(ValueError, match="Azimut"):
            system.radar.inject_target(target)

    def test_invalid_azimuth_360(self, system: SystemFixture) -> None:
        """TC-RADAR-001d: Azimut de 360° fuera de rango."""
        target = RadarTarget(azimuth_deg=360.0, elevation_deg=0.0, distance_nm=10.0)
        with pytest.raises(ValueError, match="Azimut"):
            system.radar.inject_target(target)


@doors("REQ-RADAR-001")
class TestRadarElevationRange:
    """Validación de rango de elevación [-90.0, 90.0]."""

    def test_valid_elevation_min(self, system: SystemFixture) -> None:
        """TC-RADAR-002a: Elevación en límite inferior (-90.0°)."""
        target = RadarTarget(azimuth_deg=90.0, elevation_deg=-90.0, distance_nm=50.0)
        system.radar.inject_target(target)
        assert system.radar.state == RadarState.DETECTING

    def test_valid_elevation_max(self, system: SystemFixture) -> None:
        """TC-RADAR-002b: Elevación en límite superior (90.0°)."""
        target = RadarTarget(azimuth_deg=90.0, elevation_deg=90.0, distance_nm=50.0)
        system.radar.inject_target(target)
        assert system.radar.state == RadarState.DETECTING

    def test_invalid_elevation_below_min(self, system: SystemFixture) -> None:
        """TC-RADAR-002c: Elevación menor al mínimo."""
        target = RadarTarget(azimuth_deg=90.0, elevation_deg=-90.01, distance_nm=50.0)
        with pytest.raises(ValueError, match="Elevaci"):
            system.radar.inject_target(target)

    def test_invalid_elevation_above_max(self, system: SystemFixture) -> None:
        """TC-RADAR-002d: Elevación mayor al máximo."""
        target = RadarTarget(azimuth_deg=90.0, elevation_deg=90.01, distance_nm=50.0)
        with pytest.raises(ValueError, match="Elevaci"):
            system.radar.inject_target(target)


@doors("REQ-RADAR-003")
class TestRadarDistanceRange:
    """Validación de rango de distancia [0.0, 500.0] NM."""

    def test_valid_distance_zero(self, system: SystemFixture) -> None:
        """TC-RADAR-003a: Distancia mínima 0.0 NM."""
        target = RadarTarget(azimuth_deg=45.0, elevation_deg=5.0, distance_nm=0.0)
        system.radar.inject_target(target)
        assert system.radar.state == RadarState.DETECTING

    def test_valid_distance_max(self, system: SystemFixture) -> None:
        """TC-RADAR-003b: Distancia máxima 500.0 NM."""
        target = RadarTarget(azimuth_deg=45.0, elevation_deg=5.0, distance_nm=500.0)
        system.radar.inject_target(target)
        assert system.radar.state == RadarState.DETECTING

    def test_invalid_distance_negative(self, system: SystemFixture) -> None:
        """TC-RADAR-003c: Distancia negativa."""
        target = RadarTarget(azimuth_deg=45.0, elevation_deg=5.0, distance_nm=-1.0)
        with pytest.raises(ValueError, match="Distancia"):
            system.radar.inject_target(target)

    def test_invalid_distance_over_max(self, system: SystemFixture) -> None:
        """TC-RADAR-003d: Distancia superior al límite."""
        target = RadarTarget(azimuth_deg=45.0, elevation_deg=5.0, distance_nm=500.01)
        with pytest.raises(ValueError, match="Distancia"):
            system.radar.inject_target(target)


@doors("REQ-RADAR-002")
def test_radar_update_frequency(system: SystemFixture) -> None:
    """TC-RADAR-004: Frecuencia de emisión de telemetría >= 10 Hz."""
    target = RadarTarget(azimuth_deg=180.0, elevation_deg=10.0, distance_nm=100.0)
    system.radar.inject_target(target)

    frames_before: int = system.radar.frames_sent
    time.sleep(0.5)
    frames_after: int = system.radar.frames_sent
    frames_emitted: int = frames_after - frames_before

    assert frames_emitted >= 5, (
        f"Frecuencia insuficiente: {frames_emitted} frames en 0.5 s "
        f"(mínimo 5 para cumplir >= 10 Hz)"
    )


@doors("REQ-RADAR-004")
def test_radar_sequence_numbers_monotonic(system: SystemFixture) -> None:
    """TC-RADAR-005: Números de secuencia crecientes y monotónicos."""
    listener_port = _get_free_port()
    listener_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listener_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener_sock.bind(("127.0.0.1", listener_port))
    listener_sock.settimeout(0.25)

    iso_radar_port = _get_free_port()
    iso_radar = RadarSubsystem(
        bind_port=iso_radar_port,
        c2_port=listener_port,
        update_interval_s=0.05,
    )
    iso_radar.start()

    captured_seqs: list[int] = []
    try:
        iso_radar.inject_target(
            RadarTarget(azimuth_deg=90.0, elevation_deg=5.0, distance_nm=50.0)
        )
        deadline = time.monotonic() + 0.8
        while time.monotonic() < deadline and len(captured_seqs) < 6:
            try:
                data, _ = listener_sock.recvfrom(4096)
                frame = TacticalFrame.deserialize(data)
                captured_seqs.append(frame.seq_num)
            except socket.timeout:
                break
    finally:
        iso_radar.stop()
        listener_sock.close()

    assert len(captured_seqs) >= 2, (
        f"No se capturaron suficientes tramas ({len(captured_seqs)})."
    )
    for i in range(1, len(captured_seqs)):
        expected = (captured_seqs[i - 1] + 1) & 0xFFFF
        assert captured_seqs[i] == expected, (
            f"Salto no monotónico en secuencia: {captured_seqs[i-1]} -> {captured_seqs[i]}"
        )


@doors("REQ-RADAR-001")
def test_radar_state_transitions(system: SystemFixture) -> None:
    """TC-RADAR-006: Transiciones de la máquina de estados del radar."""
    assert system.radar.state == RadarState.SCANNING

    target = RadarTarget(azimuth_deg=45.0, elevation_deg=5.0, distance_nm=20.0)
    system.radar.inject_target(target)
    assert system.radar.state == RadarState.DETECTING

    system.radar.clear_target()
    assert system.radar.state == RadarState.SCANNING

    system.radar.inject_fault()
    assert system.radar.state == RadarState.FAULT

    system.radar.reset_fault()
    assert system.radar.state == RadarState.SCANNING
