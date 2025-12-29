# node/router.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
import time
import threading

from common.nid import NID
from common.bluetooth import BluetoothManager, DeviceInfo
from common.routing import RoutingTable
from common.message import (
    WireMessage,
    MessageHeader,
    ServiceId,
    encode_message,
    decode_message,
    split_packet,
)
from common.security import SecurityContext


# By convention, all-zero NID = Sink
SINK_NID = NID(b"\x00" * 16)


# ----------------------------------------------------------------------
# LinkState — tracks per-link information
# ----------------------------------------------------------------------
@dataclass
class LinkState:
    is_uplink: bool
    peer_nid: NID | None = None
    peer_hop_count: int = 255


# ----------------------------------------------------------------------
# Node Router
# ----------------------------------------------------------------------
@dataclass
class NodeRouter:
    my_nid: NID
    bt: BluetoothManager
    sec: SecurityContext
    sink_cert_pem: bytes

    routing: RoutingTable = field(default_factory=RoutingTable)

    # FIX: This field was missing!
    links: dict[int, LinkState] = field(default_factory=dict)

    uplink_link_id: Optional[int] = None
    hop_count: int = 255  # unknown

    routed_count: int = 0
    lost_heartbeats: int = 0
    last_heartbeat_ts: float = field(default_factory=lambda: 0.0)

    inbox_messages: List[tuple[NID, str]] = field(default_factory=list)

    _next_seq: int = 0

    # Heartbeat service fields
    _heartbeat_running: bool = False
    _heartbeat_thread: Optional[threading.Thread] = None
    _heartbeat_counter: int = 0
    _heartbeat_interval: float = 5.0  # seconds

    # ----------------------------------------------------------------------
    def start(self) -> None:
        self.bt.start(self.on_bt_data)
        self._start_heartbeat_service()
        print(f"[NODE {self.my_nid}] Router started with heartbeat service")

    def stop(self) -> None:
        self._stop_heartbeat_service()
        self.bt.stop()
        print(f"[NODE {self.my_nid}] Router stopped")

    # ========================================================================
    # HEARTBEAT SERVICE
    # ========================================================================
    def _start_heartbeat_service(self) -> None:
        """Start the heartbeat service thread for this node."""
        self._heartbeat_running = True
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name=f"HeartbeatService-{self.my_nid}"
        )
        self._heartbeat_thread.start()
        print(f"[NODE {self.my_nid}] Heartbeat service started (interval={self._heartbeat_interval}s)")

    def _stop_heartbeat_service(self) -> None:
        """Stop the heartbeat service thread."""
        self._heartbeat_running = False
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=2.0)
        print(f"[NODE {self.my_nid}] Heartbeat service stopped")

    def _heartbeat_loop(self) -> None:
        """Periodically send heartbeat messages to the sink."""
        while self._heartbeat_running:
            try:
                # Only send heartbeats if we have a valid uplink
                if self.uplink_link_id is not None and self.uplink_link_id in self.bt._sockets:
                    self._send_heartbeat()
                time.sleep(self._heartbeat_interval)
            except Exception as e:
                print(f"[NODE {self.my_nid}] Heartbeat error: {e}")
                time.sleep(self._heartbeat_interval)

    def _send_heartbeat(self) -> None:
        """Send a heartbeat message to the sink."""
        self._heartbeat_counter += 1

        hdr = MessageHeader(
            src=self.my_nid,
            dst=SINK_NID,
            service=ServiceId.HEARTBEAT,
            client_id=0,
            seq=self._next_seq_num(),
        )

        counter_bytes = self._heartbeat_counter.to_bytes(4, "big")
        signature = self.sec.sign_heartbeat(self._heartbeat_counter)
        payload = counter_bytes + signature

        msg = WireMessage(header=hdr, payload=payload, mac=b"")

        try:
            if self.uplink_link_id is not None:
                self._send_on_link(self.uplink_link_id, msg)
        except Exception as e:
            print(f"[NODE {self.my_nid}] Failed to send heartbeat: {e}")

    # ========================================================================
    def on_bt_data(self, link_id: int, packet: bytes) -> None:
        try:
            raw, mac = split_packet(packet, mac_len=32)
        except ValueError as e:
            print(f"[NODE {self.my_nid}] malformed packet: {e}")
            return

        if not self.sec.verify_mac(link_id, raw, mac):
            print(f"[NODE {self.my_nid}] MAC failed on link {link_id}")
            return

        try:
            msg = decode_message(raw, mac)
        except Exception as e:
            print(f"[NODE {self.my_nid}] decode error: {e}")
            return

        self.routing.learn(msg.header.src, link_id, hop_count=1)

        if msg.header.service == ServiceId.HEARTBEAT:
            self._handle_heartbeat(msg, link_id)
        elif msg.header.service == ServiceId.INBOX:
            self._handle_inbox(msg, link_id)
        else:
            self._forward(msg, link_id)

    # ----------------------------------------------------------------------
    # Heartbeat
    # ----------------------------------------------------------------------
    def _handle_heartbeat(self, msg: WireMessage, link_id: int) -> None:
        if len(msg.payload) < 4:
            return

        counter = int.from_bytes(msg.payload[:4], "big")
        signature = msg.payload[4:]

        if not SecurityContext.verify_heartbeat(counter, signature, self.sink_cert_pem):
            print(f"[NODE {self.my_nid}] bad heartbeat signature")
            return

        self.last_heartbeat_ts = time.monotonic()
        self.lost_heartbeats = 0

        if self.uplink_link_id is None:
            self.uplink_link_id = link_id
            self.hop_count = 1
            print(f"[NODE {self.my_nid}] Uplink established on link {link_id}")

        self._flood(msg, incoming_link=link_id)

    # ----------------------------------------------------------------------
    # Inbox
    # ----------------------------------------------------------------------
    def _handle_inbox(self, msg: WireMessage, incoming_link: int) -> None:
        if msg.header.dst == self.my_nid:
            text = msg.payload.decode(errors="ignore")
            self.inbox_messages.append((msg.header.src, text))
            print(f"[NODE {self.my_nid}] Inbox: {text}")
            return

        self._forward(msg, incoming_link)

    # ----------------------------------------------------------------------
    # Forwarding
    # ----------------------------------------------------------------------
    def _forward(self, msg: WireMessage, incoming_link: int) -> None:
        dst = msg.header.dst

        entry = self.routing.lookup(dst)
        if entry:
            out_link = entry.link
        elif dst == SINK_NID and self.uplink_link_id is not None:
            out_link = self.uplink_link_id
        else:
            return

        if out_link == incoming_link:
            return

        self._send_on_link(out_link, msg)
        self.routed_count += 1

    def _flood(self, msg: WireMessage, incoming_link: int) -> None:
        used = set()
        for entry in self.routing.snapshot().values():
            if entry.link == incoming_link:
                continue
            if entry.link in used:
                continue
            self._send_on_link(entry.link, msg)
            used.add(entry.link)

    # ----------------------------------------------------------------------
    # Sending helpers
    # ----------------------------------------------------------------------
    def _next_seq_num(self) -> int:
        self._next_seq = (self._next_seq + 1) & 0xFFFFFFFF
        return self._next_seq

    def _send_on_link(self, link_id: int, msg: WireMessage) -> None:
        raw = encode_message(msg)
        mac = self.sec.compute_mac(link_id, raw)
        packet = raw + mac
        self.bt.send(link_id, packet)

    # ----------------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------------
    def scan_and_connect_best(self) -> None:
        devices = self.bt.scan_nearby()
        if not devices:
            print("[NODE] No devices found")
            return

        best = min(devices, key=lambda d: d.hop_count)
        print(f"[NODE {self.my_nid}] Connecting to {best.address} ({best.name})")

        link_id = self.bt.connect_to(best.address)

        dummy_key = b"\x01" * 32
        self.sec.set_link_key(link_id, dummy_key)

        if self.uplink_link_id is None:
            self.uplink_link_id = link_id
            self.hop_count = (best.hop_count + 1) if best.hop_count < 255 else 2
            print(f"[NODE] Using link {link_id} as uplink")

    def send_inbox_message(self, text: str) -> None:
        if self.uplink_link_id is None:
            print("[NODE] No uplink, cannot send")
            return

        hdr = MessageHeader(
            src=self.my_nid,
            dst=SINK_NID,
            service=ServiceId.INBOX,
            client_id=1,
            seq=self._next_seq_num(),
        )
        msg = WireMessage(header=hdr, payload=text.encode(), mac=b"")

        self._send_on_link(self.uplink_link_id, msg)
        print("[NODE] Inbox message sent")

    # Heartbeat timeout
    # ========================================================================
    def tick(self, heartbeat_timeout: float = 30.0) -> None:
        """
        Called periodically to check heartbeat health and manage reconnection.
        Increased default timeout to 30s to be more tolerant of mesh latency.
        """
        if self.uplink_link_id is None:
            return
        
        if self.last_heartbeat_ts == 0:
            return

        elapsed = time.monotonic() - self.last_heartbeat_ts
        
        if elapsed > heartbeat_timeout:
            self.lost_heartbeats += 1
            print(f"[NODE {self.my_nid}] Heartbeat timeout ({elapsed:.1f}s > {heartbeat_timeout}s), "
                  f"lost_count={self.lost_heartbeats}")
            self._on_uplink_down()
        elif elapsed > heartbeat_timeout / 2:
            # Warning state: heartbeat is late but not yet timed out
            print(f"[NODE {self.my_nid}] WARNING: Heartbeat late ({elapsed:.1f}s)")

    def _on_uplink_down(self) -> None:
        """Handle loss of uplink connection."""
        if self.uplink_link_id is not None:
            self.sec.drop_link_key(self.uplink_link_id)
            self.uplink_link_id = None

        self.hop_count = 255
        self.routing = RoutingTable()
        self.last_heartbeat_ts = 0.0
        print(f"[NODE {self.my_nid}] Uplink down — routing reset, attempting reconnection...")

    # ----------------------------------------------------------------------
    # UI helper: connect to a chosen device
    # ----------------------------------------------------------------------
    def connect_to_device(self, dev: DeviceInfo) -> None:
        if "MESH" not in dev.name and "|" not in dev.name:
            print(f"[NODE] WARNING: '{dev.name}' may not be a mesh device")

        try:
            link_id = self.bt.connect_to(dev.address)
        except Exception as e:
            print(f"[NODE] Connection failed: {e}")
            return

        hop = dev.hop_count if dev.hop_count < 255 else 10

        self.links[link_id] = LinkState(
            is_uplink=(self.uplink_link_id is None),
            peer_nid=None,
            peer_hop_count=hop,
        )

        if self.uplink_link_id is None:
            self.uplink_link_id = link_id
            self.hop_count = hop + 1
            print(f"[NODE] Using link {link_id} as uplink (hop={self.hop_count})")

        dummy_key = b"\x02" * 32
        self.sec.set_link_key(link_id, dummy_key)

        print(f"[NODE] Connected on link {link_id}")
