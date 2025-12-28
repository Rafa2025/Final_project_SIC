# common/__init__.py

from .nid import NID
from .message import (
    MessageHeader,
    WireMessage,
    ServiceId,
    encode_message,
    decode_message,
    split_packet,
    validate_message_size,
    fragment_payload,
    MessageError,
    EncodingError,
    DecodingError,
    MAX_PAYLOAD_SIZE_RFCOMM,
    MAX_PAYLOAD_SIZE_L2CAP,
)
from .routing import RoutingTable
from .bluetooth import BluetoothManager, DeviceInfo
from .security import SecurityContext, CertAndKey
from .dtls_channel import DTLSChannel

__all__ = [
    # NID
    "NID",
    
    # Message types
    "MessageHeader",
    "WireMessage",
    "ServiceId",
    
    # Message functions
    "encode_message",
    "decode_message",
    "split_packet",
    "validate_message_size",
    "fragment_payload",
    
    # Message exceptions
    "MessageError",
    "EncodingError",
    "DecodingError",
    
    # Message constants
    "MAX_PAYLOAD_SIZE_RFCOMM",
    "MAX_PAYLOAD_SIZE_L2CAP",
    
    # Routing
    "RoutingTable",
    
    # Bluetooth
    "BluetoothManager",
    "DeviceInfo",
    
    # Security
    "SecurityContext",
    "CertAndKey",
    
    # DTLS
    "DTLSChannel",
]