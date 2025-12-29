# node/router.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
import time

from common.dtls_channel import DTLSChannel
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
from cryptography.hazmat.primitives import (
    hashes,
    hmac,
    serialization,
)
from common.security import SecurityContext


# By convention, all-zero NID = Sink
SINK_NID = NID(b"\x00" * 16)
DEBUG_LINK_KEY = b"\x02" * 32


# ----------------------------------------------------------------------
# LinkState — tracks per-link information
# ----------------------------------------------------------------------
@dataclass
class LinkState:
    is_uplink: bool
    peer_nid: NID | None = None
    peer_hop_count: int = -1


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
    links: dict[int, LinkState] = field(default_factory=dict)
    heartbeat_paused_links: set[int] = field(default_factory=set)  # for pause/resume
    pending_handshakes: dict[int, dict] = field(default_factory=dict)  # for handshake

    uplink_link_id: Optional[int] = None  # ← MISSING HERE! Add this
    hop_count: int = -1  # unknown

    routed_count: int = 0
    lost_heartbeats: int = 0
    last_heartbeat_ts: float = field(default_factory=lambda: 0.0)

    inbox_messages: List[tuple[NID, str]] = field(default_factory=list)
    dtls_channel: Optional[DTLSChannel] = None  # if using DTLS

    _next_seq: int = 0

    # ----------------------------------------------------------------------
    def start(self) -> None:
        self.bt.start(self.on_bt_data)
        print(f"[NODE {self.my_nid}] Router started")

    def stop(self) -> None:
        self.bt.stop()
        print(f"[NODE {self.my_nid}] Router stopped")

    def _init_dtls(self, link_id: int) -> None:
        if self.dtls_channel is not None:
            return

        nid_hex = self.my_nid.to_hex()
        dtls = DTLSChannel(
            is_server=False,
            certfile=f"certs/{nid_hex}/device.cert.pem",
            keyfile=f"certs/{nid_hex}/device.key.pem",
            cafile="certs/ca/ca.cert.pem",
        )

        # Get the raw Bluetooth socket for this link
        sock = self.bt._sockets.get(link_id)
        if sock is None:
            raise RuntimeError("No socket for link")

        dtls.connect(sock)  # Pass the connected RFCOMM socket
        self.dtls_channel = dtls

    # ----------------------------------------------------------------------
    # Bluetooth callback
    # ----------------------------------------------------------------------
    def on_bt_data(self, link_id: int, packet: bytes) -> None:
        try:
            raw, mac = split_packet(packet, mac_len=32)
        except ValueError as e:
            print(f"[NODE {self.my_nid}] malformed packet: {e}")
            return
        
        has_key = self.sec.has_link_key(link_id)

        if has_key:
            if not self.sec.verify_mac(link_id, raw, mac):
                print(f"[NODE {self.my_nid}] MAC failed on link {link_id}")
                return
        else:
            if len(mac) != 0:
                return

        try:
            msg = decode_message(raw, mac)
        except Exception as e:
            print(f"[NODE {self.my_nid}] decode error: {e}")
            return
        
        if has_key and not self.sec.check_seq(link_id, msg.header.service, msg.header.client_id, msg.header.seq):
            print(f"[NODE] Replay detected on link {link_id}")
            return
        
        if link_id not in self.links:
            self.links[link_id] = LinkState(
                is_uplink=False,
                peer_nid=msg.header.src,
                peer_hop_count=-1,
            )

        self.routing.learn(msg.header.src, link_id, hop_count=1)

        if msg.header.service == ServiceId.HEARTBEAT:
            self._handle_heartbeat(msg, link_id)
        elif not self.sec.has_link_key(link_id):
            print("[NODE] Dropping message before handshake")
            return
        elif not self.sec.check_seq(link_id, msg.header.service, msg.header.client_id, msg.header.seq):
            print("[NODE] Replay detected")
            return

    # ----------------------------------------------------------------------
    # Heartbeat
    # ----------------------------------------------------------------------
    def _handle_heartbeat(self, msg: WireMessage, link_id: int) -> None:
        if self.uplink_link_id is not None and link_id != self.uplink_link_id:
            print(f"[NODE] Heartbeat from non-uplink {link_id}, ignoring")
            return
        
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
            self.links[link_id].is_uplink = True
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
            if entry.link in self.heartbeat_paused_links:
                continue
            self._send_on_link(entry.link, msg)
            used.add(entry.link)

    # ----------------------------------------------------------------------
    # Sending helpers
    # ----------------------------------------------------------------------
    def _next_seq_num(self) -> int:
        self._next_seq = (self._next_seq + 1) & 0xFFFFFFFF
        return self._next_seq

    def _send_on_link(self, link_id: int, msg: WireMessage, force_no_mac: bool = False) -> None:
        raw = encode_message(msg)
        mac = b"" if force_no_mac else self.sec.compute_mac(link_id, raw)
        self.bt.send(link_id, raw + mac)

    # ----------------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------------
    def scan_and_connect_best(self) -> None:
        devices = self.bt.scan_nearby()
        if not devices:
            print("[NODE] No devices found")
            return
        
        devices = [d for d in devices if d.hop_count >= 0]
        if not devices:
            print("[NODE] No connected devices found")
            return

        best = min(devices, key=lambda d: d.hop_count)
        print(f"[NODE {self.my_nid}] Connecting to {best.address} ({best.name})")

        link_id = self.bt.connect_to(best.address)

        self.sec.set_link_key(link_id, DEBUG_LINK_KEY)

        if self.uplink_link_id is None:
            self.uplink_link_id = link_id
            self.hop_count = best.hop_count + 1
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
        try:
            self._send_on_link(self.uplink_link_id, msg)
            print("[NODE] Inbox message sent to Sink")
        except Exception as e:
            print(f"[NODE] Send failed: {e}")



    # ----------------------------------------------------------------------
    # Heartbeat timeout
    # ----------------------------------------------------------------------
    def tick(self, heartbeat_timeout: float = 15.0) -> None:
        if self.uplink_link_id is None:
            return
        if self.last_heartbeat_ts == 0:
            return

        if time.monotonic() - self.last_heartbeat_ts > heartbeat_timeout:
            self.lost_heartbeats += 1
            print("[NODE] Heartbeat timeout, dropping uplink")
            self._on_uplink_down()

    def _on_uplink_down(self) -> None:
        old_uplink = self.uplink_link_id

        if old_uplink is not None:
            self.sec.drop_link_key(old_uplink)
            self.bt.disconnect(old_uplink)

        for link_id in list(self.links.keys()):
            if link_id != old_uplink:
                self.sec.drop_link_key(link_id)
                self.bt.disconnect(link_id)

        self.links = {}
        self.uplink_link_id = None
        self.hop_count = -1
        self.routing = RoutingTable()
        self.last_heartbeat_ts = 0.0
        print("[NODE] Uplink down — routing reset")

    # ----------------------------------------------------------------------
    # UI helper: connect to a chosen device
    # ----------------------------------------------------------------------
    def connect_to_device(self, dev: DeviceInfo) -> None:
        if dev.hop_count < 0:
            print(f"[NODE] Cannot connect to device with negative hop count ({dev.name})")
            return
        
        if "MESH" not in dev.name and "|" not in dev.name:
            print(f"[NODE] WARNING: '{dev.name}' may not be a mesh device")

        try:
            link_id = self.bt.connect_to(dev.address)
        except Exception as e:
            print(f"[NODE] Connection failed: {e}")
            return

        hop = dev.hop_count if dev.hop_count >= 0 else 10

        self.links[link_id] = LinkState(
            is_uplink=(self.uplink_link_id is None),
            peer_nid=None,
            peer_hop_count=hop,
        )

        if self.uplink_link_id is None:
            self.uplink_link_id = link_id
            self.hop_count = hop + 1
            print(f"[NODE] Using link {link_id} as uplink (hop={self.hop_count})")

        self.sec.set_link_key(link_id, DEBUG_LINK_KEY)

        print(f"[NODE] Connected on link {link_id}")

    def pause_heartbeats_to(self, link_id: int) -> None:
        if link_id not in self.links:
            print(f"[NODE] Link {link_id} not found")
            return
        if self.links[link_id].is_uplink:
            print(f"[NODE] Cannot pause heartbeats on uplink {link_id}")
            return
        self.heartbeat_paused_links.add(link_id)
        print(f"[NODE] Paused heartbeats to downlink {link_id}")

    def resume_heartbeats_to(self, link_id: int) -> None:
        self.heartbeat_paused_links.discard(link_id)
        print(f"[NODE] Resumed heartbeats to downlink {link_id}")

    def _start_handshake(self, link_id: int) -> None:
        if self.sec.has_link_key(link_id):
            return

        my_ephem_priv, my_ephem_pub = self.sec.generate_ephemeral()
        self.pending_handshakes[link_id] = {
            'my_ephem_priv': my_ephem_priv,
            'my_ephem_pub': my_ephem_pub,
            'step': 1,
        }

        hdr = MessageHeader(
            src=self.my_nid,
            dst=SINK_NID,  # assume uplink is to Sink
            service=ServiceId.HANDSHAKE,
            client_id=1,
            seq=self._next_seq_num(),
        )
        payload = self.sec._device_cert.public_bytes(serialization.Encoding.PEM)
        msg = WireMessage(header=hdr, payload=payload, mac=b"")  # no MAC yet
        self._send_on_link(link_id, msg, force_no_mac=True)

    def _handle_handshake(self, msg: WireMessage, link_id: int) -> None:
        step = msg.header.client_id

        if step == 1:  # Received peer cert (client -> server)
            peer_cert_pem = msg.payload
            try:
                peer_cert = self.sec._verify_peer_cert(peer_cert_pem)
            except Exception as e:
                print(f"[NODE] Handshake failed: {e}")
                return

            # Generate ephemeral
            my_ephem_priv, my_ephem_pub = self.sec.generate_ephemeral()
            my_pub_bytes = self.sec.serialize_pubkey(my_ephem_pub)
            sig = self.sec.sign_data(my_pub_bytes)

            # Store for later
            self.pending_handshakes[link_id] = {
                'peer_cert_pem': peer_cert_pem,
                'my_ephem_priv': my_ephem_priv,
                'my_ephem_pub': my_ephem_pub,
            }

            hdr = MessageHeader(
                src=self.my_nid,
                dst=msg.header.src,
                service=ServiceId.HANDSHAKE,
                client_id=2,
                seq=self._next_seq_num(),
            )
            payload = (
                len(peer_cert_pem).to_bytes(2, 'big') + peer_cert_pem +
                len(my_pub_bytes).to_bytes(2, 'big') + my_pub_bytes +
                len(sig).to_bytes(2, 'big') + sig
            )
            resp = WireMessage(header=hdr, payload=payload, mac=b"")
            self._send_on_link(link_id, resp, force_no_mac=True)

        elif step == 2:  # Received peer cert + pub + sig (server -> client)
            # Parse payload with lengths
            offset = 0
            cert_len = int.from_bytes(msg.payload[offset:offset+2], 'big')
            offset += 2
            peer_cert_pem = msg.payload[offset:offset+cert_len]
            offset += cert_len
            pub_len = int.from_bytes(msg.payload[offset:offset+2], 'big')
            offset += 2
            peer_pub_bytes = msg.payload[offset:offset+pub_len]
            offset += pub_len
            sig_len = int.from_bytes(msg.payload[offset:offset+2], 'big')
            offset += 2
            sig = msg.payload[offset:offset+sig_len]

            peer_cert = self.sec._verify_peer_cert(peer_cert_pem, expect_sink=True)  # check OU=Sink
            peer_pub = self.sec.deserialize_pubkey(peer_pub_bytes)

            if not self.sec.verify_data(peer_cert.public_key(), peer_pub_bytes, sig):
                print("[NODE] Handshake signature invalid")
                return

            my_ephem_priv, my_ephem_pub = self.sec.generate_ephemeral()
            my_pub_bytes = self.sec.serialize_pubkey(my_ephem_pub)
            my_sig = self.sec.sign_data(my_pub_bytes)

            # Derive key
            self.sec.derive_link_key_ephemeral(
                link_id, peer_cert_pem, my_ephem_priv, peer_pub, expect_sink=True
            )

            # Send step 3
            hdr = MessageHeader(
                src=self.my_nid,
                dst=msg.header.src,
                service=ServiceId.HANDSHAKE,
                client_id=3,
                seq=self._next_seq_num(),
            )
            payload = (
                len(my_pub_bytes).to_bytes(2, 'big') + my_pub_bytes +
                len(my_sig).to_bytes(2, 'big') + my_sig
            )
            resp = WireMessage(header=hdr, payload=payload, mac=b"")
            self._send_on_link(link_id, resp, force_no_mac=True)

            del self.pending_handshakes[link_id]

        elif step == 3:  # Received client ephem + sig (server -> client)
            offset = 0
            pub_len = int.from_bytes(msg.payload[offset:offset+2], 'big')
            offset += 2
            peer_pub_bytes = msg.payload[offset:offset+pub_len]
            offset += pub_len
            sig_len = int.from_bytes(msg.payload[offset:offset+2], 'big')
            offset += 2
            sig = msg.payload[offset:offset+sig_len]

            # Get stored peer cert and my ephemeral
            state = self.pending_handshakes.get(link_id)
            if not state:
                print(f"[NODE] No pending handshake for link {link_id}")
                return

            peer_cert_pem = state['peer_cert_pem']
            my_ephem_priv = state['my_ephem_priv']

            try:
                peer_cert = self.sec._verify_peer_cert(peer_cert_pem)  # already verified in step 1
            except:
                return

            peer_pub = self.sec.deserialize_pubkey(peer_pub_bytes)

            if not self.sec.verify_data(peer_cert.public_key(), peer_pub_bytes, sig):
                print(f"[NODE] Signature verification failed in step 3")
                return

            # Derive session key
            self.sec.derive_link_key_ephemeral(
                link_id, peer_cert_pem, my_ephem_priv, peer_pub
            )

            # Handshake complete
            print(f"[NODE] Handshake completed on link {link_id}")
            del self.pending_handshakes[link_id]

        else:
            print(f"[NODE] Unknown handshake step {step}")