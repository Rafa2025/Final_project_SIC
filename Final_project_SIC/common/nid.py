# common/nid.py
import os
from dataclasses import dataclass

@dataclass(frozen=True)
class NID:
    """128-bit Network Identifier."""
    value: bytes  # 16 bytes

    def __post_init__(self):
        if len(self.value) != 16:
            raise ValueError("NID must be 16 bytes")

    @classmethod
    def random(cls) -> "NID":
        return cls(os.urandom(16))

    @classmethod
    def from_hex(cls, s: str) -> "NID":
        return cls(bytes.fromhex(s))

    def to_hex(self) -> str:
        return self.value.hex()

    def __str__(self) -> str:
        return self.to_hex()
