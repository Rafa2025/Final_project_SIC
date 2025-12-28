# common/security.py

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import (
    hashes,
    hmac,
    serialization,
)
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


@dataclass
class CertAndKey:
    cert_pem: bytes
    key_pem: bytes


class SecurityContext:
    """
    Handles:
      - loading device cert & private key
      - loading CA cert
      - verifying peer certs
      - deriving per-link symmetric keys via ECDH
      - computing and verifying MACs (HMAC-SHA256)
      - signing/validating heartbeat messages (ECDSA)
    """

    def __init__(self, device: CertAndKey, ca_pem: bytes) -> None:
        self._device_cert = x509.load_pem_x509_certificate(device.cert_pem, default_backend())
        self._device_key = serialization.load_pem_private_key(device.key_pem, password=None)
        self._ca_cert = x509.load_pem_x509_certificate(ca_pem, default_backend())

        # link_id -> symmetric key bytes
        self._link_keys: Dict[int, bytes] = {}

    # ------------------------------------------------------------------
    # Certificate / ECDH / Session Key Derivation
    # ------------------------------------------------------------------

    def _verify_peer_cert(self, peer_cert_pem: bytes) -> x509.Certificate:
        """
        Very simple verification: check that peer cert is issued by our CA.
        For a proper chain validation you'd use an X509Store, but this
        is usually enough for the lab.
        """
        peer_cert = x509.load_pem_x509_certificate(peer_cert_pem, default_backend())
        if peer_cert.issuer != self._ca_cert.subject:
            raise ValueError("Peer certificate not issued by our CA")
        # Verify signature of peer_cert using CA public key
        ca_pub = self._ca_cert.public_key()
        ca_pub.verify(
            peer_cert.signature,
            peer_cert.tbs_certificate_bytes,
            ec.ECDSA(peer_cert.signature_hash_algorithm),  # type: ignore[arg-type]
        )
        return peer_cert

    def derive_link_key_from_cert(self, link_id: int, peer_cert_pem: bytes) -> None:
        """
        Perform ECDH between our device key and the peer's public key extracted
        from its certificate. Use HKDF-SHA256 to derive a symmetric key.
        """
        peer_cert = self._verify_peer_cert(peer_cert_pem)
        peer_public_key = peer_cert.public_key()

        if not isinstance(self._device_key, ec.EllipticCurvePrivateKey):
            raise TypeError("Device private key is not an EC key")

        shared = self._device_key.exchange(ec.ECDH(), peer_public_key)

        # Derive a 256-bit key from the shared secret
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,  # 256-bit key
            salt=None,
            info=b"SIC-IoT-link-key",
        )
        key = hkdf.derive(shared)
        self._link_keys[link_id] = key

    def set_link_key(self, link_id: int, key: bytes) -> None:
        """
        If you implement your own handshake, you can call this directly,
        bypassing the ECDH derivation step.
        """
        self._link_keys[link_id] = key

    def drop_link_key(self, link_id: int) -> None:
        self._link_keys.pop(link_id, None)

    # ------------------------------------------------------------------
    # MAC (HMAC-SHA256)
    # ------------------------------------------------------------------

    def compute_mac(self, link_id: int, data: bytes) -> bytes:
        key = self._link_keys.get(link_id)
        if key is None:
            raise ValueError(f"No session key for link {link_id}")
        h = hmac.HMAC(key, hashes.SHA256())
        h.update(data)
        return h.finalize()

    def verify_mac(self, link_id: int, data: bytes, mac: bytes) -> bool:
        key = self._link_keys.get(link_id)
        if key is None:
            return False
        h = hmac.HMAC(key, hashes.SHA256())
        h.update(data)
        try:
            h.verify(mac)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Heartbeat signing / verification (Sink-side & Node-side)
    # ------------------------------------------------------------------

    def sign_heartbeat(self, counter: int) -> bytes:
        """
        Sign the heartbeat counter with the device's private key.
        Typically used by the Sink.
        """
        if not isinstance(self._device_key, ec.EllipticCurvePrivateKey):
            raise TypeError("Device private key is not EC")
        data = counter.to_bytes(4, "big")
        signature = self._device_key.sign(data, ec.ECDSA(hashes.SHA256()))
        return signature

    @staticmethod
    def verify_heartbeat(counter: int, signature: bytes, sink_cert_pem: bytes) -> bool:
        """
        Verify heartbeat signature using the Sink's certificate.
        """
        sink_cert = x509.load_pem_x509_certificate(sink_cert_pem, default_backend())
        pub = sink_cert.public_key()
        data = counter.to_bytes(4, "big")
        try:
            pub.verify(signature, data, ec.ECDSA(hashes.SHA256()))
            return True
        except Exception:
            return False
