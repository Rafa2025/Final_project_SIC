# common/bluetooth.py

import threading
import bluetooth
from dataclasses import dataclass
from typing import Dict, Callable, List

MessageCallback = Callable[[int, bytes], None]

RFCOMM_PORT = 3   # SPP RFCOMM channel

@dataclass
class DeviceInfo:
    address: str
    name: str
    hop_count: int = 255


class BluetoothManager:
    """
    PyBluez Classic RFCOMM manager.
    Sink = server
    Nodes = clients only
    """

    def __init__(self, enable_server: bool = False):
        self.enable_server = enable_server
        self._callback: MessageCallback | None = None

        self._next_link = 1
        self._sockets: Dict[int, bluetooth.BluetoothSocket] = {}
        self._recv_threads: Dict[int, threading.Thread] = {}

        self._server_sock: bluetooth.BluetoothSocket | None = None

    # ================================================================
    # START
    # ================================================================
    def start(self, callback: MessageCallback):
        self._callback = callback

        if self.enable_server:
            self.start_server()
        else:
            print("[BT] Server disabled (client-only mode).")

    # ================================================================
    # SERVER (Sink only)
    # ================================================================
    def start_server(self):
        print("[BT] Starting RFCOMM server...")

        try:
            server_sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
            server_sock.bind(("", RFCOMM_PORT))
            server_sock.listen(1)
        except Exception as e:
            print(f"[BT] ERROR starting server: {e}")
            raise

        self._server_sock = server_sock
        print(f"[BT] RFCOMM server listening on channel {RFCOMM_PORT}")

        t = threading.Thread(target=self._accept_loop, daemon=True)
        t.start()

    def _accept_loop(self):
        server = self._server_sock
        while True:
            try:
                client_sock, addr = server.accept()
                print(f"[BT] Incoming connection from {addr}")

                link_id = self._next_link
                self._next_link += 1
                self._sockets[link_id] = client_sock

                t = threading.Thread(target=self._recv_loop, args=(link_id,), daemon=True)
                t.start()
                self._recv_threads[link_id] = t

            except Exception as e:
                print(f"[BT] Server accept failed: {e}")
                return

    # ================================================================
    # CLIENT MODE (Nodes)
    # ================================================================
    def connect_to(self, address: str) -> int:
        print(f"[BT] Connecting to {address} via RFCOMM...")

        sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        sock.connect((address, RFCOMM_PORT))

        link_id = self._next_link
        self._next_link += 1
        self._sockets[link_id] = sock

        print(f"[BT] Connected on link {link_id}")

        t = threading.Thread(target=self._recv_loop, args=(link_id,), daemon=True)
        t.start()
        self._recv_threads[link_id] = t

        return link_id

    # ================================================================
    # SCAN
    # ================================================================
    def scan_nearby(self) -> List[DeviceInfo]:
        print("[BT] Scanning for nearby BT devices...")
        raw = bluetooth.discover_devices(lookup_names=True)

        devices = []
        for addr, name in raw:
            hop = 255
            if "|" in name:
                try:
                    hop = int(name.split("|")[1])
                except:
                    pass
            devices.append(DeviceInfo(address=addr, name=name, hop_count=hop))

        return devices

    # ================================================================
    # SEND
    # ================================================================
    def send(self, link_id: int, data: bytes):
        sock = self._sockets.get(link_id)
        if not sock:
            print(f"[BT] ERROR: link {link_id} not found")
            return

        try:
            sock.send(data)
        except Exception as e:
            print(f"[BT] Send error: {e}")

    # ================================================================
    # RECEIVE LOOP
    # ================================================================
    def _recv_loop(self, link_id: int):
        sock = self._sockets[link_id]
        while True:
            try:
                data = sock.recv(4096)
                if not data:
                    print(f"[BT] Link {link_id}: closed by peer")
                    self.disconnect(link_id)
                    return

                if self._callback:
                    self._callback(link_id, data)

            except Exception as e:
                print(f"[BT] Receive error on link {link_id}: {e}")
                self.disconnect(link_id)
                return

    # ================================================================
    # DISCONNECT
    # ================================================================
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

    # ================================================================
    # STOP
    # ================================================================
    def stop(self):
        print("[BT] Stopping Bluetooth Manager...")

        for lid in list(self._sockets.keys()):
            self.disconnect(lid)

        if self._server_sock:
            try:
                self._server_sock.close()
            except:
                pass

        print("[BT] Manager stopped")
