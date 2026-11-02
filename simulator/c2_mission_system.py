"""Sistema Central de Mando y Control (C2 / ATM Ground Station)."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional

from simulator.protocol import (
    ChecksumMismatchError,
    CorruptSyncError,
    FrameTooShortError,
    InvalidPayloadLengthError,
    MsgType,
    SubsysID,
    TacticalFrame,
    build_cmd_payload,
    parse_ack_payload,
    parse_nack_payload,
    parse_telemetry_payload,
)
from simulator.transport import LOOPBACK, UDPTransport

logger = logging.getLogger(__name__)


@dataclass
class TargetTrack:
    """Última posición de blanco registrada."""
    azimuth_deg: float
    elevation_deg: float
    distance_nm: float
    op_status: int
    timestamp: float


class C2MissionSystem:
    """Procesa telemetría de radar y despacha comandos de posición al actuador."""

    def __init__(
        self,
        bind_port: int,
        actuator_port: int,
        actuator_host: str = LOOPBACK,
    ) -> None:
        self._bind_port = bind_port
        self._actuator_port = actuator_port
        self._actuator_host = actuator_host

        self._transport = UDPTransport(bind_port=bind_port)
        self._last_track: Optional[TargetTrack] = None
        self._seq_num = 0

        self._telemetry_rx_count = 0
        self._commands_sent_count = 0
        self._ack_rx_count = 0
        self._nack_rx_count = 0
        self._corrupt_frames_count = 0

        self._last_cmd_timestamp: Optional[float] = None
        self._last_ack_latency_s: Optional[float] = None

        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Inicia el transporte y el hilo daemon de procesamiento."""
        self._transport.open()
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, name="C2MissionSystem", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Detiene el hilo y cierra el transporte."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._transport.close()

    @property
    def last_track(self) -> Optional[TargetTrack]:
        with self._lock:
            return self._last_track

    @property
    def telemetry_rx_count(self) -> int:
        with self._lock:
            return self._telemetry_rx_count

    @property
    def commands_sent_count(self) -> int:
        with self._lock:
            return self._commands_sent_count

    @property
    def ack_rx_count(self) -> int:
        with self._lock:
            return self._ack_rx_count

    @property
    def nack_rx_count(self) -> int:
        with self._lock:
            return self._nack_rx_count

    @property
    def corrupt_frames_count(self) -> int:
        with self._lock:
            return self._corrupt_frames_count

    @property
    def last_ack_latency_s(self) -> Optional[float]:
        with self._lock:
            return self._last_ack_latency_s

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
        except (
            CorruptSyncError,
            ChecksumMismatchError,
            FrameTooShortError,
            InvalidPayloadLengthError,
        ) as exc:
            logger.warning("C2 descartó trama corrupta: %s", exc)
            with self._lock:
                self._corrupt_frames_count += 1
            return

        if frame.msg_type == MsgType.TELEMETRY:
            self._process_telemetry(frame)
        elif frame.msg_type == MsgType.ACK:
            self._process_ack(frame)
        elif frame.msg_type == MsgType.NACK:
            self._process_nack(frame)

    def _process_telemetry(self, frame: TacticalFrame) -> None:
        try:
            azimuth, elevation, distance, status = parse_telemetry_payload(
                frame.payload
            )
        except InvalidPayloadLengthError as exc:
            logger.warning("Payload de telemetría inválido: %s", exc)
            with self._lock:
                self._corrupt_frames_count += 1
            return

        track = TargetTrack(
            azimuth_deg=azimuth,
            elevation_deg=elevation,
            distance_nm=distance,
            op_status=status,
            timestamp=time.monotonic(),
        )
        with self._lock:
            self._last_track = track
            self._telemetry_rx_count += 1

        self._dispatch_position_command(azimuth, elevation)

    def _dispatch_position_command(self, azimuth: float, elevation: float) -> None:
        payload = build_cmd_payload(azimuth, elevation)
        with self._lock:
            seq = self._seq_num
            self._seq_num = (self._seq_num + 1) & 0xFFFF
            self._last_cmd_timestamp = time.monotonic()

        frame = TacticalFrame(
            src_id=SubsysID.C2,
            dst_id=SubsysID.ACTUATOR,
            msg_type=MsgType.CMD_POSITION,
            seq_num=seq,
            payload=payload,
        )
        try:
            self._transport.send_to(
                self._actuator_host,
                self._actuator_port,
                frame.serialize(),
            )
            with self._lock:
                self._commands_sent_count += 1
        except OSError as exc:
            logger.error("Error enviando CMD al actuador: %s", exc)

    def _process_ack(self, frame: TacticalFrame) -> None:
        try:
            azimuth, elevation, status = parse_ack_payload(frame.payload)
        except InvalidPayloadLengthError as exc:
            logger.warning("Payload ACK inválido: %s", exc)
            return

        with self._lock:
            if self._last_cmd_timestamp is not None:
                self._last_ack_latency_s = (
                    time.monotonic() - self._last_cmd_timestamp
                )
            self._ack_rx_count += 1

    def _process_nack(self, frame: TacticalFrame) -> None:
        try:
            error_code = parse_nack_payload(frame.payload)
        except InvalidPayloadLengthError:
            error_code = 0xFFFF
        with self._lock:
            self._nack_rx_count += 1
