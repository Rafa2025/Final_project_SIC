# common/dtls_channel.py (corrected for RFCOMM/TLS)

import os
import socket
import ssl
from typing import Optional, Tuple

class DTLSChannel:
    """
    Emulated DTLS using TLS over RFCOMM (stream socket).
    Works with Bluetooth RFCOMM sockets.
    """

    def __init__(
        self,
        is_server: bool,
        certfile: str,
        keyfile: str,
        cafile: str,
    ) -> None:
        self.is_server = is_server
        self.certfile = certfile
        self.keyfile = keyfile
        self.cafile = cafile

        self._context = self._create_context()
        self._tls_conn: Optional[ssl.SSLObject] = None
        self._raw_sock: Optional[socket.socket] = None

    def _create_context(self) -> ssl.SSLContext:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT if not self.is_server else ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=self.certfile, keyfile=self.keyfile)
        ctx.load_verify_locations(cafile=self.cafile)
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.check_hostname = False
        return ctx

    def connect(self, raw_sock) -> None:
        """Wrap an already connected RFCOMM socket with TLS."""
        if self.is_server:
            raise RuntimeError("connect only on client")

        # PyBluez BluetoothSocket doesn't implement .detach() (needed by ssl in py3.12).
        # Convert to a real socket.socket using a dup()'d fd.
        if isinstance(raw_sock, socket.socket):
            std_sock = raw_sock
        else:
            fd = raw_sock.fileno()
            dup_fd = os.dup(fd)
            std_sock = socket.socket(fileno=dup_fd)

        std_sock.setblocking(True)

        self._raw_sock = std_sock
        self._tls_conn = self._context.wrap_socket(std_sock, server_hostname="localhost")

    def send(self, data: bytes) -> None:
        if self._tls_conn is None:
            raise RuntimeError("DTLS not connected")
        self._tls_conn.sendall(data)

    def recv(self, bufsize: int = 4096) -> bytes:
        if self._tls_conn is None:
            raise RuntimeError("DTLS not connected")
        return self._tls_conn.recv(bufsize)

    def close(self) -> None:
        if self._tls_conn:
            self._tls_conn.close()
        if self._raw_sock:
            self._raw_sock.close()