# node/ui.py
from __future__ import annotations
from .router import NodeRouter

class NodeUI:
    def __init__(self, router: NodeRouter):
        self.router = router

    def print_status(self) -> None:
        print("=== Node Status ===")
        print("NID:", self.router.my_nid)
        print("Hop count:", self.router.hop_count)
        print("Lost heartbeats:", self.router.lost_heartbeats)
        print("Routed messages:", self.router.routed_count)
        print("===================")

    def run(self) -> None:
        while True:
            print("\nMenu:")
            print("1) Show status")
            print("2) Send Inbox message to Sink")
            print("0) Quit")
            choice = input("> ").strip()
            if choice == "1":
                self.print_status()
            elif choice == "2":
                text = input("Message: ")
                self.router.send_inbox_message(text)
            elif choice == "0":
                break
