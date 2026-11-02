"""
Protocolo de mensajería binaria táctica/ATM (formato Big-Endian).

Estructura de trama (12 bytes mínimo + payload):
  ┌────────┬────────┬────────┬──────────┬─────────┬─────────────┬─────────┬──────────┐
  │ SYNC   │ SRC_ID │ DST_ID │ MSG_TYPE │ SEQ_NUM │ PAYLOAD_LEN │ PAYLOAD │ CHECKSUM │
  │  2 B   │  1 B   │  1 B   │   2 B    │   2 B   │    2 B      │ var. B  │   2 B    │
  └────────┴────────┴────────┴──────────┴─────────┴─────────────┴─────────┴──────────┘
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field
from typing import ClassVar

SYNC_WORD: int = 0xEB90
HEADER_FORMAT: str = "!HBBHHH"  # SYNC(H) SRC(B) DST(B) TYPE(H) SEQ(H) LEN(H)
HEADER_SIZE: int = struct.calcsize(HEADER_FORMAT)
CHECKSUM_SIZE: int = 2
MIN_FRAME_SIZE: int = HEADER_SIZE + CHECKSUM_SIZE


class SubsysID:
    C2: int = 0x01
    RADAR: int = 0x02
    ACTUATOR: int = 0x03
    BROADCAST: int = 0xFF


class MsgType:
    TELEMETRY: int = 0x0100
    CMD_POSITION: int = 0x0200
    ACK: int = 0x0300
    NACK: int = 0x0301
    FAULT: int = 0x0900


PAYLOAD_FMT_TELEMETRY: str = "!fffB"
PAYLOAD_FMT_CMD: str = "!ff"
PAYLOAD_FMT_ACK: str = "!ffB"
PAYLOAD_FMT_NACK: str = "!H"

PAYLOAD_SIZE_TELEMETRY: int = struct.calcsize(PAYLOAD_FMT_TELEMETRY)
PAYLOAD_SIZE_CMD: int = struct.calcsize(PAYLOAD_FMT_CMD)
PAYLOAD_SIZE_ACK: int = struct.calcsize(PAYLOAD_FMT_ACK)
PAYLOAD_SIZE_NACK: int = struct.calcsize(PAYLOAD_FMT_NACK)


class ProtocolError(Exception):
    """Base para excepciones del protocolo binario."""


class CorruptSyncError(ProtocolError):
    def __init__(self, received: int) -> None:
        super().__init__(f"SYNC inválido: esperado 0x{SYNC_WORD:04X}, recibido 0x{received:04X}")
        self.received = received


class ChecksumMismatchError(ProtocolError):
    def __init__(self, expected: int, got: int) -> None:
        super().__init__(f"Checksum inválido: calculado 0x{expected:04X}, recibido 0x{got:04X}")
        self.expected = expected
        self.got = got


class InvalidPayloadLengthError(ProtocolError):
    def __init__(self, declared: int, available: int) -> None:
        super().__init__(f"Longitud inválida: declarada={declared}, disponible={available}")
        self.declared = declared
        self.available = available


class FrameTooShortError(ProtocolError):
    def __init__(self, length: int) -> None:
        super().__init__(f"Trama demasiado corta: {length} bytes (mínimo {MIN_FRAME_SIZE})")
        self.length = length


def _compute_checksum(data: bytes) -> int:
    return sum(data) & 0xFFFF


@dataclass
class TacticalFrame:
    """Trama estructurada del protocolo táctico."""

    src_id: int
    dst_id: int
    msg_type: int
    seq_num: int
    payload: bytes = field(default_factory=bytes)

    _global_seq: ClassVar[int] = 0

    def serialize(self) -> bytes:
        """Serializa la trama agregando cabecera y checksum de 16 bits."""
        payload_len = len(self.payload)
        if payload_len > 0xFFFF:
            raise ValueError(f"Payload demasiado largo: {payload_len} bytes")

        header = struct.pack(
            HEADER_FORMAT,
            SYNC_WORD,
            self.src_id,
            self.dst_id,
            self.msg_type,
            self.seq_num,
            payload_len,
        )
        body = header + self.payload
        checksum = _compute_checksum(body)
        return body + struct.pack("!H", checksum)

    @staticmethod
    def deserialize(data: bytes) -> TacticalFrame:
        """Valida y deserializa un datagrama binario en una TacticalFrame."""
        if len(data) < MIN_FRAME_SIZE:
            raise FrameTooShortError(len(data))

        sync, src_id, dst_id, msg_type, seq_num, payload_len = struct.unpack_from(
            HEADER_FORMAT, data, 0
        )

        if sync != SYNC_WORD:
            raise CorruptSyncError(sync)

        expected_total = HEADER_SIZE + payload_len + CHECKSUM_SIZE
        if len(data) < expected_total:
            raise InvalidPayloadLengthError(
                declared=payload_len,
                available=len(data) - HEADER_SIZE - CHECKSUM_SIZE,
            )

        payload = data[HEADER_SIZE : HEADER_SIZE + payload_len]
        embedded_checksum = struct.unpack_from("!H", data, HEADER_SIZE + payload_len)[0]
        computed_checksum = _compute_checksum(data[: HEADER_SIZE + payload_len])

        if computed_checksum != embedded_checksum:
            raise ChecksumMismatchError(
                expected=computed_checksum, got=embedded_checksum
            )

        return TacticalFrame(
            src_id=src_id,
            dst_id=dst_id,
            msg_type=msg_type,
            seq_num=seq_num,
            payload=payload,
        )

    def __repr__(self) -> str:
        return (
            f"TacticalFrame(src=0x{self.src_id:02X}, dst=0x{self.dst_id:02X}, "
            f"type=0x{self.msg_type:04X}, seq={self.seq_num}, "
            f"payload_len={len(self.payload)})"
        )


# ---------------------------------------------------------------------------
# Helpers de construcción de payloads tipados
# ---------------------------------------------------------------------------

def _validate_finite_floats(*values: float) -> None:
    """Verifica que todos los valores flotantes sean números reales finitos (no NaN, no Inf)."""
    for v in values:
        if math.isnan(v) or math.isinf(v):
            raise ValueError(f"Valor flotante no finito inválido: {v}")


def build_telemetry_payload(
    azimuth_deg: float,
    elevation_deg: float,
    distance_nm: float,
    op_status: int,
) -> bytes:
    """Empaqueta payload de telemetría radar (13 bytes)."""
    _validate_finite_floats(azimuth_deg, elevation_deg, distance_nm)
    return struct.pack(
        PAYLOAD_FMT_TELEMETRY, azimuth_deg, elevation_deg, distance_nm, op_status
    )


def parse_telemetry_payload(
    payload: bytes,
) -> tuple[float, float, float, int]:
    """Desempaqueta payload de telemetría radar → (azimuth, elevation, distance, status)."""
    if len(payload) < PAYLOAD_SIZE_TELEMETRY:
        raise InvalidPayloadLengthError(PAYLOAD_SIZE_TELEMETRY, len(payload))
    azimuth, elevation, distance, status = struct.unpack_from(
        PAYLOAD_FMT_TELEMETRY, payload
    )
    _validate_finite_floats(azimuth, elevation, distance)
    return azimuth, elevation, distance, status


def build_cmd_payload(azimuth_deg: float, elevation_deg: float) -> bytes:
    """Empaqueta payload de comando de posición (8 bytes)."""
    _validate_finite_floats(azimuth_deg, elevation_deg)
    return struct.pack(PAYLOAD_FMT_CMD, azimuth_deg, elevation_deg)


def parse_cmd_payload(payload: bytes) -> tuple[float, float]:
    """Desempaqueta payload de comando → (azimuth, elevation)."""
    if len(payload) < PAYLOAD_SIZE_CMD:
        raise InvalidPayloadLengthError(PAYLOAD_SIZE_CMD, len(payload))
    azimuth, elevation = struct.unpack_from(PAYLOAD_FMT_CMD, payload)
    _validate_finite_floats(azimuth, elevation)
    return azimuth, elevation


def build_ack_payload(
    azimuth_deg: float, elevation_deg: float, status: int
) -> bytes:
    """Empaqueta payload de ACK (9 bytes)."""
    _validate_finite_floats(azimuth_deg, elevation_deg)
    return struct.pack(PAYLOAD_FMT_ACK, azimuth_deg, elevation_deg, status)


def parse_ack_payload(payload: bytes) -> tuple[float, float, int]:
    """Desempaqueta payload de ACK → (azimuth, elevation, status)."""
    if len(payload) < PAYLOAD_SIZE_ACK:
        raise InvalidPayloadLengthError(PAYLOAD_SIZE_ACK, len(payload))
    azimuth, elevation, status = struct.unpack_from(PAYLOAD_FMT_ACK, payload)
    _validate_finite_floats(azimuth, elevation)
    return azimuth, elevation, status


def build_nack_payload(error_code: int) -> bytes:
    """Empaqueta payload de NACK con código de error (2 bytes)."""
    return struct.pack(PAYLOAD_FMT_NACK, error_code & 0xFFFF)


def parse_nack_payload(payload: bytes) -> int:
    """Desempaqueta payload de NACK → error_code."""
    if len(payload) < PAYLOAD_SIZE_NACK:
        raise InvalidPayloadLengthError(PAYLOAD_SIZE_NACK, len(payload))
    (error_code,) = struct.unpack_from(PAYLOAD_FMT_NACK, payload)
    return error_code
