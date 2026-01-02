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

from common.message import ServiceId


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

        # For anti-replay: per link_id, last seq per service/client_id
        self._seq_trackers: Dict[int, Dict[tuple[ServiceId, int], int]] = {}  # link_id -> (service, client_id) -> last_seq

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

    def derive_link_key_ephemeral(self, link_id: int, peer_cert_pem: bytes, my_ephem_priv: ec.EllipticCurvePrivateKey, peer_ephem_pub: ec.EllipticCurvePublicKey) -> None:
        peer_cert = self._verify_peer_cert(peer_cert_pem)
        # Verify it's issued by CA, etc.

        # Derive shared secret with ephemeral keys
        shared = my_ephem_priv.exchange(ec.ECDH(), peer_ephem_pub)

        # HKDF to get session key
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"iot-mesh-session-key",
        )
        key = hkdf.derive(shared)
        self._link_keys[link_id] = key

    # New: generate ephemeral key pair
    def generate_ephemeral(self) -> tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]:
        priv = ec.generate_private_key(ec.SECP521R1())
        pub = priv.public_key()
        return priv, pub

    # New: serialize pubkey
    @staticmethod
    def serialize_pubkey(pub: ec.EllipticCurvePublicKey) -> bytes:
        return pub.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )

    # New: deserialize pubkey
    @staticmethod
    def deserialize_pubkey(pub_bytes: bytes) -> ec.EllipticCurvePublicKey:
        return ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP521R1(), pub_bytes)

    # New: sign data
    def sign_data(self, data: bytes) -> bytes:
        if not isinstance(self._device_key, ec.EllipticCurvePrivateKey):
            raise TypeError("Device key not EC")
        return self._device_key.sign(data, ec.ECDSA(hashes.SHA256()))

    # New: verify signature
    def verify_data(self, pub: ec.EllipticCurvePublicKey, data: bytes, sig: bytes) -> bool:
        try:
            pub.verify(sig, data, ec.ECDSA(hashes.SHA256()))
            return True
        except:
            return False

    # For anti-replay: check and update seq
    def check_seq(self, link_id: int, service: ServiceId, client_id: int, seq: int) -> bool:
        key = (service, client_id)
        if link_id not in self._seq_trackers:
            self._seq_trackers[link_id] = {}
        tracker = self._seq_trackers[link_id]
        last = tracker.get(key, -1)
        if seq <= last:
            return False  # replay or old
        tracker[key] = seq
        return True

    def set_link_key(self, link_id: int, key: bytes) -> None:
        """
        If you implement your own handshake, you can call this directly,
        bypassing the ECDH derivation step.
        """
        self._link_keys[link_id] = key

    def drop_link_key(self, link_id: int) -> None:
        self._link_keys.pop(link_id, None)

    def has_link_key(self, link_id: int) -> bool:
        return link_id in self._link_keys
    
    def ensure_link_key(self, link_id: int, key: bytes) -> None:
        """
        Force-set a link key (used only in debug/lab mode with static key).
        Creates the key if missing, or overwrites if present.
        """
        if len(key) != 32:
            raise ValueError("Link key must be 32 bytes")
        self._link_keys[link_id] = key
        print(f"[SEC] Forced debug link key for link {link_id}")

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
