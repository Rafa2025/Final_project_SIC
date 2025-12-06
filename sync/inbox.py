# sync/inbox.py
from __future__ import annotations
from common.nid import NID

class InboxService:
    def __init__(self):
        self.messages = []  # list of (src, client_id, text)

    def on_message_from_node(self, src: NID, client_id: int, payload: bytes) -> None:
        text = payload.decode(errors="ignore")
        self.messages.append((src, client_id, text))
        print(f"[SINK] Inbox from {src}: {text}")
