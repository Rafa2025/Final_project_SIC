# sync/router.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict
from common.nid import NID
from common.bluetooth import BluetoothManager
from common.routing import RoutingTable, LinkId
from common.message import WireMessage, ServiceId, MessageHeader, encode_message
from common.security import SecurityContext
from .inbox import InboxService

SINK_NID = NID(bytes(16))

@dataclass
class SinkRouter:
    sink_nid: NID
    bt: BluetoothManager
    sec: SecurityContext
    inbox: InboxService

    routing: RoutingTable = field(default_factory=RoutingTable)
    links: Dict[LinkId, NID] = field(default_factory=dict)

    def start(self) -> None:
        self.bt.start(self.on_message)

    def stop(self) -> None:
        self.bt.stop()

    def on_message(self, link_id: int, msg: WireMessage) -> None:
        data = encode_message(msg)
        if not self.sec.verify_mac(link_id, data, msg.mac):
            return
        self.routing.learn(msg.header.src, link_id, 1)  # 1 hop from sink

        if msg.header.service == ServiceId.INBOX:
            self._handle_inbox(msg, link_id)
        elif msg.header.service == ServiceId.HEARTBEAT:
            # heartbeats originate here usually; may ignore
            pass

    def _handle_inbox(self, msg: WireMessage, link_id: int) -> None:
        if msg.header.dst == self.sink_nid:
            self.inbox.on_message_from_node(
                src=msg.header.src,
                client_id=msg.header.client_id,
                payload=msg.payload,
            )
        else:
            # should not happen often, but forward if needed
            self._forward(msg, link_id)

    def _forward(self, msg: WireMessage, incoming_link: int) -> None:
        entry = self.routing.lookup(msg.header.dst)
        if not entry:
            return
        if entry.link == incoming_link:
            return
        self._send_on_link(entry.link, msg)

    def _send_on_link(self, link_id: int, msg: WireMessage) -> None:
        data = encode_message(msg)
        msg.mac = self.sec.compute_mac(link_id, data)
        self.bt.send(link_id, msg)

    def broadcast_heartbeat(self, hb_msg: WireMessage) -> None:
        for link_id in list(self.links.keys()):
            self._send_on_link(link_id, hb_msg)
