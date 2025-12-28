# sync/main_sink.py
from __future__ import annotations

import time

from common.nid import NID
from common.bluetooth import BluetoothManager
from common.security import SecurityContext, CertAndKey

from .router import SinkRouter
from .heartbeat import HeartbeatService
from .inbox import InboxService
from .sink_ui import SinkUI  # new import


def load_sink_certs() -> SecurityContext:
    with open("certs/sink/sink.cert.pem", "rb") as f:
        cert_pem = f.read()
    with open("certs/sink/sink.key.pem", "rb") as f:
        key_pem = f.read()
    with open("certs/ca/ca.cert.pem", "rb") as f:
        ca_pem = f.read()
    return SecurityContext(CertAndKey(cert_pem=cert_pem, key_pem=key_pem), ca_pem)


def main() -> None:
    sink_nid = NID(bytes(16))  # reserved ID for sink

    bt = BluetoothManager(enable_server=True, adapter="hci0")
    sec = load_sink_certs()
    inbox = InboxService()

    router = SinkRouter(sink_nid=sink_nid, bt=bt, sec=sec, inbox=inbox)
    router.start()

    hb = HeartbeatService(router, sec, interval=5.0)
    hb.start()

    ui = SinkUI(router)
    print("[SINK] Running. Press Ctrl+C to stop.")

    try:
        ui.run()
    except KeyboardInterrupt:
        pass
    finally:
        hb.stop()
        router.stop()

if __name__ == "__main__":
    main()
