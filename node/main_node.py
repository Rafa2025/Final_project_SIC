# node/main_node.py

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

from common.nid import NID
from common.bluetooth import BluetoothManager
from common.security import SecurityContext, CertAndKey
from .router import NodeRouter
from .ui import NodeUI


def load_security(nid_hex: str) -> tuple[SecurityContext, bytes]:
    """
    Load device cert/key, CA cert, and Sink cert.
    Expects files:
      certs/ca/ca.cert.pem
      certs/<nid_hex>/device.cert.pem
      certs/<nid_hex>/device.key.pem
      certs/sink/sink.cert.pem
    """
    base = Path("certs")

    ca_pem = (base / "ca" / "ca.cert.pem").read_bytes()
    dev_cert = (base / nid_hex / "device.cert.pem").read_bytes()
    dev_key = (base / nid_hex / "device.key.pem").read_bytes()
    sink_cert = (base / "sink" / "sink.cert.pem").read_bytes()

    sec = SecurityContext(
        device=CertAndKey(cert_pem=dev_cert, key_pem=dev_key),
        ca_pem=ca_pem,
    )
    return sec, sink_cert


def main() -> None:
    if len(sys.argv) >= 2:
        nid_hex = sys.argv[1].strip().lower()
        my_nid = NID.from_hex(nid_hex)
    else:
        my_nid = NID.random()
        nid_hex = my_nid.to_hex()
        print(f"[NODE] No NID provided on command line, using random NID: {nid_hex}")

    try:
        sec, sink_cert_pem = load_security(nid_hex)
    except FileNotFoundError as e:
        print(f"[NODE] Certificate file missing: {e}")
        print("       Make sure you ran the CA and device cert generation scripts.")
        sys.exit(1)

    bt = BluetoothManager(enable_server=False)
    router = NodeRouter(my_nid=my_nid, bt=bt, sec=sec, sink_cert_pem=sink_cert_pem)
    router.start()

    # Background thread to handle heartbeat timeouts
    running = True

    def heartbeat_thread():
        while running:
            router.tick(heartbeat_timeout=15.0)
            time.sleep(1.0)

    t = threading.Thread(target=heartbeat_thread, daemon=True)
    t.start()

    ui = NodeUI(router)
    try:
        ui.run()
    finally:
        running = False
        router.stop()


if __name__ == "__main__":
    main()
