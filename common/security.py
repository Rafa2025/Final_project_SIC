# common/security.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Tuple
from .nid import NID
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization, hmac
from cryptography.hazmat.backends import default_backend
import os

@dataclass
class CertAndKey:
    cert_pem: bytes
    key_pem: bytes

class SecurityContext:
    """
    Handles:
    - loading device/CA certs
    - mutual authentication + ECDH for per-link session keys
    - HMAC-based MAC
    - heartbeat signing/verification
    """
    def __init__(self, device: CertAndKey, ca_pem: bytes) -> None:
        self._device_cert = x509.load_pem_x509_certificate(device.cert_pem, default_backend())
        self._device_key = serialization.load_pem_private_key(device.key_pem, password=None)
        self._ca_cert = x509.load_pem_x509_certificate(ca_pem, default_backend())
        self._link_keys: Dict[int, bytes] = {}  # link_id -> session key

    # --- Mutual authentication + ECDH ---

    def derive_link_key(self, link_id: int, peer_cert_pem: bytes) -> None:
        """Verify peer cert and derive symmetric key for this link."""
        peer_cert = x509.load_pem_x509_certificate(peer_cert_pem, default_backend())
        # TODO: verify peer_cert is signed by CA (chain verification)
        # (For project: at least compare issuer == CA subject)
        if peer_cert.issuer != self._ca_cert.subject:
            raise ValueError("Peer cert not issued by CA")

        # ECDH using ephemeral key (for demo, use device key)
        assert isinstance(self._device_key, ec.EllipticCurvePrivateKey)
        peer_pub = peer_cert.public_key()
        shared = self._device_key.exchange(ec.ECDH(), peer_pub)
        # Derive symmetric key from shared secret:
        digest = hashes.Hash(hashes.SHA256())
        digest.update(shared)
        key = digest.finalize()[:16]  # 128-bit HMAC key
        self._link_keys[link_id] = key

    # --- MACs ---

    def compute_mac(self, link_id: int, data: bytes) -> bytes:
        key = self._link_keys.get(link_id)
        if not key:
            raise ValueError("No session key for link")
        h = hmac.HMAC(key, hashes.SHA256())
        h.update(data)
        return h.finalize()

    def verify_mac(self, link_id: int, data: bytes, mac: bytes) -> bool:
        try:
            key = self._link_keys.get(link_id)
            if not key:
                return False
            h = hmac.HMAC(key, hashes.SHA256())
            h.update(data)
            h.verify(mac)
            return True
        except Exception:
            return False

    # --- Heartbeat signing / verifying ---

    def sign_heartbeat(self, counter: int) -> bytes:
        """Sign heartbeat counter with device private key (Sink)."""
        assert isinstance(self._device_key, ec.EllipticCurvePrivateKey)
        data = counter.to_bytes(4, "big")
        return self._device_key.sign(data, ec.ECDSA(hashes.SHA256()))

    def verify_heartbeat(self, counter: int, signature: bytes, sink_cert_pem: bytes) -> bool:
        sink_cert = x509.load_pem_x509_certificate(sink_cert_pem, default_backend())
        pub = sink_cert.public_key()
        data = counter.to_bytes(4, "big")
        try:
            pub.verify(signature, data, ec.ECDSA(hashes.SHA256()))
            return True
        except Exception:
            return False
