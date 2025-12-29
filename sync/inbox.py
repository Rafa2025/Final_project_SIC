# sync/inbox.py

from common.dtls_channel import DTLSChannel
from common.nid import NID


class InboxService:
    def __init__(self):
        self.messages = []
        self.dtls_server = DTLSChannel(
            is_server=True,
            certfile="certs/sink/sink.cert.pem",
            keyfile="certs/sink/sink.key.pem",
            cafile="certs/ca/ca.cert.pem",
        )

    def on_message_from_node(self, src: NID, client_id: int, payload: bytes) -> None:
        text = payload.decode(errors="ignore")
        self.messages.append((src, client_id, text))
        print(f"[SINK] Inbox from {src} (client {client_id}): {text}")