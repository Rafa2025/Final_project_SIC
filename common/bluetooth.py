# common/bluetooth.py
import threading
import socket
import bluetooth  # PyBluez
from dataclasses import dataclass
from typing import Dict, Callable, List

MessageCallback = Callable[[int, bytes], None]


# Classic Bluetooth uses RFCOMM channels (SPP)
RFCOMM_PORT = 3  # professor uses channel 3 in examples

@dataclass
class DeviceInfo:
    address: str
    name: str
    hop_count: int = 255    # you can embed hop count in device name later


class BluetoothManager:
    """
    Bluetooth manager using PyBluez (Classic RFCOMM).
    Matches professor's code style 100%.
    """

    def __init__(self):
        self._callback: MessageCallback | None = None
        self._next_link = 1
        self._sockets: Dict[int, bluetooth.BluetoothSocket] = {}

        # Receiving threads for each connection
        self._recv_threads: Dict[int, threading.Thread] = {}

    # ---------------------------------------------------------------
    # START / STOP
    # ---------------------------------------------------------------
    def start(self, callback: MessageCallback):
        self._callback = callback
        print("[BT] Bluetooth Manager started (PyBluez Classic Mode)")

    def stop(self):
        print("[BT] Stopping Bluetooth Manager...")
        for link_id in list(self._sockets.keys()):
            self.disconnect(link_id)
        print("[BT] Manager stopped")

    # ---------------------------------------------------------------
    # DEVICE DISCOVERY  (matches professor's guide)
    # ---------------------------------------------------------------
    def scan_nearby(self) -> List[DeviceInfo]:
        print("[BT] Scanning for nearby Classic BT devices...")
        devices = bluetooth.discover_devices(lookup_names=True)

        results = []
        for addr, name in devices:
            # You can encode hop count inside name like: "NodeA|5"
            hop = 255
            if "|" in name:
                try:
                    hop = int(name.split("|")[1])
                except:
                    pass

            results.append(DeviceInfo(address=addr, name=name, hop_count=hop))

        return results

    # ---------------------------------------------------------------
    # CONNECT TO PEER (RFCOMM socket)
    # ---------------------------------------------------------------
    def connect_to(self, address: str) -> int:
        print(f"[BT] Connecting to {address} via RFCOMM...")

        sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)

        # Professor-style connect
        sock.connect((address, RFCOMM_PORT))

        link_id = self._next_link
        self._next_link += 1
        self._sockets[link_id] = sock

        print(f"[BT] Connected: link_id={link_id}")

        # Start receive thread
        t = threading.Thread(target=self._recv_loop, args=(link_id,), daemon=True)
        t.start()
        self._recv_threads[link_id] = t

        return link_id

    # ---------------------------------------------------------------
    # DISCONNECT
    # ---------------------------------------------------------------
    def disconnect(self, link_id: int):
        sock = self._sockets.get(link_id)
        if not sock:
            return

        print(f"[BT] Closing link {link_id}")
        try:
            sock.close()
        except:
            pass

        del self._sockets[link_id]

    # ---------------------------------------------------------------
    # SEND MESSAGE (raw bytes)
    # ---------------------------------------------------------------
    def send(self, link_id: int, data: bytes):
        sock = self._sockets.get(link_id)
        if not sock:
            print(f"[BT] ERROR: link {link_id} not found")
            return

        try:
            sock.send(data)
        except Exception as e:
            print(f"[BT] Send error: {e}")

    # ---------------------------------------------------------------
    # RECEIVE LOOP (per-connection)
    # ---------------------------------------------------------------
    def _recv_loop(self, link_id: int):
        sock = self._sockets[link_id]

        while True:
            try:
                data = sock.recv(4096)
                if not data:
                    print(f"[BT] Peer closed connection link {link_id}")
                    self.disconnect(link_id)
                    return

                if self._callback:
                    self._callback(link_id, data)

            except Exception as e:
                print(f"[BT] Receive error (link {link_id}): {e}")
                self.disconnect(link_id)
                return
