# common/bluetooth.py

import os
import threading
import subprocess
import socket

try:
    import bluetooth  # Only for discovery
    HAS_PYBLUEZ = True
except ImportError:
    HAS_PYBLUEZ = False

from dataclasses import dataclass
from typing import Dict, Callable, List

MessageCallback = Callable[[int, bytes], None]
LinkLossCallback = Callable[[int], None]  # link_id

RFCOMM_PORT = 3  # Canal SPP RFCOMM

@dataclass
class DeviceInfo:
    address: str
    name: str
    hop_count: int = -1

class BluetoothManager:
    def __init__(self, enable_server: bool = False, adapter: str = "hci0", is_sink: bool = False):
        self.enable_server = enable_server
        self.adapter = adapter
        self.is_sink = is_sink
        self.local_mac = self._get_mac_address()

        self._callback: MessageCallback | None = None
        self._next_link = 1
        self._sockets: Dict[int, socket.socket] = {}
        self._recv_threads: Dict[int, threading.Thread] = {}

        self._server_sock: socket.socket | None = None

        print(f"[BT] Initialized on adapter {self.adapter} ({self.local_mac})")

        # Set initial name
        if self.is_sink:
            initial_name = "SINK|0"
        else:
            initial_name = "MESH|-1" if not enable_server else "MESH|0"  # temporary until hop learned

        self.set_name(initial_name)
        print(f"[BT] Initial device name set to {initial_name}")

        if enable_server:
            try:
                subprocess.run(["hciconfig", self.adapter, "piscan"], check=True, capture_output=True)
                print(f"[BT] Set {self.adapter} to discoverable and scannable")
            except subprocess.CalledProcessError as e:
                print(f"[BT] Failed to set discoverable: {e.stderr.decode().strip()} (run with sudo?)")
            except Exception as e:
                print(f"[BT] Failed to set discoverable: {e}")

        self._on_link_loss: LinkLossCallback | None = None

    def set_link_loss_callback(self, callback: LinkLossCallback) -> None:
        self._on_link_loss = callback

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

    def set_name(self, name: str) -> None:
        try:
            result = subprocess.run(
                ["hciconfig", self.adapter, "name", name],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                print(f"[BT] Set device name to {name} on {self.adapter}")
            else:
                err_msg = result.stderr.strip() if result.stderr else "Unknown error"
                if "Operation not permitted" in err_msg:
                    print(f"[BT] Skipping name change: Operation not permitted (run with sudo?)")
                    print(f"    Error: {err_msg}")
                else:
                    print(f"[BT] Failed to set name: {err_msg}")
        except FileNotFoundError:
            print("[BT] hciconfig not found — skipping name change (normal on newer systems)")
        except Exception as e:
            print(f"[BT] Unexpected error setting name: {e}")

    def start(self, callback: MessageCallback):
        self._callback = callback

        if self.enable_server:
            self._server_sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
            self._server_sock.bind((self.local_mac, RFCOMM_PORT))
            self._server_sock.listen(1)
            t = threading.Thread(target=self._accept_loop, daemon=True)
            t.start()
            print(f"[BT] Server started on port {RFCOMM_PORT} bound to {self.local_mac}")
        else:
            print("[BT] Server disabled (client-only mode).")

    def _accept_loop(self):
        while True:
            try:
                client_sock, addr = self._server_sock.accept()
                address = addr[0].upper()  # Normalize
                link_id = self._next_link
                self._next_link += 1
                self._sockets[link_id] = client_sock
                print(f"[BT] Accepted connection from {address} on link {link_id}")
                t = threading.Thread(target=self._recv_loop, args=(link_id,), daemon=True)
                t.start()
                self._recv_threads[link_id] = t
            except Exception as e:
                print(f"[BT] Accept error: {e}")
                break

    def connect_to(self, address: str) -> int:
        address = address.upper()  # Normalize
        sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        sock.connect((address, RFCOMM_PORT))
        link_id = self._next_link
        self._next_link += 1
        self._sockets[link_id] = sock
        print(f"[BT] Connected on link {link_id} using {self.adapter}")
        t = threading.Thread(target=self._recv_loop, args=(link_id,), daemon=True)
        t.start()
        self._recv_threads[link_id] = t
        return link_id

    def scan_nearby(self) -> List[DeviceInfo]:
        if not HAS_PYBLUEZ:
            raise RuntimeError("[BT] PyBluez not installed — cannot scan devices")
        print(f"[BT] Scanning on adapter {self.adapter}...")
        raw = bluetooth.discover_devices(lookup_names=True)
        devices = []
        for addr, name in raw:
            addr = addr.upper()  # Normalize
            hop = -1
            if "|" in name:
                try:
                    hop = int(name.split("|")[1])
                except:
                    pass
            devices.append(DeviceInfo(address=addr, name=name, hop_count=hop))
        if not devices:
            print("[BT] No devices found — try running 'sudo hciconfig hci0 reset' or check sink visibility")
        return devices

    def send(self, link_id: int, data: bytes):
        sock = self._sockets.get(link_id)
        if not sock:
            # Don't spam error — just skip (heartbeat will retry next cycle)
            return
        try:
            sock.send(data)
        except OSError as e:
            print(f"[BT] Send error: {e}")
            if e.errno in (107, 14):  # ENOTCONN or EFAULT
                print(f"[BT] Treating send failure as link loss on {link_id}")
                if self._on_link_loss:
                    self._on_link_loss(link_id)
                self.disconnect(link_id)
        except Exception as e:
            print(f"[BT] Send error: {e}")

    def _recv_loop(self, link_id: int):
        sock = self._sockets.get(link_id)
        if not sock:
            return
        while link_id in self._sockets:
            try:
                data = sock.recv(4096)
                if not data:
                    print(f"[BT] Link {link_id}: closed by peer (empty recv)")
                    if self._on_link_loss:
                        self._on_link_loss(link_id)
                    self.disconnect(link_id)
                    return
                if self._callback:
                    self._callback(link_id, data)
            except OSError as e:
                if e.errno in (9, 107, 32, 104, 14):
                    print(f"[BT] Link {link_id}: socket closed ({e})")
                    if self._on_link_loss:
                        self._on_link_loss(link_id)
                    self.disconnect(link_id)
                    return
                else:
                    print(f"[BT] Temporary receive error on link {link_id}: {e}")
                    continue
            except Exception as e:
                print(f"[BT] Unexpected receive error on link {link_id}: {e}")
                if self._on_link_loss:
                    self._on_link_loss(link_id)
                self.disconnect(link_id)
                return

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

        # Join recv thread to stop it cleanly
        if link_id in self._recv_threads:
            t = self._recv_threads.pop(link_id)
            t.join(timeout=1.0)  # Wait up to 1s

        # Trigger link loss callback for cleanup
        if self._on_link_loss:
            self._on_link_loss(link_id)

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