# node/ui.py

from __future__ import annotations
from typing import NoReturn
from .router import NodeRouter

class NodeUI:
    """
    UI that allows:
      - Show status
      - Scan & choose device to connect
      - Send Inbox messages
      - View Inbox
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

    def _scan_and_choose(self) -> None:
        devices = self.router.bt.scan_nearby()
        if not devices:
            print("[UI] No Bluetooth devices found.")
            return

        # Show menu
        print("\n=== Nearby Devices ===")
        for idx, d in enumerate(devices, start=1):
            print(f"{idx}) {d.address}   {d.name}   hop={d.hop_count}")
        print("======================")

        while True:
            sel = input("Choose device number to connect (0 to cancel): ").strip()
            if sel == "0":
                print("[UI] Cancelled.")
                return

            try:
                idx = int(sel)
                if 1 <= idx <= len(devices):
                    chosen = devices[idx - 1]
                    print(f"[UI] Connecting to {chosen.address} ({chosen.name})...")
                    self.router.connect_to_device(chosen)
                    return
            except ValueError:
                pass

            print("Invalid selection. Try again.")

    def run(self) -> NoReturn:
        while True:
            print("\nNode Menu:")
            print(" 1) Show status")
            print(" 2) Scan & choose device to connect")
            print(" 3) Send Inbox message to Sink")
            print(" 4) Show Inbox messages")
            print(" 0) Quit")
            choice = input("> ").strip()

            if choice == "1":
                self._print_status()
            elif choice == "2":
                self._scan_and_choose()
            elif choice == "3":
                text = input("Enter message text: ")
                self.router.send_inbox_message(text)
            elif choice == "4":
                self._print_inbox()
            elif choice == "0":
                break
            else:
                print("Invalid choice.")
