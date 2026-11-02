"""Pruebas del subsistema de seguimiento de antena (actuador)."""

from __future__ import annotations

import time

import pytest

from framework.custom_markers import doors
from framework.fault_injector import FaultInjector
from framework.subsystem_client import SubsystemClient
from simulator.actuator_subsystem import ActuatorState, ActuatorSubsystem
from simulator.protocol import (
    MsgType,
    SubsysID,
    TacticalFrame,
    build_cmd_payload,
)
from tests.conftest import SubsystemPorts, SystemFixture

LOOPBACK = "127.0.0.1"
POLL_TIMEOUT = 1.0


@doors("REQ-ACT-001")
def test_actuator_ack_on_valid_command(system: SystemFixture) -> None:
    """TC-ACT-001: El actuador responde con ACK ante un comando válido."""
    with SubsystemClient(listen_port=system.ports.c2_port) as client:
        frame = TacticalFrame(
            src_id=SubsysID.C2,
            dst_id=SubsysID.ACTUATOR,
            msg_type=MsgType.CMD_POSITION,
            seq_num=1,
            payload=build_cmd_payload(azimuth_deg=135.0, elevation_deg=30.0),
        )
        ack_before = system.actuator.ack_count
        client.send_frame(
            frame=frame,
            dest_host=LOOPBACK,
            dest_port=system.ports.actuator_port,
        )

        client.wait_for(
            condition=lambda: system.actuator.ack_count > ack_before,
            description="ACK del actuador",
            timeout_s=POLL_TIMEOUT,
        )

    assert system.actuator.ack_count > ack_before, (
        "El actuador no emitió ACK tras comando válido."
    )


@doors("REQ-ACT-001")
def test_actuator_position_updated_after_command(system: SystemFixture) -> None:
    """TC-ACT-002: La posición interna se actualiza tras un comando válido."""
    target_azimuth = 270.5
    target_elevation = -15.0

    with SubsystemClient(listen_port=system.ports.c2_port) as client:
        frame = TacticalFrame(
            src_id=SubsysID.C2,
            dst_id=SubsysID.ACTUATOR,
            msg_type=MsgType.CMD_POSITION,
            seq_num=2,
            payload=build_cmd_payload(
                azimuth_deg=target_azimuth,
                elevation_deg=target_elevation,
            ),
        )
        ack_before = system.actuator.ack_count
        client.send_frame(
            frame=frame,
            dest_host=LOOPBACK,
            dest_port=system.ports.actuator_port,
        )

        client.wait_for(
            condition=lambda: system.actuator.ack_count > ack_before,
            description="ACK de posición actualizada",
            timeout_s=POLL_TIMEOUT,
        )

    pos = system.actuator.position
    assert abs(pos.azimuth_deg - target_azimuth) < 0.001, (
        f"Azimut incorrecto: {pos.azimuth_deg}° (esperado {target_azimuth}°)"
    )
    assert abs(pos.elevation_deg - target_elevation) < 0.001, (
        f"Elevación incorrecta: {pos.elevation_deg}° (esperada {target_elevation}°)"
    )


@doors("REQ-ACT-002")
def test_actuator_nack_on_invalid_azimuth(system: SystemFixture) -> None:
    """TC-ACT-003: Emisión de NACK ante azimut fuera de rango [0.0, 360.0)."""
    with SubsystemClient(listen_port=system.ports.c2_port) as client:
        frame = TacticalFrame(
            src_id=SubsysID.C2,
            dst_id=SubsysID.ACTUATOR,
            msg_type=MsgType.CMD_POSITION,
            seq_num=10,
            payload=build_cmd_payload(azimuth_deg=360.0, elevation_deg=0.0),
        )
        nack_before = system.actuator.nack_count
        client.send_frame(
            frame=frame,
            dest_host=LOOPBACK,
            dest_port=system.ports.actuator_port,
        )

        client.wait_for(
            condition=lambda: system.actuator.nack_count > nack_before,
            description="NACK por azimut inválido",
            timeout_s=POLL_TIMEOUT,
        )

    assert system.actuator.nack_count > nack_before


@doors("REQ-ACT-002")
def test_actuator_nack_on_invalid_elevation(system: SystemFixture) -> None:
    """TC-ACT-004: Emisión de NACK ante elevación fuera de rango [-90.0, 90.0]."""
    with SubsystemClient(listen_port=system.ports.c2_port) as client:
        frame = TacticalFrame(
            src_id=SubsysID.C2,
            dst_id=SubsysID.ACTUATOR,
            msg_type=MsgType.CMD_POSITION,
            seq_num=11,
            payload=build_cmd_payload(azimuth_deg=180.0, elevation_deg=91.0),
        )
        nack_before = system.actuator.nack_count
        client.send_frame(
            frame=frame,
            dest_host=LOOPBACK,
            dest_port=system.ports.actuator_port,
        )

        client.wait_for(
            condition=lambda: system.actuator.nack_count > nack_before,
            description="NACK por elevación inválida",
            timeout_s=POLL_TIMEOUT,
        )

    assert system.actuator.nack_count > nack_before


@doors("REQ-ACT-001")
def test_actuator_returns_to_ready_after_move(system: SystemFixture) -> None:
    """TC-ACT-005: El actuador regresa a estado READY tras procesar comando."""
    with SubsystemClient(listen_port=system.ports.c2_port) as client:
        frame = TacticalFrame(
            src_id=SubsysID.C2,
            dst_id=SubsysID.ACTUATOR,
            msg_type=MsgType.CMD_POSITION,
            seq_num=20,
            payload=build_cmd_payload(azimuth_deg=45.0, elevation_deg=15.0),
        )
        ack_before = system.actuator.ack_count
        client.send_frame(
            frame=frame,
            dest_host=LOOPBACK,
            dest_port=system.ports.actuator_port,
        )

        client.wait_for(
            condition=lambda: system.actuator.ack_count > ack_before,
            description="ACK y retorno a READY",
            timeout_s=POLL_TIMEOUT,
        )

    assert system.actuator.state == ActuatorState.READY
