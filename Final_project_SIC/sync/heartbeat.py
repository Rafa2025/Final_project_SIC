# sync/heartbeat.py
from __future__ import annotations

import threading
import time

from common.message import WireMessage, MessageHeader, ServiceId
from common.nid import NID
from common.security import SecurityContext
from .router import SinkRouter


class HeartbeatService:
    def __init__(self, router: SinkRouter, sec: SecurityContext, interval: float = 5.0):
        self.router = router
        self.sec = sec
        self.interval = interval
        self.running = False
        self.thread: threading.Thread | None = None
        self.counter = 0

    def start(self) -> None:
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.running = False

    def _loop(self) -> None:
        while self.running:
            self.counter += 1

            hdr = MessageHeader(
                src=self.router.sink_nid,
                dst=self.router.sink_nid,
                service=ServiceId.HEARTBEAT,
                client_id=0,
                seq=self.counter,
            )

            counter_bytes = self.counter.to_bytes(4, "big")
            signature = self.sec.sign_heartbeat(self.counter)
            payload = counter_bytes + signature

            msg = WireMessage(header=hdr, payload=payload, mac=b"")

            self.router.broadcast_heartbeat(msg)
            time.sleep(self.interval)
