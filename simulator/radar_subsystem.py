"""Subsistema de Sensor Radar (máquina de estados y emisión periódica de telemetría)."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from simulator.protocol import (
    MsgType,
    SubsysID,
    TacticalFrame,
    build_telemetry_payload,
)
from simulator.transport import LOOPBACK, UDPTransport

logger = logging.getLogger(__name__)


class RadarState(Enum):
    IDLE = auto()
    SCANNING = auto()
    DETECTING = auto()
    FAULT = auto()


@dataclass
class RadarTarget:
    """Parámetros de blanco simulado."""
    azimuth_deg: float
    elevation_deg: float
    distance_nm: float
    op_status: int = 1


class RadarSubsystem:
    """Sensor radar que emite reportes de telemetría hacia el C2."""

    def __init__(
        self,
        bind_port: int,
        c2_port: int,
        update_interval_s: float = 0.05,
        c2_host: str = LOOPBACK,
    ) -> None:
        self._bind_port = bind_port
        self._c2_port = c2_port
        self._c2_host = c2_host
        self._update_interval_s = update_interval_s

        self._transport = UDPTransport(bind_port=bind_port)
        self._state = RadarState.IDLE
        self._current_target: Optional[RadarTarget] = None
        self._seq_num = 0
        self._frames_sent = 0

        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Inicia el transporte y el hilo daemon de emisión."""
        self._transport.open()
        self._state = RadarState.SCANNING
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, name="RadarSubsystem", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Detiene el hilo emisor y cierra el transporte."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._transport.close()
        self._state = RadarState.IDLE

    def inject_target(self, target: RadarTarget) -> None:
        """Inyecta un blanco y transiciona el radar a DETECTING."""
        if not (0.0 <= target.azimuth_deg < 360.0):
            raise ValueError(f"Azimut inválido: {target.azimuth_deg}° (rango [0, 360))")
        if not (-90.0 <= target.elevation_deg <= 90.0):
            raise ValueError(f"Elevación inválida: {target.elevation_deg}° (rango [-90, 90])")
        if not (0.0 <= target.distance_nm <= 500.0):
            raise ValueError(f"Distancia inválida: {target.distance_nm} NM (rango [0, 500])")
        with self._lock:
            self._current_target = target
            self._state = RadarState.DETECTING

    def clear_target(self) -> None:
        """Elimina el blanco activo y regresa a SCANNING."""
        with self._lock:
            self._current_target = None
            self._state = RadarState.SCANNING

    def inject_fault(self) -> None:
        """Fuerza estado FAULT."""
        with self._lock:
            self._state = RadarState.FAULT

    def reset_fault(self) -> None:
        """Recupera el estado de FAULT a SCANNING."""
        with self._lock:
            if self._state == RadarState.FAULT:
                self._state = RadarState.SCANNING

    @property
    def state(self) -> RadarState:
        with self._lock:
            return self._state

    @property
    def frames_sent(self) -> int:
        with self._lock:
            return self._frames_sent

    @property
    def bind_port(self) -> int:
        return self._bind_port

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            with self._lock:
                state = self._state
                target = self._current_target

            if state == RadarState.DETECTING and target is not None:
                self._emit_telemetry(target)

            self._stop_event.wait(timeout=self._update_interval_s)

    def _emit_telemetry(self, target: RadarTarget) -> None:
        payload = build_telemetry_payload(
            azimuth_deg=target.azimuth_deg,
            elevation_deg=target.elevation_deg,
            distance_nm=target.distance_nm,
            op_status=target.op_status,
        )
        with self._lock:
            seq = self._seq_num
            self._seq_num = (self._seq_num + 1) & 0xFFFF

        frame = TacticalFrame(
            src_id=SubsysID.RADAR,
            dst_id=SubsysID.C2,
            msg_type=MsgType.TELEMETRY,
            seq_num=seq,
            payload=payload,
        )
        try:
            self._transport.send_to(self._c2_host, self._c2_port, frame.serialize())
            with self._lock:
                self._frames_sent += 1
        except OSError as exc:
            logger.error("Error al emitir telemetría: %s", exc)
