"""Inyector de fallos en tramas tácticas para pruebas de robustez."""

from __future__ import annotations

import random
import struct
import time
from typing import Optional

from simulator.protocol import MIN_FRAME_SIZE


class FaultInjector:
    """Utilidades para corromper tramas binarias antes de su transmisión."""

    def __init__(
        self,
        seed: Optional[int] = None,
        drop_probability: float = 0.0,
        jitter_max_s: float = 0.0,
    ) -> None:
        self._rng: random.Random = random.Random(seed)
        self._drop_probability: float = max(0.0, min(1.0, drop_probability))
        self._jitter_max_s: float = max(0.0, jitter_max_s)

    @staticmethod
    def corrupt_checksum(frame_bytes: bytes) -> bytes:
        """Invierte los 2 bytes finales de checksum en la trama."""
        if len(frame_bytes) < MIN_FRAME_SIZE:
            raise ValueError(f"Trama demasiado corta para corromper: {len(frame_bytes)} bytes")
        data = bytearray(frame_bytes)
        original_cs: int = struct.unpack_from("!H", data, len(data) - 2)[0]
        corrupted_cs: int = (~original_cs) & 0xFFFF
        struct.pack_into("!H", data, len(data) - 2, corrupted_cs)
        return bytes(data)

    @staticmethod
    def corrupt_payload_len(frame_bytes: bytes, false_len: int = 0xFFFF) -> bytes:
        """Sobreescribe el campo PAYLOAD_LEN (offset 8) con un valor arbitrario."""
        if len(frame_bytes) < MIN_FRAME_SIZE:
            raise ValueError(f"Trama demasiado corta: {len(frame_bytes)} bytes")
        data = bytearray(frame_bytes)
        struct.pack_into("!H", data, 8, false_len & 0xFFFF)
        return bytes(data)

    @staticmethod
    def corrupt_sync_word(frame_bytes: bytes, bad_sync: int = 0xDEAD) -> bytes:
        """Sobreescribe los 2 bytes de SYNC iniciales con un valor inválido."""
        if len(frame_bytes) < 2:
            raise ValueError("Trama demasiado corta para corromper SYNC.")
        data = bytearray(frame_bytes)
        struct.pack_into("!H", data, 0, bad_sync & 0xFFFF)
        return bytes(data)

    @staticmethod
    def truncate_frame(frame_bytes: bytes, keep_bytes: int = 5) -> bytes:
        """Trunca la trama conservando solo keep_bytes."""
        return frame_bytes[:keep_bytes]

    def should_drop_packet(self) -> bool:
        """Determina según drop_probability si el paquete debe descartarse."""
        return self._rng.random() < self._drop_probability

    def add_jitter(self) -> None:
        """Introduce un retardo aleatorio en [0, jitter_max_s] si está configurado."""
        if self._jitter_max_s > 0.0:
            delay: float = self._rng.uniform(0.0, self._jitter_max_s)
            time.sleep(delay)
