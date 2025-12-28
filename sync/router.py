# sync/router.py
from __future__ import annotations

from dataclasses import dataclass, field
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
    MessageError,
    EncodingError,
    DecodingError,
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
        # Split packet into message and MAC
        try:
            raw, mac = split_packet(packet, mac_len=32)
        except ValueError as e:
            print(f"[SINK] Malformed packet on link {link_id}: {e}")
            return
        
        # Ensure we have a key for this link (lab-mode static key)
        if not self.sec.has_link_key(link_id):
            self.sec.set_link_key(link_id, DEBUG_LINK_KEY)
        
        print(f"[SINK] Received {len(packet)} bytes on link {link_id}")

        # Verify MAC
        if not self.sec.verify_mac(link_id, raw, mac):
            print(f"[SINK] MAC verification failed on link {link_id}")
            return

        # Decode message
        try:
            msg = decode_message(raw, mac)
        except DecodingError as e:
            print(f"[SINK] Message decode error on link {link_id}: {e}")
            return
        except MessageError as e:
            print(f"[SINK] Message error on link {link_id}: {e}")
            return

        # Learn route to source
        self.routing.learn(msg.header.src, link_id, hop_count=1)
        self.links[link_id] = msg.header.src

        # Dispatch by service
        if msg.header.service == ServiceId.INBOX:
            self._handle_inbox(msg)
        elif msg.header.service == ServiceId.HEARTBEAT:
            # Sink usually sends heartbeats, so incoming ones are typically ignored
            pass
        else:
            # Unknown service -> possibly forward
            self._forward(msg, link_id)

    # ------------------------------------------------------------------
    # Link loss handling (cascade disconnection)
    # ------------------------------------------------------------------
    def _on_link_loss(self, lost_link_id: int) -> None:
        """
        Handle link loss: remove routes and clean up.
        """
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
            self.routing.remove_link(lost_link_id)  # removes all via that link
            print(f"[SINK] Removed route to {nid} via lost link {lost_link_id}")

        # Drop security context for this link
        self.sec.drop_link_key(lost_link_id)

        # No further disconnection needed on Sink side – nodes will detect via heartbeat timeout

    # ------------------------------------------------------------------
    # Inbox handler
    # ------------------------------------------------------------------
    def _handle_inbox(self, msg: WireMessage) -> None:
        """
        Handle incoming INBOX messages.
        """
        if msg.header.dst == self.sink_nid:
            self.inbox.on_message_from_node(
                msg.header.src,
                msg.header.client_id,
                msg.payload,
            )
        else:
            # Message is for another node - forward it
            self._forward(msg, incoming_link=None)

    # ------------------------------------------------------------------
    # Forwarding
    # ------------------------------------------------------------------
    def _forward(self, msg: WireMessage, incoming_link: Optional[int]) -> None:
        """
        Forward a message to its destination.
        """
        entry = self.routing.lookup(msg.header.dst)
        if not entry:
            print(f"[SINK] No route to {msg.header.dst}, dropping message")
            return

        out_link = entry.link
        
        # Avoid forwarding back on the same link (loop prevention)
        if incoming_link is not None and out_link == incoming_link:
            print(f"[SINK] Prevented forwarding loop for {msg.header.dst}")
            return

        self._send_on_link(out_link, msg)

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------
    def _send_on_link(self, link_id: int, msg: WireMessage) -> None:
        """
        Send a message on a specific link with MAC protection.
        """
        try:
            # Encode message
            raw = encode_message(msg)
            
            # Compute MAC
            if not self.sec.has_link_key(link_id):
                print(f"[SINK] No link key for link {link_id}, cannot send")
                return
            
            mac = self.sec.compute_mac(link_id, raw)
            
            # Send packet
            packet = raw + mac
            self.bt.send(link_id, packet)
            
        except EncodingError as e:
            print(f"[SINK] Message encoding error for link {link_id}: {e}")
        except MessageError as e:
            print(f"[SINK] Message error for link {link_id}: {e}")
        except Exception as e:
            print(f"[SINK] Unexpected error sending on link {link_id}: {e}")

    # ------------------------------------------------------------------
    # Heartbeat broadcast
    # ------------------------------------------------------------------
    def broadcast_heartbeat(self, hb: WireMessage) -> None:
        """
        Broadcast heartbeat message to all connected nodes.
        """
        if not self.links:
            return
        
        print(f"[SINK] Broadcasting heartbeat to {len(self.links)} link(s)")
        
        for link_id in list(self.links.keys()):
            self._send_on_link(link_id, hb)