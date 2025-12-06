# common/dtls_channel.py

from __future__ import annotations
from typing import Optional, Tuple
import socket
import ssl


class DTLSChannel:
    """
    Simple TLS-over-TCP channel placeholder for the 'DTLS' API.
    In your report you can explain that this is used to emulate DTLS
    semantics for the lab.

    If you later install a proper DTLS library, you can swap the
    internals here and keep the same API for the rest of the code.
    """

    def __init__(
        self,
        is_server: bool,
        certfile: str,
        keyfile: str,
        cafile: Optional[str] = None,
    ) -> None:
        self.is_server = is_server
        self.certfile = certfile
        self.keyfile = keyfile
        self.cafile = cafile

        self._sock: Optional[socket.socket] = None
        self._ssl_sock: Optional[ssl.SSLSocket] = None

    def _create_context(self) -> ssl.SSLContext:
        if self.is_server:
            ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ctx.load_cert_chain(certfile=self.certfile, keyfile=self.keyfile)
            if self.cafile:
                ctx.load_verify_locations(self.cafile)
                ctx.verify_mode = ssl.CERT_REQUIRED
        else:
            ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            if self.cafile:
                ctx.load_verify_locations(self.cafile)
            ctx.load_cert_chain(certfile=self.certfile, keyfile=self.keyfile)
        return ctx

    # ------------------------------------------------------------------
    # Server side
    # ------------------------------------------------------------------

    def bind_and_listen(self, addr: Tuple[str, int], backlog: int = 5) -> None:
        if not self.is_server:
            raise RuntimeError("bind_and_listen called on client DTLSChannel")

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind(addr)
        self._sock.listen(backlog)

    def accept(self) -> None:
        if self._sock is None:
            raise RuntimeError("Server socket not bound/listening")

        raw_client, _ = self._sock.accept()
        ctx = self._create_context()
        self._ssl_sock = ctx.wrap_socket(raw_client, server_side=True)

    # ------------------------------------------------------------------
    # Client side
    # ------------------------------------------------------------------

    def connect(self, addr: Tuple[str, int]) -> None:
        if self.is_server:
            raise RuntimeError("connect called on server DTLSChannel")

        raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw_sock.connect(addr)
        ctx = self._create_context()
        self._ssl_sock = ctx.wrap_socket(raw_sock, server_hostname=addr[0])

    # ------------------------------------------------------------------
    # Common
    # ------------------------------------------------------------------

    def send(self, data: bytes) -> None:
        if self._ssl_sock is None:
            raise RuntimeError("DTLS/TLS socket not connected")
        self._ssl_sock.sendall(data)

    def recv(self, bufsize: int = 4096) -> bytes:
        if self._ssl_sock is None:
            raise RuntimeError("DTLS/TLS socket not connected")
        return self._ssl_sock.recv(bufsize)

    def close(self) -> None:
        if self._ssl_sock:
            try:
                self._ssl_sock.close()
            except Exception:
                pass
            self._ssl_sock = None

        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
