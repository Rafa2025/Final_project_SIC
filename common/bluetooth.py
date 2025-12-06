# common/bluetooth.py

import threading
import bluetooth  # PyBluez or pybluez2
from dataclasses import dataclass
from typing import Dict, Callable, List, Optional

MessageCallback = Callable[[int, bytes], None]

# Classic Bluetooth uses RFCOMM channels (SPP)
RFCOMM_PORT = 3  # you can change if you want

@dataclass
class DeviceInfo:
    address: str
    name: str
    hop_count: int = 255  # you can embed hop count in device name later


class BluetoothManager:
    """
    Bluetooth manager using PyBluez (Classic RFCOMM).
    Provides:
        - scanning
        - client connect/disconnect/send
        - server listener accepting incoming connections
        - per-link receive threads calling a callback
    """

    def __init__(self):
        self._callback: Optional[MessageCallback] = None
        self._next_link = 1

        # link_id -> BluetoothSocket
        self._sockets: Dict[int, bluetooth.BluetoothSocket] = {}

        # link_id -> receive thread
        self._recv_threads: Dict[int, threading.Thread] = {}

        # Server state
        self._server_sock: Optional[bluetooth.BluetoothSocket] = None
        self._server_thread: Optional[threading.Thread] = None
        self._server_running = False

    # ---------------------------------------------------------------
    # START / STOP
    # ---------------------------------------------------------------
    def start(self, callback: MessageCallback):
        self._callback = callback
        print("[BT] Bluetooth Manager started (PyBluez Classic Mode)")

    def stop(self):
        print("[BT] Stopping Bluetooth Manager...")

        # Stop server listener
        self._server_running = False
        if self._server_sock is not None:
            try:
                self._server_sock.close()
            except Exception:
                pass
            self._server_sock = None

        # Close all client sockets
        for link_id in list(self._sockets.keys()):
            self.disconnect(link_id)

        print("[BT] Manager stopped")

    # ---------------------------------------------------------------
    # DEVICE DISCOVERY  (matches professor's guide)
    # ---------------------------------------------------------------
    def scan_nearby(self) -> List[DeviceInfo]:
        print("[BT] Scanning for nearby Classic BT devices...")
        devices = bluetooth.discover_devices(lookup_names=True)

        results: List[DeviceInfo] = []
        for addr, name in devices:
            hop = 255
            if "|" in name:
                try:
                    hop = int(name.split("|")[1])
                except Exception:
                    pass

            results.append(DeviceInfo(address=addr, name=name, hop_count=hop))

        return results

    # ---------------------------------------------------------------
    # SERVER LISTENER (accept incoming RFCOMM connections)
    # ---------------------------------------------------------------
    def start_server(self, port: int = RFCOMM_PORT):
        """
        Start an RFCOMM server listening on the given port.
        Accepts connections in a background thread and allocates
        new link_ids for each.
        """
        if self._server_running:
            print("[BT] Server already running")
            return

        server_sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        server_sock.bind(("", port))
        server_sock.listen(1)
        self._server_sock = server_sock
        self._server_running = True

        print(f"[BT] RFCOMM server listening on channel {port}")

        t = threading.Thread(target=self._accept_loop, daemon=True)
        t.start()
        self._server_thread = t

    def _accept_loop(self):
        assert self._server_sock is not None
        while self._server_running:
            try:
                client_sock, client_info = self._server_sock.accept()
                addr = client_info[0] if isinstance(client_info, tuple) else str(client_info)
                link_id = self._next_link
                self._next_link += 1

                self._sockets[link_id] = client_sock
                print(f"[BT] Accepted connection from {addr} as link {link_id}")

                t = threading.Thread(target=self._recv_loop, args=(link_id,), daemon=True)
                t.start()
                self._recv_threads[link_id] = t
            except Exception as e:
                if self._server_running:
                    print(f"[BT] Accept error: {e}")
                break

    # ---------------------------------------------------------------
    # CONNECT TO PEER (CLIENT)
    # ---------------------------------------------------------------
    def connect_to(self, address: str) -> int:
        print(f"[BT] Connecting to {address} via RFCOMM...")

        sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        sock.connect((address, RFCOMM_PORT))

        link_id = self._next_link
        self._next_link += 1
        self._sockets[link_id] = sock

        print(f"[BT] Connected: link_id={link_id}")

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
        except Exception:
            pass

        self._sockets.pop(link_id, None)
        self._recv_threads.pop(link_id, None)

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
            print(f"[BT] Send error on link {link_id}: {e}")
            self.disconnect(link_id)

    # ---------------------------------------------------------------
    # RECEIVE LOOP (per-connection)
    # ---------------------------------------------------------------
    def _recv_loop(self, link_id: int):
        sock = self._sockets.get(link_id)
        if sock is None:
            return

        while True:
            try:
                data = sock.recv(4096)
                if not data:
                    print(f"[BT] Peer closed connection on link {link_id}")
                    self.disconnect(link_id)
                    return

                if self._callback:
                    self._callback(link_id, data)

            except Exception as e:
                print(f"[BT] Receive error (link {link_id}): {e}")
                self.disconnect(link_id)
                return
