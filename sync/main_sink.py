# sync/main_sink.py
from common.nid import NID
from common.bluetooth import BluetoothManager
from common.security import SecurityContext, CertAndKey
from .router import SinkRouter
from .heartbeat import HeartbeatService
from .inbox import InboxService

def load_sink_certs() -> SecurityContext:
    with open("certs/sink/sink.cert.pem", "rb") as f:
        cert_pem = f.read()
    with open("certs/sink/sink.key.pem", "rb") as f:
        key_pem = f.read()
    with open("certs/ca/ca.cert.pem", "rb") as f:
        ca_pem = f.read()
    return SecurityContext(CertAndKey(cert_pem=cert_pem, key_pem=key_pem), ca_pem)

def main():
    sink_nid = NID(bytes(16))  # reserved
    bt = BluetoothManager()
    sec = load_sink_certs()
    inbox = InboxService()
    router = SinkRouter(sink_nid=sink_nid, bt=bt, sec=sec, inbox=inbox)
    router.start()

    hb = HeartbeatService(router=router, sec=sec, interval=5.0)
    hb.start()

    try:
        print("Sink running. Press Ctrl+C to exit.")
        while True:
            # For now just keep process alive.
            # You could add a small CLI menu to inspect inbox, routes, etc.
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        hb.stop()
        router.stop()

if __name__ == "__main__":
    main()
# sync/main_sink.py
from common.nid import NID
from common.bluetooth import BluetoothManager
from common.security import SecurityContext, CertAndKey
from .router import SinkRouter
from .heartbeat import HeartbeatService
from .inbox import InboxService

def load_sink_certs() -> SecurityContext:
    with open("certs/sink/sink.cert.pem", "rb") as f:
        cert_pem = f.read()
    with open("certs/sink/sink.key.pem", "rb") as f:
        key_pem = f.read()
    with open("certs/ca/ca.cert.pem", "rb") as f:
        ca_pem = f.read()
    return SecurityContext(CertAndKey(cert_pem=cert_pem, key_pem=key_pem), ca_pem)

def main():
    sink_nid = NID(bytes(16))  # reserved
    bt = BluetoothManager()
    sec = load_sink_certs()
    inbox = InboxService()
    router = SinkRouter(sink_nid=sink_nid, bt=bt, sec=sec, inbox=inbox)
    router.start()

    hb = HeartbeatService(router=router, sec=sec, interval=5.0)
    hb.start()

    try:
        print("Sink running. Press Ctrl+C to exit.")
        while True:
            # For now just keep process alive.
            # You could add a small CLI menu to inspect inbox, routes, etc.
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        hb.stop()
        router.stop()

if __name__ == "__main__":
    main()
