"""Capa de transporte UDP para la comunicación entre subsistemas."""

from __future__ import annotations

import logging
import socket
from typing import Optional

logger = logging.getLogger(__name__)

MAX_DATAGRAM_SIZE: int = 4096
LOOPBACK: str = "127.0.0.1"


class UDPTransport:
    """Transporte UDP no bloqueante con timeout configurable."""

    def __init__(
        self,
        bind_port: int,
        bind_host: str = LOOPBACK,
        recv_timeout_s: float = 0.05,
    ) -> None:
        self._bind_port: int = bind_port
        self._bind_host: str = bind_host
        self._recv_timeout_s: float = recv_timeout_s
        self._socket: Optional[socket.socket] = None

    def open(self) -> None:
        """Abre y enlaza el socket UDP local."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(self._recv_timeout_s)
        sock.bind((self._bind_host, self._bind_port))
        self._socket = sock

    def close(self) -> None:
        """Cierra el socket y libera el puerto."""
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None

    def __enter__(self) -> UDPTransport:
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def send_to(self, host: str, port: int, data: bytes) -> None:
        """Envía un datagrama UDP a la dirección indicada."""
        if self._socket is None:
            raise RuntimeError("UDPTransport no está abierto.")
        self._socket.sendto(data, (host, port))

    def recv(self) -> Optional[tuple[bytes, tuple[str, int]]]:
        """Recibe un datagrama o devuelve None si expira el timeout."""
        if self._socket is None:
            raise RuntimeError("UDPTransport no está abierto.")
        try:
            data, addr = self._socket.recvfrom(MAX_DATAGRAM_SIZE)
            return data, addr
        except (socket.timeout, BlockingIOError, ConnectionResetError):
            return None

    @property
    def bind_port(self) -> int:
        return self._bind_port

    @property
    def is_open(self) -> bool:
        return self._socket is not None
