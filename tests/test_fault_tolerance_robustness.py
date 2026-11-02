"""Pruebas de tolerancia a fallos y robustez ante tramas corruptas."""

from __future__ import annotations

import time

import pytest

from framework.custom_markers import doors
from framework.fault_injector import FaultInjector
from framework.subsystem_client import SubsystemClient
from simulator.actuator_subsystem import ActuatorState
from simulator.protocol import (
    MsgType,
    SubsysID,
    TacticalFrame,
    build_cmd_payload,
    build_telemetry_payload,
)
from tests.conftest import SystemFixture

LOOPBACK = "127.0.0.1"
POLL_TIMEOUT = 1.0


@doors("REQ-SYS-ROB-001")
def test_corrupt_checksum_actuator_sends_nack(system: SystemFixture) -> None:
    """TC-ROB-001: Checksum corrupto provoca NACK y el actuador sigue operativo."""
    injector = FaultInjector()

    valid_frame = TacticalFrame(
        src_id=SubsysID.C2,
        dst_id=SubsysID.ACTUATOR,
        msg_type=MsgType.CMD_POSITION,
        seq_num=100,
        payload=build_cmd_payload(azimuth_deg=90.0, elevation_deg=10.0),
    )
    corrupted_bytes = injector.corrupt_checksum(valid_frame.serialize())

    with SubsystemClient(listen_port=system.ports.c2_port) as client:
        nack_before = system.actuator.nack_count
        client.send_raw(
            data=corrupted_bytes,
            dest_host=LOOPBACK,
            dest_port=system.ports.actuator_port,
        )

        client.wait_for(
            condition=lambda: system.actuator.nack_count > nack_before,
            description="NACK tras checksum corrupto",
            timeout_s=POLL_TIMEOUT,
        )

    assert system.actuator.state == ActuatorState.READY, (
        "El actuador no está en READY tras recibir trama con checksum corrupto."
    )
    assert system.actuator.nack_count > nack_before


@doors("REQ-SYS-ROB-002")
def test_corrupt_payload_len_actuator_sends_nack(system: SystemFixture) -> None:
    """TC-ROB-002: Longitud de payload inconsistente provoca NACK."""
    injector = FaultInjector()

    valid_frame = TacticalFrame(
        src_id=SubsysID.C2,
        dst_id=SubsysID.ACTUATOR,
        msg_type=MsgType.CMD_POSITION,
        seq_num=101,
        payload=build_cmd_payload(azimuth_deg=180.0, elevation_deg=20.0),
    )
    corrupted_bytes = injector.corrupt_payload_len(
        valid_frame.serialize(), false_len=0xFFFF
    )

    with SubsystemClient(listen_port=system.ports.c2_port) as client:
        nack_before = system.actuator.nack_count
        client.send_raw(
            data=corrupted_bytes,
            dest_host=LOOPBACK,
            dest_port=system.ports.actuator_port,
        )

        client.wait_for(
            condition=lambda: system.actuator.nack_count > nack_before,
            description="NACK tras PAYLOAD_LEN corrupto",
            timeout_s=POLL_TIMEOUT,
        )

    assert system.actuator.state == ActuatorState.READY
    assert system.actuator.nack_count > nack_before


@doors("REQ-SYS-ROB-001")
def test_corrupt_sync_word_no_crash(system: SystemFixture) -> None:
    """TC-ROB-003: Palabra de sincronización inválida se descarta sin caída del servicio."""
    injector = FaultInjector()

    valid_frame = TacticalFrame(
        src_id=SubsysID.C2,
        dst_id=SubsysID.ACTUATOR,
        msg_type=MsgType.CMD_POSITION,
        seq_num=102,
        payload=build_cmd_payload(azimuth_deg=45.0, elevation_deg=5.0),
    )
    corrupted_bytes = injector.corrupt_sync_word(valid_frame.serialize())

    with SubsystemClient(listen_port=system.ports.c2_port) as client:
        client.send_raw(
            data=corrupted_bytes,
            dest_host=LOOPBACK,
            dest_port=system.ports.actuator_port,
        )
        time.sleep(0.15)

    assert system.actuator.state == ActuatorState.READY, (
        "El actuador no está en READY tras SYNC corrupto."
    )


@doors("REQ-SYS-ROB-002")
def test_truncated_frame_no_crash(system: SystemFixture) -> None:
    """TC-ROB-004: Trama truncada (< tamaño mínimo) se descarta sin caída."""
    injector = FaultInjector()

    valid_frame = TacticalFrame(
        src_id=SubsysID.C2,
        dst_id=SubsysID.ACTUATOR,
        msg_type=MsgType.CMD_POSITION,
        seq_num=103,
        payload=build_cmd_payload(azimuth_deg=60.0, elevation_deg=8.0),
    )
    truncated = injector.truncate_frame(valid_frame.serialize(), keep_bytes=5)

    with SubsystemClient(listen_port=system.ports.c2_port) as client:
        client.send_raw(
            data=truncated,
            dest_host=LOOPBACK,
            dest_port=system.ports.actuator_port,
        )
        time.sleep(0.15)

    assert system.actuator.state == ActuatorState.READY


@doors("REQ-SYS-ROB-001")
def test_c2_discards_corrupt_telemetry(system: SystemFixture) -> None:
    """TC-ROB-005: El C2 descarta telemetría corrupta sin alterar la traza actual."""
    injector = FaultInjector()

    assert system.c2.last_track is None

    telemetry_payload = build_telemetry_payload(
        azimuth_deg=50.0,
        elevation_deg=5.0,
        distance_nm=100.0,
        op_status=1,
    )
    valid_frame = TacticalFrame(
        src_id=SubsysID.RADAR,
        dst_id=SubsysID.C2,
        msg_type=MsgType.TELEMETRY,
        seq_num=200,
        payload=telemetry_payload,
    )
    corrupted_bytes = injector.corrupt_checksum(valid_frame.serialize())
    corrupt_before = system.c2.corrupt_frames_count

    with SubsystemClient(listen_port=system.ports.actuator_port) as client:
        client.send_raw(
            data=corrupted_bytes,
            dest_host=LOOPBACK,
            dest_port=system.ports.c2_port,
        )
        client.wait_for(
            condition=lambda: system.c2.corrupt_frames_count > corrupt_before,
            description="C2 registra trama corrupta",
            timeout_s=POLL_TIMEOUT,
        )

    assert system.c2.last_track is None, (
        "El C2 actualizó la traza con una trama corrupta."
    )
    assert system.c2.corrupt_frames_count > corrupt_before


@doors("REQ-SYS-ROB-001")
@doors("REQ-SYS-ROB-002")
def test_sustained_fault_injection_system_remains_operational(
    system: SystemFixture,
) -> None:
    """TC-ROB-006: El subsistema sigue operativo tras ráfaga sostenida de tramas corruptas."""
    injector = FaultInjector()

    with SubsystemClient(listen_port=system.ports.c2_port) as client:
        for seq in range(300, 310):
            valid_frame = TacticalFrame(
                src_id=SubsysID.C2,
                dst_id=SubsysID.ACTUATOR,
                msg_type=MsgType.CMD_POSITION,
                seq_num=seq,
                payload=build_cmd_payload(azimuth_deg=90.0, elevation_deg=5.0),
            )
            corrupted = injector.corrupt_checksum(valid_frame.serialize())
            client.send_raw(
                data=corrupted,
                dest_host=LOOPBACK,
                dest_port=system.ports.actuator_port,
            )

        time.sleep(0.1)

        valid_cmd = TacticalFrame(
            src_id=SubsysID.C2,
            dst_id=SubsysID.ACTUATOR,
            msg_type=MsgType.CMD_POSITION,
            seq_num=999,
            payload=build_cmd_payload(azimuth_deg=135.0, elevation_deg=25.0),
        )
        ack_before = system.actuator.ack_count
        client.send_frame(
            frame=valid_cmd,
            dest_host=LOOPBACK,
            dest_port=system.ports.actuator_port,
        )

        client.wait_for(
            condition=lambda: system.actuator.ack_count > ack_before,
            description="ACK tras inyección sostenida de fallos",
            timeout_s=POLL_TIMEOUT,
        )

    assert system.actuator.state == ActuatorState.READY
    assert system.actuator.ack_count > ack_before
