# common/bluetooth.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Dict, List
from .message import WireMessage

MessageCallback = Callable[[int, WireMessage], None]

@dataclass
class DeviceInfo:
    address: str
    hop_count: int  # advertised by peers

class BluetoothManager:
    """
    Abstraction over BLE (e.g., using Bleak).
    For the project, you must implement the TODOs with real BLE.
    """
    def __init__(self) -> None:
        self._callback: MessageCallback | None = None
        self._next_link_id = 1
        self._links: Dict[int, str] = {}  # link_id -> address

    def start(self, callback: MessageCallback) -> None:
        self._callback = callback
        # TODO: start BLE advertising + GATT server to receive writes,
        # and a client role to connect to others.

    def stop(self) -> None:
        # TODO: cleanly close BLE resources
        pass

    def scan_nearby(self) -> List[DeviceInfo]:
        # TODO: use bleak.BleakScanner to discover devices
        # and parse custom advertising data including hop_count.
        return []

    def connect_to(self, address: str) -> int:
        # TODO: use BleakClient or similar to connect & maintain a mapping
        link_id = self._next_link_id
        self._next_link_id += 1
        self._links[link_id] = address
        return link_id

    def disconnect(self, link_id: int) -> None:
        # TODO: disconnect from BLE peer
        self._links.pop(link_id, None)

    def send(self, link_id: int, msg: WireMessage) -> None:
        # TODO:
        # 1. encode message (without mac)
        # 2. your higher layer should already fill mac
        # 3. send via BLE characteristic write
        if link_id not in self._links:
            return
        # bleak_client.write_gatt_char(...)

    # This should be called by your BLE receive handler:
    def _on_raw_bytes(self, link_id: int, buf: bytes, mac: bytes) -> None:
        from .message import decode_message
        if not self._callback:
            return
        msg = decode_message(buf, mac)
        self._callback(link_id, msg)
