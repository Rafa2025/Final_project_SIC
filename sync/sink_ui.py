# sync/sink_ui.py
from __future__ import annotations
from typing import NoReturn

from common.message import MessageHeader, ServiceId, WireMessage
from .router import SinkRouter
from common.nid import NID

class SinkUI:
    def __init__(self, router: SinkRouter):
        self.router = router

    def _print_status(self) -> None:
        print("\n=== Sink Status ===")
        print(f"NID: {self.router.sink_nid}")
        print(f"Direct children: {len(self.router.links)}")
        print("====================\n")

    def _list_children(self) -> None:
        print("\n=== Direct Connected Devices ===")
        if not self.router.links:
            print("(none)")
        for link_id, nid in self.router.links.items():
            print(f"Link {link_id}: NID={nid}")
        print("=============================\n")

    def _print_routing_table(self) -> None:
        snapshot = self.router.routing.snapshot()
        print("\n=== Forwarding Table ===")
        if not snapshot:
            print("(empty)")
        else:
            for nid, entry in snapshot.items():
                print(f"NID {nid} → link {entry.link} (hop {entry.hop_count})")
        print("======================\n")

    def _print_inbox(self) -> None:
        print("\n=== Received Inbox Messages ===")
        if not self.router.inbox.messages:
            print("(empty)")
        else:
            for i, (src, client_id, payload) in enumerate(self.router.inbox.messages, start=1):
                # payload is already a decoded string
                print(f"{i}. from {src} (client {client_id}): {payload}")
        print("===========================\n")

    def _disconnect_child(self) -> None:
        self._list_children()
        if not self.router.links:
            return
        link_str = input("Enter link ID to disconnect (0 to cancel): ").strip()
        if link_str == "0":
            return
        try:
            link_id = int(link_str)
        except ValueError:
            print("Invalid link ID")
            return

        if link_id not in self.router.links:
            print("Link not found")
            return

        print(f"[SINK UI] Disconnecting link {link_id} (NID: {self.router.links[link_id]})")
        self.router.bt.disconnect(link_id)  # This will trigger _on_link_loss

    def _send_to_node(self) -> None:
        # Optional: send message to a specific node
        nid_hex = input("Enter target NID (hex): ").strip()
        try:
            target_nid = NID.from_hex(nid_hex)
        except:
            print("Invalid NID")
            return
        text = input("Enter message: ")
        hdr = MessageHeader(
            src=self.router.sink_nid,
            dst=target_nid,
            service=ServiceId.INBOX,
            client_id=1,
            seq=0,  # or increment
        )
        msg = WireMessage(header=hdr, payload=text.encode(), mac=b"")
        self.router._forward(msg, incoming_link=None)
        print("[SINK] Message sent to node")

    def run(self) -> NoReturn:
        while True:
            print("\nSink Menu:")
            print(" 1) Show status")
            print(" 2) List direct connected devices")
            print(" 3) Disconnect a direct child")
            print(" 4) Show forwarding table")
            print(" 5) Show received Inbox messages")
            print(" 6) Send message to a node")
            print(" 0) Quit")
            choice = input("> ").strip()

            if choice == "1":
                self._print_status()
            elif choice == "2":
                self._list_children()
            elif choice == "3":
                self._disconnect_child()
            elif choice == "4":
                self._print_routing_table()
            elif choice == "5":
                self._print_inbox()
            elif choice == "6":
                self._send_to_node()
            elif choice == "0":
                break
            else:
                print("Invalid choice.")