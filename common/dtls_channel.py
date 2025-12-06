# common/dtls_channel.py
from __future__ import annotations
from typing import Tuple

class DTLSChannel:
    """
    End-to-end DTLS between IoT node and Sink.
    You must integrate a DTLS library here and expose a simple API.
    """
    def __init__(self, is_server: bool, certfile: str, keyfile: str, cafile: str) -> None:
        self.is_server = is_server
        self.certfile = certfile
        self.keyfile = keyfile
        self.cafile = cafile
        # TODO: create DTLS socket/context

    def connect(self, addr: Tuple[str, int]) -> None:
        # TODO: client-side DTLS handshake
        pass

    def accept(self) -> None:
        # TODO: server-side wait & accept DTLS handshake
        pass

    def send(self, data: bytes) -> None:
        # TODO: dtls_sock.send(data)
        pass

    def recv(self, bufsize: int = 4096) -> bytes:
        # TODO: dtls_sock.recv(bufsize)
        return b""
