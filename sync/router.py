# sync/router.py
from __future__ import annotations

from dataclasses import dataclass, field
import subprocess
from typing import Dict, Optional

from common.nid import NID
from common.bluetooth import BluetoothManager
from common.routing import RoutingTable, LinkId
from common.message import (
    WireMessage,
    MessageHeader,
    ServiceId,
    encode_message,
    decode_message,
    split_packet,
)
from common.security import SecurityContext
from .inbox import InboxService


SINK_NID = NID(bytes(16))  # 16-byte all-zero ID
DEBUG_LINK_KEY = b"\x02" * 32


@dataclass
class SinkRouter:
    """
    Sink-side router:
      - Accepts connections from nodes (via BluetoothManager)
      - Verifies MACs
      - Handles Inbox messages
      - Broadcasts Heartbeats
      - Maintains routing info for multi-hop networks
    """

    sink_nid: NID
    bt: BluetoothManager
    sec: SecurityContext
    inbox: InboxService

    routing: RoutingTable = field(default_factory=RoutingTable)
    links: Dict[LinkId, NID] = field(default_factory=dict)  # link_id -> neighbor nid

    def start(self) -> None:
    # BluetoothManager(enable_server=True) already starts server
        self.bt.set_link_loss_callback(self._on_link_loss)
        self.bt.start(self.on_bt_data)
        print("[SINK] Router started")

    def stop(self) -> None:
        self.bt.stop()
        print("[SINK] Router stopped")

    # ------------------------------------------------------------------
    # Bluetooth receive handler
    # ------------------------------------------------------------------
    def on_bt_data(self, link_id: int, packet: bytes) -> None:
        """
        BluetoothManager gives raw bytes:
            packet = raw_message_without_mac + mac(32)
        """
        try:
            raw, mac = split_packet(packet, mac_len=32)
        except ValueError as e:
            print(f"[SINK] malformed packet on link {link_id}: {e}")
            return
        
        # Ensure we have a key for this link (lab-mode static key)
        self.sec.ensure_link_key(link_id, DEBUG_LINK_KEY)
        print(f"[SINK] rx {len(packet)} bytes on link {link_id}")


        # MAC verify
        if not self.sec.verify_mac(link_id, raw, mac):
            print(f"[SINK] MAC verify failed on link {link_id}")
            return

        # Decode
        try:
            msg = decode_message(raw, mac)
        except Exception as e:
            print(f"[SINK] decode error on link {link_id}: {e}")
            return

        # Learn route to src
        self.routing.learn(msg.header.src, link_id, hop_count=1)
        self.links[link_id] = msg.header.src

        # Dispatch
        if msg.header.service == ServiceId.INBOX:
            self._handle_inbox(msg)
        elif msg.header.service == ServiceId.HEARTBEAT:
            # Sink usually sends, so typically ignored
            pass
        else:
            # Unknown service -> possibly forward
            self._forward(msg, link_id)

    # ------------------------------------------------------------------
    # Link loss handling (cascade disconnection)
    # ------------------------------------------------------------------
    def _on_link_loss(self, lost_link_id: int) -> None:
        if lost_link_id not in self.links:
            return

        lost_nid = self.links[lost_link_id]
        print(f"[SINK] Link {lost_link_id} lost (NID: {lost_nid})")

        # Remove the direct child
        del self.links[lost_link_id]

        # Find all routes that went through this link (direct and indirect)
        routes_to_remove = [
            nid for nid, entry in self.routing.snapshot().items()
            if entry.link == lost_link_id
        ]

        # Remove routes
        for nid in routes_to_remove:
            self.routing.remove_link(lost_link_id)
            print(f"[SINK] Removed route to {nid} via lost link {lost_link_id}")

        # If no more direct children, reset adapter to clear stuck RFCOMM state
        if not self.links:
            print("[SINK] No remaining connections — resetting Bluetooth adapter to fix reconnect issues")
            try:
                subprocess.run(["hciconfig", "hci0", "reset"], check=True)
                print("[SINK] Adapter reset complete")
            except subprocess.CalledProcessError as e:
                print(f"[SINK] Failed to reset adapter: {e}")
            except Exception as e:
                print(f"[SINK] Unexpected error during reset: {e}")

    # ------------------------------------------------------------------
    # Inbox
    # ------------------------------------------------------------------
    def _handle_inbox(self, msg: WireMessage) -> None:
        if msg.header.dst == self.sink_nid:
            self.inbox.on_message_from_node(
                msg.header.src,
                msg.header.client_id,
                msg.payload,
            )
        else:
            self._forward(msg, incoming_link=None)

    # ------------------------------------------------------------------
    # Forwarding
    # ------------------------------------------------------------------
    def _forward(self, msg: WireMessage, incoming_link: Optional[int]) -> None:
        entry = self.routing.lookup(msg.header.dst)
        if not entry:
            return

        out_link = entry.link
        if incoming_link is not None and out_link == incoming_link:
            return  # avoid loops

        self._send_on_link(out_link, msg)

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------
    def _send_on_link(self, link_id: int, msg: WireMessage) -> None:
        raw = encode_message(msg)
        mac = self.sec.compute_mac(link_id, raw)
        packet = raw + mac
        self.bt.send(link_id, packet)

    # ------------------------------------------------------------------
    # Heartbeat broadcast
    # ------------------------------------------------------------------
    def broadcast_heartbeat(self, hb: WireMessage) -> None:
        for link_id in list(self.links.keys()):
            self._send_on_link(link_id, hb)
