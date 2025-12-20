# common/bluetooth.py

import os
import threading
import subprocess
import bluetooth
from dataclasses import dataclass
from typing import Dict, Callable, List

MessageCallback = Callable[[int, bytes], None]

RFCOMM_PORT = 3  # SPP RFCOMM channel


@dataclass
class DeviceInfo:
    address: str
    name: str
    hop_count: int = 255


class BluetoothManager:
    """
    PyBluez Classic RFCOMM manager with multi-adapter support.
    Each instance binds to a specific Bluetooth adapter (hci0, hci1, ...).
    """

    def __init__(self, enable_server: bool = False, adapter: str = "hci0"):
        self.enable_server = enable_server
        self.adapter = adapter     # NEW
        self.local_mac = self._get_mac_address()  # NEW

        # Force PyBluez to use a specific adapter for scanning
        os.environ["BLUETOOTH_DEVICE"] = self.adapter

        self._callback: MessageCallback | None = None
        self._next_link = 1
        self._sockets: Dict[int, bluetooth.BluetoothSocket] = {}
        self._recv_threads: Dict[int, threading.Thread] = {}

        self._server_sock: bluetooth.BluetoothSocket | None = None

        print(f"[BT] Initialized on adapter {self.adapter} ({self.local_mac})")

    # ---------------------------------------------------------------
    # Utility: Get MAC address of selected adapter
    # ---------------------------------------------------------------
    def _get_mac_address(self) -> str:
        try:
            out = subprocess.check_output(["hciconfig", self.adapter]).decode()
            for line in out.splitlines():
                line = line.strip()
                if "BD Address:" in line:
                    return line.split()[2]
        except:
            pass
        raise RuntimeError(f"Cannot find MAC for {self.adapter}")

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
        print(f"[BT] Starting RFCOMM server on {self.adapter} ({self.local_mac})...")

        try:
            server_sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)

            # NEW: bind to a specific adapter via MAC
            server_sock.bind((self.local_mac, RFCOMM_PORT))

            server_sock.listen(1)
        except Exception as e:
            print(f"[BT] ERROR starting server: {e}")
            raise

        self._server_sock = server_sock
        print(f"[BT] RFCOMM server listening on channel {RFCOMM_PORT} @ {self.adapter}")

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
        print(f"[BT] Connecting via {self.adapter} ({self.local_mac}) to {address}...")

        sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)

        # NEW: bind outbound socket to adapter
        sock.bind((self.local_mac, 0))

        sock.connect((address, RFCOMM_PORT))

        link_id = self._next_link
        self._next_link += 1
        self._sockets[link_id] = sock

        print(f"[BT] Connected on link {link_id} using {self.adapter}")

        t = threading.Thread(target=self._recv_loop, args=(link_id,), daemon=True)
        t.start()
        self._recv_threads[link_id] = t

        return link_id

    # ================================================================
    # SCAN
    # ================================================================
    def scan_nearby(self) -> List[DeviceInfo]:
        print(f"[BT] Scanning on adapter {self.adapter}...")

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
