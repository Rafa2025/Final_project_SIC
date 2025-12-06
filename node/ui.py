# node/ui.py

from __future__ import annotations

from typing import NoReturn
from .router import NodeRouter


class NodeUI:
    """
    Very simple text UI to interact with a node:
      - Show status
      - Scan & connect
      - Send Inbox messages
      - Show received Inbox messages
    """

    def __init__(self, router: NodeRouter):
        self.router = router

    def _print_status(self) -> None:
        rt_snapshot = self.router.routing.snapshot()
        print("\n=== Node Status ===")
        print(f"NID:             {self.router.my_nid}")
        print(f"Hop count:       {self.router.hop_count}")
        print(f"Uplink link_id:  {self.router.uplink_link_id}")
        print(f"Routed messages: {self.router.routed_count}")
        print(f"Lost heartbeats: {self.router.lost_heartbeats}")
        print(f"Routing entries: {len(rt_snapshot)}")
        print("====================\n")

    def _print_inbox(self) -> None:
        print("\n=== Inbox Messages ===")
        if not self.router.inbox_messages:
            print("(empty)")
        else:
            for i, (src, text) in enumerate(self.router.inbox_messages, start=1):
                print(f"{i}. from {src}: {text}")
        print("======================\n")

    def run(self) -> NoReturn:
        while True:
            print("Node Menu:")
            print(" 1) Show status")
            print(" 2) Scan & connect to best neighbor")
            print(" 3) Send Inbox message to Sink")
            print(" 4) Show Inbox messages")
            print(" 0) Quit")
            choice = input("> ").strip()

            if choice == "1":
                self._print_status()
            elif choice == "2":
                self.router.scan_and_connect_best()
            elif choice == "3":
                text = input("Enter message text: ")
                self.router.send_inbox_message(text)
            elif choice == "4":
                self._print_inbox()
            elif choice == "0":
                break
            else:
                print("Invalid choice.")
