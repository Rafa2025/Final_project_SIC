# common/message.py

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Tuple
import struct

from .nid import NID


class ServiceId(Enum):
    """
    Logical services used by your project.
    Extend if needed (e.g., CONTROL, DEBUG, etc.).
    """
    INBOX = 1
    HEARTBEAT = 2
    CONTROL = 3


@dataclass
class MessageHeader:
    src: NID
    dst: NID
    service: ServiceId
    client_id: int  # 0..65535
    seq: int        # 0..2^32-1


@dataclass
class WireMessage:
    header: MessageHeader
    payload: bytes
    mac: bytes = b""  # per-link MAC (HMAC-SHA256, so 32 bytes typically)


# Header layout (big endian):
#   src (16 bytes)
#   dst (16 bytes)
#   service (1 byte)
#   client_id (2 bytes, unsigned short)
#   seq (4 bytes, unsigned int)
#   payload_len (4 bytes, unsigned int)
_HEADER_FMT = "!16s16sBHII"
_HEADER_SIZE = struct.calcsize(_HEADER_FMT)


def encode_message(msg: WireMessage) -> bytes:
    """
    Serialize a WireMessage WITHOUT the MAC.
    The MAC is computed over this returned buffer.
    """
    hdr = msg.header
    payload_len = len(msg.payload)

    data = struct.pack(
        _HEADER_FMT,
        hdr.src.value,
        hdr.dst.value,
        hdr.service.value,
        hdr.client_id,
        hdr.seq,
        payload_len,
    )
    return data + msg.payload


def decode_message(buf: bytes, mac: bytes = b"") -> WireMessage:
    """
    Decode a buffer (WITHOUT MAC) into a WireMessage.
    'mac' must be provided separately (e.g., last 32 bytes from a packet).
    """
    if len(buf) < _HEADER_SIZE:
        raise ValueError("Buffer too short for header")

    src_bytes, dst_bytes, service_val, client_id, seq, payload_len = struct.unpack(
        _HEADER_FMT, buf[:_HEADER_SIZE]
    )

    expected_len = _HEADER_SIZE + payload_len
    if len(buf) < expected_len:
        raise ValueError("Truncated payload")

    payload = buf[_HEADER_SIZE:expected_len]

    header = MessageHeader(
        src=NID(src_bytes),
        dst=NID(dst_bytes),
        service=ServiceId(service_val),
        client_id=client_id,
        seq=seq,
    )

    return WireMessage(header=header, payload=payload, mac=mac)


def split_packet(packet: bytes, mac_len: int = 32) -> Tuple[bytes, bytes]:
    """
    Utility: split [encoded_without_mac][mac] into (buf, mac).
    """
    if len(packet) < mac_len:
        raise ValueError("Packet too short to contain MAC")
    return packet[:-mac_len], packet[-mac_len:]
