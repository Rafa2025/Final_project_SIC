# common/message.py
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import List
from .nid import NID
import struct

class ServiceId(Enum):
    INBOX = 1
    HEARTBEAT = 2

@dataclass
class MessageHeader:
    src: NID
    dst: NID
    service: ServiceId
    client_id: int   # 0–65535
    seq: int         # 0–2^32-1

@dataclass
class WireMessage:
    header: MessageHeader
    payload: bytes
    mac: bytes  # per-link MAC

def encode_message(msg: WireMessage) -> bytes:
    """
    Serialize message WITHOUT MAC (MAC is computed over this).
    """
    hdr = msg.header
    # src(16) + dst(16) + service(1) + client_id(2) + seq(4) + payload_len(4)
    header_fmt = "!16s16sBHI I"  # note: 'I I' = client_id(uint16)+seq(uint32)+payload_len(uint32)
    payload_len = len(msg.payload)
    data = struct.pack(
        header_fmt,
        hdr.src.value,
        hdr.dst.value,
        hdr.service.value,
        hdr.client_id,
        hdr.seq,
        payload_len,
    )
    return data + msg.payload

def decode_message(buf: bytes, mac: bytes) -> WireMessage:
    header_fmt = "!16s16sBHI I"
    header_size = struct.calcsize(header_fmt)
    if len(buf) < header_size:
        raise ValueError("Buffer too short for header")

    src, dst, service_val, client_id, seq, payload_len = struct.unpack(
        header_fmt, buf[:header_size]
    )
    payload = buf[header_size:header_size+payload_len]
    if len(payload) != payload_len:
        raise ValueError("Truncated payload")

    hdr = MessageHeader(
        src=NID(src),
        dst=NID(dst),
        service=ServiceId(service_val),
        client_id=client_id,
        seq=seq
    )
    return WireMessage(header=hdr, payload=payload, mac=mac)
