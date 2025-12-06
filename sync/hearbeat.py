# sync/heartbeat.py
from __future__ import annotations
import threading
import time
from common.message import WireMessage, MessageHeader, ServiceId
from common.nid import NID
from common.message import encode_message
from common.security import SecurityContext
from .router import SinkRouter

class HeartbeatService:
    def __init__(self, router: SinkRouter, sec: SecurityContext, interval: float = 5.0):
        self.router = router
        self.sec = sec
        self.interval = interval
        self._running = False
        self._thread: threading.Thread | None = None
        self._counter = 0

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join()

    def _loop(self) -> None:
        while self._running:
            self._counter += 1
            hdr = MessageHeader(
                src=self.router.sink_nid,
                dst=self.router.sink_nid,
                service=ServiceId.HEARTBEAT,
                client_id=0,
                seq=self._counter,
            )
            counter_bytes = self._counter.to_bytes(4, "big")
            signature = self.sec.sign_heartbeat(self._counter)
            payload = counter_bytes + signature

            msg = WireMessage(header=hdr, payload=payload, mac=b"")
            # MAC is per-link; router will fill it when sending
            self.router.broadcast_heartbeat(msg)

            time.sleep(self.interval)
