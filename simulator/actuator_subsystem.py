"""Subsistema de Servocontrol de Antena."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from simulator.protocol import (
    ChecksumMismatchError,
    CorruptSyncError,
    FrameTooShortError,
    InvalidPayloadLengthError,
    MsgType,
    SubsysID,
    TacticalFrame,
    build_ack_payload,
    build_nack_payload,
    parse_cmd_payload,
)
from simulator.transport import LOOPBACK, UDPTransport

logger = logging.getLogger(__name__)

NACK_INVALID_RANGE: int = 0x0001
NACK_BAD_CHECKSUM: int = 0x0002
NACK_BAD_LENGTH: int = 0x0003
NACK_UNKNOWN: int = 0x00FF


class ActuatorState(Enum):
    IDLE = auto()
    READY = auto()
    MOVING = auto()
    FAULT = auto()


@dataclass
class AntennaPosition:
    azimuth_deg: float = 0.0
    elevation_deg: float = 0.0


class ActuatorSubsystem:
    """Subsistema de servocontrol de antena con confirmación ACK/NACK."""

    def __init__(
        self,
        bind_port: int,
        c2_port: int,
        movement_delay_s: float = 0.010,
        c2_host: str = LOOPBACK,
    ) -> None:
        self._bind_port = bind_port
        self._c2_port = c2_port
        self._c2_host = c2_host
        self._movement_delay_s = movement_delay_s

        self._transport = UDPTransport(bind_port=bind_port)
        self._state = ActuatorState.IDLE
        self._position = AntennaPosition()
        self._nack_count = 0
        self._ack_count = 0
        self._seq_num = 0

        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Inicia el transporte y el hilo daemon receptor."""
        self._transport.open()
        self._state = ActuatorState.READY
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, name="ActuatorSubsystem", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Detiene el hilo receptor y cierra el transporte."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._transport.close()
        self._state = ActuatorState.IDLE

    @property
    def position(self) -> AntennaPosition:
        with self._lock:
            return AntennaPosition(
                azimuth_deg=self._position.azimuth_deg,
                elevation_deg=self._position.elevation_deg,
            )

    @property
    def state(self) -> ActuatorState:
        with self._lock:
            return self._state

    @property
    def ack_count(self) -> int:
        with self._lock:
            return self._ack_count

    @property
    def nack_count(self) -> int:
        with self._lock:
            return self._nack_count

    @property
    def bind_port(self) -> int:
        return self._bind_port

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            result = self._transport.recv()
            if result is None:
                continue
            raw_data, _ = result
            self._handle_datagram(raw_data)

    def _handle_datagram(self, raw_data: bytes) -> None:
        try:
            frame = TacticalFrame.deserialize(raw_data)
        except (CorruptSyncError, ChecksumMismatchError) as exc:
            logger.warning("Trama rechazada [integridad]: %s", exc)
            self._send_nack(NACK_BAD_CHECKSUM)
            return
        except (FrameTooShortError, InvalidPayloadLengthError) as exc:
            logger.warning("Trama rechazada [longitud]: %s", exc)
            self._send_nack(NACK_BAD_LENGTH)
            return

        if frame.msg_type == MsgType.CMD_POSITION:
            self._process_position_cmd(frame)

    def _process_position_cmd(self, frame: TacticalFrame) -> None:
        try:
            azimuth, elevation = parse_cmd_payload(frame.payload)
        except InvalidPayloadLengthError as exc:
            logger.warning("Payload de comando inválido: %s", exc)
            self._send_nack(NACK_BAD_LENGTH)
            return

        if not (0.0 <= azimuth < 360.0) or not (-90.0 <= elevation <= 90.0):
            logger.warning("Coordenadas fuera de rango: az=%.2f el=%.2f", azimuth, elevation)
            self._send_nack(NACK_INVALID_RANGE)
            return

        with self._lock:
            self._state = ActuatorState.MOVING

        time.sleep(self._movement_delay_s)

        with self._lock:
            self._position.azimuth_deg = azimuth
            self._position.elevation_deg = elevation
            self._state = ActuatorState.READY

        self._send_ack(azimuth, elevation)

    def _send_ack(self, azimuth: float, elevation: float) -> None:
        payload = build_ack_payload(azimuth, elevation, status=1)
        with self._lock:
            seq = self._seq_num
            self._seq_num = (self._seq_num + 1) & 0xFFFF

        frame = TacticalFrame(
            src_id=SubsysID.ACTUATOR,
            dst_id=SubsysID.C2,
            msg_type=MsgType.ACK,
            seq_num=seq,
            payload=payload,
        )
        try:
            self._transport.send_to(
                self._c2_host, self._c2_port, frame.serialize()
            )
            with self._lock:
                self._ack_count += 1
        except OSError as exc:
            logger.error("Error enviando ACK: %s", exc)

    def _send_nack(self, error_code: int) -> None:
        payload = build_nack_payload(error_code)
        with self._lock:
            seq = self._seq_num
            self._seq_num = (self._seq_num + 1) & 0xFFFF

        frame = TacticalFrame(
            src_id=SubsysID.ACTUATOR,
            dst_id=SubsysID.C2,
            msg_type=MsgType.NACK,
            seq_num=seq,
            payload=payload,
        )
        try:
            self._transport.send_to(
                self._c2_host, self._c2_port, frame.serialize()
            )
            with self._lock:
                self._nack_count += 1
        except OSError as exc:
            logger.error("Error enviando NACK: %s", exc)
