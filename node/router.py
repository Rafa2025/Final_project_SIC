# node/router.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional, List
from time import monotonic

from common.nid import NID
from common.bluetooth import BluetoothManager
from common.routing import RoutingTable, LinkId
from common.message import WireMessage, MessageHeader, ServiceId, encode_message
from common.security import SecurityContext

SINK_NID = NID(bytes(16))  # all zeros, configurable

@dataclass
class LinkState:
    is_uplink: bool
    peer_nid: Optional[NID] = None
    peer_hop_count: int = 255

@dataclass
class NodeRouter:
    my_nid: NID
    bt: BluetoothManager
    sec: SecurityContext

    routing: RoutingTable = field(default_factory=RoutingTable)
    links: Dict[LinkId, LinkState] = field(default_factory=dict)
    uplink_link_id: Optional[LinkId] = None
    hop_count: int = 255  # 255 = no uplink
    lost_heartbeats: int = 0
    routed_count: int = 0
    last_heartbeat_ts: float = field(default_factory=lambda: monotonic())

    def start(self) -> None:
        self.bt.start(self.on_message)
        self._connect_to_network()

    def stop(self) -> None:
        self.bt.stop()

    # --- network join -------------------------------------------------

    def _connect_to_network(self) -> None:
        """Lazy uplink selection: pick neighbor with lowest hop_count."""
        nearby = self.bt.scan_nearby()
        best_addr = None
        best_hop = 999
        for dev in nearby:
            if 0 <= dev.hop_count < best_hop:
                best_hop = dev.hop_count
                best_addr = dev.address

        if best_addr is None:
            # stay disconnected
            self.hop_count = 255
            return

        link_id = self.bt.connect_to(best_addr)
        self.links[link_id] = LinkState(is_uplink=True, peer_hop_count=best_hop)
        self.uplink_link_id = link_id
        self.hop_count = best_hop + 1
        # TODO: run mutual authentication + derive link key with SecurityContext

    # --- message handling ---------------------------------------------

    def on_message(self, link_id: int, msg: WireMessage) -> None:
        # verify MAC
        data_no_mac = encode_message(msg)
        if not self.sec.verify_mac(link_id, data_no_mac, msg.mac):
            # drop
            return

        # learn route back to src
        self.routing.learn(msg.header.src, link_id, self.hop_count)

        if msg.header.service == ServiceId.HEARTBEAT:
            self._handle_heartbeat(msg, link_id)
        elif msg.header.service == ServiceId.INBOX:
            self._handle_inbox(msg, link_id)

    def _handle_heartbeat(self, msg: WireMessage, link_id: int) -> None:
        self.last_heartbeat_ts = monotonic()
        self.lost_heartbeats = 0

        # Flood to all links except incoming
        for lid in list(self.links.keys()):
            if lid == link_id:
                continue
            self._send_on_link(lid, msg)

    def _handle_inbox(self, msg: WireMessage, link_id: int) -> None:
        if msg.header.dst == self.my_nid:
            # deliver to local inbox (e.g. store for UI)
            print(f"[NODE {self.my_nid}] Inbox from {msg.header.src}: {msg.payload.decode(errors='ignore')}")
            return

        self._forward(msg, link_id)

    def _forward(self, msg: WireMessage, incoming_link: int) -> None:
        out_link: Optional[int] = None

        if msg.header.dst == SINK_NID:
            if self.uplink_link_id is None:
                return
            out_link = self.uplink_link_id
        else:
            entry = self.routing.lookup(msg.header.dst)
            if entry:
                out_link = entry.link
            elif self.uplink_link_id is not None:
                out_link = self.uplink_link_id

        if out_link is None or out_link == incoming_link:
            return

        self._send_on_link(out_link, msg)
        self.routed_count += 1

    def _send_on_link(self, link_id: int, msg: WireMessage) -> None:
        data = encode_message(msg)
        msg.mac = self.sec.compute_mac(link_id, data)
        self.bt.send(link_id, msg)

    # --- heartbeat timeout --------------------------------------------

    def tick(self, hb_interval: float = 5.0) -> None:
        """
        Call this periodically from your main loop.
        If 3 heartbeats missed -> uplink down.
        """
        now = monotonic()
        if self.uplink_link_id is not None:
            if now - self.last_heartbeat_ts > 3 * hb_interval:
                self.lost_heartbeats += 1
                print(f"[NODE {self.my_nid}] uplink seems dead, reconnecting")
                self._on_uplink_down()

    def _on_uplink_down(self) -> None:
        # disconnect all
        for lid in list(self.links.keys()):
            self.bt.disconnect(lid)
        self.links.clear()
        self.routing = RoutingTable()
        self.uplink_link_id = None
        self.hop_count = 255
        self._connect_to_network()

    # --- UI accessors --------------------------------------------------

    def get_downlinks(self) -> List[NID]:
        return [st.peer_nid for st in self.links.values() if not st.is_uplink and st.peer_nid]

    def send_inbox_message(self, text: str) -> None:
        if self.uplink_link_id is None:
            print("No uplink, cannot send")
            return

        hdr = MessageHeader(
            src=self.my_nid,
            dst=SINK_NID,
            service=ServiceId.INBOX,
            client_id=1,
            seq=0,  # you should keep a per-node sequence counter
        )
        msg = WireMessage(header=hdr, payload=text.encode(), mac=b"")
        self._send_on_link(self.uplink_link_id, msg)
