# node/ui.py

from __future__ import annotations
from typing import NoReturn
from .router import LinkState, NodeRouter
from common.nid import NID

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
        uplink_nid = "None"
        if self.router.uplink_link_id is not None:
            uplink_nid = self.router.links.get(self.router.uplink_link_id, LinkState(is_uplink=True)).peer_nid or "Unknown"
        
        print("\n=== Node Status ===")
        print(f"NID:             {self.router.my_nid}")
        print(f"Uplink NID:      {uplink_nid}")
        print(f"Uplink link_id:  {self.router.uplink_link_id}")
        print(f"Hop count:       {self.router.hop_count if self.router.hop_count >= 0 else 'Disconnected'}")
        print(f"Routed messages: {self.router.routed_count}")
        print(f"Lost heartbeats: {self.router.lost_heartbeats}")
        print("===================\n")

    def _print_inbox(self) -> None:
        print("\n=== Inbox Messages ===")
        if not self.router.inbox_messages:
            print("(empty)")
        else:
            for i, (src, text) in enumerate(self.router.inbox_messages, start=1):
                print(f"{i}. from {src}: {text}")
        print("======================\n")

    def _print_routing_table(self) -> None:
        snapshot = self.router.routing.snapshot()
        print("\n=== Forwarding Table (Routing Entries) ===")
        if not snapshot:
            print("(empty)")
        else:
            for nid, entry in snapshot.items():
                print(f"NID {nid} → link {entry.link} (hop {entry.hop_count})")
        print("=========================================\n")

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

    def _list_downlinks(self) -> None:
        print("\n=== Direct Downlinks ===")
        found = False
        for link_id, state in self.router.links.items():
            if not state.is_uplink:
                print(f"Link {link_id}: hop={state.peer_hop_count}, NID={state.peer_nid}")
                found = True
        if not found:
            print("(none)")
        print("======================\n")

    def _toggle_heartbeat_pause(self) -> None:
        self._list_downlinks()
        link_str = input("Enter link ID to toggle heartbeat pause (0 to cancel): ").strip()
        if link_str == "0":
            return
        try:
            link_id = int(link_str)
        except ValueError:
            print("Invalid link ID")
            return

        if link_id not in self.router.links or self.router.links[link_id].is_uplink:
            print("Invalid or uplink link")
            return

        if link_id in self.router.heartbeat_paused_links:
            self.router.resume_heartbeats_to(link_id)
        else:
            self.router.pause_heartbeats_to(link_id)

    def run(self) -> NoReturn:
        while True:
            print("Node Menu:")
            print(" 1) Show status")
            print(" 2) Scan & choose device to connect")
            print(" 3) Send Inbox message to Sink")
            print(" 4) Show Inbox messages")
            print(" 5) List direct downlinks")
            print(" 6) Pause/Resume heartbeats to a downlink (simulate break)")
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
            elif choice == "5":
                self._list_downlinks()
            elif choice == "6":
                self._toggle_heartbeat_pause()
            elif choice == "7":
                self._print_routing_table()
            elif choice == "0":
                break
            else:
                print("Invalid choice.")
