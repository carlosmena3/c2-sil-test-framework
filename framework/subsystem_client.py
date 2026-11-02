"""Cliente de automatización para envío de estímulos y polling de estado en tests."""

from __future__ import annotations

import logging
import socket
import time
from typing import Callable, Optional, TypeVar

from simulator.protocol import TacticalFrame
from simulator.transport import LOOPBACK, MAX_DATAGRAM_SIZE

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_POLL_TIMEOUT_S: float = 2.0
POLL_INTERVAL_S: float = 0.005


class PollTimeoutError(Exception):
    """Excepción lanzada si expira el tiempo de espera en una condición."""

    def __init__(self, description: str, timeout_s: float) -> None:
        super().__init__(f"Timeout ({timeout_s:.3f}s) esperando: {description}")


class SubsystemClient:
    """Cliente para inyectar tramas UDP y capturar respuestas en los tests."""

    def __init__(
        self,
        listen_port: int,
        listen_host: str = LOOPBACK,
        recv_timeout_s: float = 0.1,
    ) -> None:
        self._listen_port: int = listen_port
        self._listen_host: str = listen_host
        self._recv_timeout_s: float = recv_timeout_s
        self._sender_sock: Optional[socket.socket] = None

    def open(self) -> None:
        """Abre el socket UDP de envío."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sender_sock = sock

    def close(self) -> None:
        """Cierra el socket de envío."""
        if self._sender_sock is not None:
            self._sender_sock.close()
            self._sender_sock = None

    def __enter__(self) -> SubsystemClient:
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def send_frame(self, frame: TacticalFrame, dest_host: str, dest_port: int) -> None:
        """Serializa y envía una trama táctica al subsistema destino."""
        if self._sender_sock is None:
            raise RuntimeError("SubsystemClient no está abierto.")
        raw = frame.serialize()
        self._sender_sock.sendto(raw, (dest_host, dest_port))

    def send_raw(self, data: bytes, dest_host: str, dest_port: int) -> None:
        """Envía bytes raw al subsistema destino."""
        if self._sender_sock is None:
            raise RuntimeError("SubsystemClient no está abierto.")
        self._sender_sock.sendto(data, (dest_host, dest_port))

    def measure_rtt_ms(
        self,
        frame: TacticalFrame,
        dest_host: str,
        dest_port: int,
        listen_port: int,
        timeout_s: float = 1.0,
    ) -> float:
        """Envía una trama y mide el tiempo hasta la primera respuesta UDP en milisegundos."""
        listen_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listen_sock.settimeout(timeout_s)
        listen_sock.bind((self._listen_host, listen_port))
        try:
            raw = frame.serialize()
            t_send = time.monotonic()
            if self._sender_sock is None:
                raise RuntimeError("SubsystemClient no está abierto.")
            self._sender_sock.sendto(raw, (dest_host, dest_port))
            listen_sock.recvfrom(MAX_DATAGRAM_SIZE)
            t_recv = time.monotonic()
            return (t_recv - t_send) * 1000.0
        except socket.timeout as exc:
            raise TimeoutError(f"Sin respuesta en {timeout_s}s al medir RTT") from exc
        finally:
            listen_sock.close()

    @staticmethod
    def wait_for(
        condition: Callable[[], bool],
        description: str = "condición",
        timeout_s: float = DEFAULT_POLL_TIMEOUT_S,
    ) -> None:
        """Espera por polling hasta que condition() sea True o venza el timeout."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(POLL_INTERVAL_S)
        raise PollTimeoutError(description, timeout_s)

    @staticmethod
    def wait_for_value(
        getter: Callable[[], T],
        predicate: Callable[[T], bool],
        description: str = "valor",
        timeout_s: float = DEFAULT_POLL_TIMEOUT_S,
    ) -> T:
        """Espera hasta que predicate(getter()) sea True y devuelve el valor obtenido."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            value = getter()
            if predicate(value):
                return value
            time.sleep(POLL_INTERVAL_S)
        raise PollTimeoutError(description, timeout_s)
