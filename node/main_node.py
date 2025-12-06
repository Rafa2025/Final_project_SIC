# node/main_node.py
from common.nid import NID
from common.bluetooth import BluetoothManager
from common.security import SecurityContext, CertAndKey
from .router import NodeRouter
from .ui import NodeUI

def load_certs(node_id: str) -> SecurityContext:
    with open(f"certs/{node_id}/device.cert.pem", "rb") as f:
        cert_pem = f.read()
    with open(f"certs/{node_id}/device.key.pem", "rb") as f:
        key_pem = f.read()
    with open("certs/ca/ca.cert.pem", "rb") as f:
        ca_pem = f.read()
    return SecurityContext(CertAndKey(cert_pem=cert_pem, key_pem=key_pem), ca_pem)

def main():
    # For demo, derive NID from node_id hex or random
    # In practice, should match cert subject CN.
    node_id_hex = "0102030405060708090a0b0c0d0e0f10"
    my_nid = NID.from_hex(node_id_hex)

    bt = BluetoothManager()
    sec = load_certs(node_id_hex)
    router = NodeRouter(my_nid=my_nid, bt=bt, sec=sec)
    router.start()

    ui = NodeUI(router)
    try:
        ui.run()
    finally:
        router.stop()

if __name__ == "__main__":
    main()
