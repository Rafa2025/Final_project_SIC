# common/message.py

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Tuple, Optional
import struct

from .nid import NID


class MessageError(Exception):
    """Base exception for message-related errors."""
    pass


class EncodingError(MessageError):
    """Raised when message encoding fails."""
    pass


class DecodingError(MessageError):
    """Raised when message decoding fails."""
    pass


class ServiceId(Enum):
    """
    Logical services used by your project.
    Extend as needed (e.g., CONTROL, DEBUG, FILE_TRANSFER, etc.).
    """
    INBOX = 1
    HEARTBEAT = 2
    HANDSHAKE = 3
    
    @classmethod
    def from_value(cls, value: int) -> ServiceId:
        """Safely convert integer to ServiceId."""
        try:
            return cls(value)
        except ValueError:
            raise DecodingError(f"Invalid service ID: {value}")


@dataclass
class MessageHeader:
    """
    Message header containing routing and sequencing information.
    
    Attributes:
        src: Source node identifier (16 bytes)
        dst: Destination node identifier (16 bytes)
        service: Target service for this message
        client_id: Client identifier (0-65535)
        seq: Sequence number for ordering/deduplication (0-2^32-1)
    """
    src: NID
    dst: NID
    service: ServiceId
    client_id: int
    seq: int
    
    def __post_init__(self):
        """Validate header fields."""
        if not isinstance(self.src, NID):
            raise ValueError("src must be a NID instance")
        if not isinstance(self.dst, NID):
            raise ValueError("dst must be a NID instance")
        if not isinstance(self.service, ServiceId):
            raise ValueError("service must be a ServiceId instance")
        if not (0 <= self.client_id <= 65535):
            raise ValueError(f"client_id must be 0-65535, got {self.client_id}")
        if not (0 <= self.seq <= 0xFFFFFFFF):
            raise ValueError(f"seq must be 0-4294967295, got {self.seq}")


@dataclass
class WireMessage:
    """
    Complete wire-format message including header, payload, and MAC.
    
    Attributes:
        header: Message header with routing information
        payload: Message payload (arbitrary bytes)
        mac: Message Authentication Code (typically HMAC-SHA256, 32 bytes)
    """
    header: MessageHeader
    payload: bytes
    mac: bytes = b""
    
    def __post_init__(self):
        """Validate message fields."""
        if not isinstance(self.payload, bytes):
            raise ValueError("payload must be bytes")
        if not isinstance(self.mac, bytes):
            raise ValueError("mac must be bytes")
    
    @property
    def total_size(self) -> int:
        """Calculate total message size in bytes."""
        return _HEADER_SIZE + len(self.payload) + len(self.mac)
    
    def fits_in_mtu(self, mtu: int = 672) -> bool:
        """
        Check if message fits within Bluetooth RFCOMM MTU.
        
        Default MTU is 672 bytes (common for RFCOMM), but can be configured.
        L2CAP typically supports 672-65535 bytes.
        """
        return self.total_size <= mtu


# Header layout (big endian):
#   src (16 bytes) - Source NID
#   dst (16 bytes) - Destination NID
#   service (1 byte) - Service identifier
#   client_id (2 bytes, unsigned short) - Client ID
#   seq (4 bytes, unsigned int) - Sequence number
#   payload_len (4 bytes, unsigned int) - Payload length
#
# Total header size: 43 bytes
_HEADER_FMT = "!16s16sBHII"
_HEADER_SIZE = struct.calcsize(_HEADER_FMT)

# Maximum payload size for typical Bluetooth RFCOMM (672 byte MTU)
# Accounting for header (43 bytes) and MAC (32 bytes)
MAX_PAYLOAD_SIZE_RFCOMM = 672 - _HEADER_SIZE - 32  # = 597 bytes

# Maximum payload size for L2CAP (more flexible)
MAX_PAYLOAD_SIZE_L2CAP = 65535 - _HEADER_SIZE - 32  # Much larger


def encode_message(msg: WireMessage, include_mac: bool = False) -> bytes:
    """
    Serialize a WireMessage to wire format.
    
    Args:
        msg: The message to encode
        include_mac: If True, append the MAC to the output
    
    Returns:
        Encoded message as bytes (with or without MAC)
    
    Raises:
        EncodingError: If encoding fails
        ValueError: If message parameters are invalid
    """
    try:
        hdr = msg.header
        payload_len = len(msg.payload)
        
        # Validate payload length
        if payload_len > 0xFFFFFFFF:
            raise EncodingError(f"Payload too large: {payload_len} bytes")
        
        # Pack header
        data = struct.pack(
            _HEADER_FMT,
            hdr.src.value,
            hdr.dst.value,
            hdr.service.value,
            hdr.client_id,
            hdr.seq,
            payload_len,
        )
        
        # Append payload
        data += msg.payload
        
        # Optionally append MAC
        if include_mac and msg.mac:
            data += msg.mac
        
        return data
        
    except struct.error as e:
        raise EncodingError(f"Struct packing failed: {e}")
    except Exception as e:
        raise EncodingError(f"Encoding failed: {e}")


def decode_message(buf: bytes, mac: bytes = b"") -> WireMessage:
    """
    Decode a buffer into a WireMessage.
    
    Args:
        buf: Buffer containing header + payload (without MAC)
        mac: Message Authentication Code (provided separately)
    
    Returns:
        Decoded WireMessage
    
    Raises:
        DecodingError: If decoding fails or buffer is invalid
    """
    try:
        if len(buf) < _HEADER_SIZE:
            raise DecodingError(
                f"Buffer too short for header: {len(buf)} < {_HEADER_SIZE}"
            )
        
        # Unpack header
        src_bytes, dst_bytes, service_val, client_id, seq, payload_len = struct.unpack(
            _HEADER_FMT, buf[:_HEADER_SIZE]
        )
        
        # Validate payload length
        expected_len = _HEADER_SIZE + payload_len
        if len(buf) < expected_len:
            raise DecodingError(
                f"Truncated payload: expected {expected_len}, got {len(buf)}"
            )
        
        if len(buf) > expected_len:
            # Extra data in buffer (might be concatenated messages)
            pass  # This is fine, we just take what we need
        
        # Extract payload
        payload = buf[_HEADER_SIZE:expected_len]
        
        # Create header with validation
        header = MessageHeader(
            src=NID(src_bytes),
            dst=NID(dst_bytes),
            service=ServiceId.from_value(service_val),
            client_id=client_id,
            seq=seq,
        )
        
        return WireMessage(header=header, payload=payload, mac=mac)
        
    except struct.error as e:
        raise DecodingError(f"Struct unpacking failed: {e}")
    except MessageError:
        raise  # Re-raise our own exceptions
    except Exception as e:
        raise DecodingError(f"Decoding failed: {e}")


def split_packet(packet: bytes, mac_len: int = 32) -> Tuple[bytes, bytes]:
    """
    Split a complete packet into message buffer and MAC.
    
    Args:
        packet: Complete packet [header + payload + MAC]
        mac_len: Expected MAC length (default: 32 for HMAC-SHA256)
    
    Returns:
        Tuple of (message_buffer, mac)
    
    Raises:
        ValueError: If packet is too short to contain MAC
    """
    if len(packet) < mac_len:
        raise ValueError(
            f"Packet too short to contain MAC: {len(packet)} < {mac_len}"
        )
    
    if len(packet) < _HEADER_SIZE + mac_len:
        raise ValueError(
            f"Packet too short for header + MAC: {len(packet)} < {_HEADER_SIZE + mac_len}"
        )
    
    return packet[:-mac_len], packet[-mac_len:]


def validate_message_size(msg: WireMessage, max_size: Optional[int] = None) -> bool:
    """
    Validate that a message fits within size constraints.
    
    Args:
        msg: Message to validate
        max_size: Maximum allowed size (default: RFCOMM MTU of 672)
    
    Returns:
        True if valid, False otherwise
    """
    if max_size is None:
        max_size = 672  # Default RFCOMM MTU
    
    return msg.total_size <= max_size


def fragment_payload(payload: bytes, max_chunk_size: int = MAX_PAYLOAD_SIZE_RFCOMM) -> list[bytes]:
    """
    Fragment a large payload into smaller chunks suitable for Bluetooth transmission.
    
    Args:
        payload: The payload to fragment
        max_chunk_size: Maximum size per chunk
    
    Returns:
        List of payload chunks
    """
    if len(payload) <= max_chunk_size:
        return [payload]
    
    chunks = []
    offset = 0
    while offset < len(payload):
        chunk = payload[offset:offset + max_chunk_size]
        chunks.append(chunk)
        offset += max_chunk_size
    
    return chunks