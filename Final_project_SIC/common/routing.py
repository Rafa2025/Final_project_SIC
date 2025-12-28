# common/routing.py

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional
import time

from .nid import NID

LinkId = int  # abstract handle for a Bluetooth connection


@dataclass
class RouteEntry:
    link: LinkId
    hop_count: int
    last_seen: float


class RoutingTable:
    """
    Very simple routing/forwarding table:
      - learns where a given NID is reachable from (link_id, hop_count)
      - always keeps the entry with the smallest hop_count
      - drops entries when a link is removed
    """

    def __init__(self) -> None:
        self._table: Dict[NID, RouteEntry] = {}

    def learn(self, nid: NID, incoming_link: LinkId, hop_count: int) -> None:
        """
        Learn that NID 'nid' is reachable via 'incoming_link' with hop_count.
        If we already know a route with higher hop_count, we replace it.
        """
        now = time.monotonic()
        entry = self._table.get(nid)
        if entry is None or hop_count < entry.hop_count:
            self._table[nid] = RouteEntry(
                link=incoming_link,
                hop_count=hop_count,
                last_seen=now,
            )

    def lookup(self, dst: NID) -> Optional[RouteEntry]:
        """
        Get the best-known route for dst, or None.
        """
        return self._table.get(dst)

    def remove_link(self, link: LinkId) -> None:
        """
        Remove all routes that use the given link.
        """
        to_delete = [nid for nid, e in self._table.items() if e.link == link]
        for nid in to_delete:
            del self._table[nid]

    def snapshot(self) -> Dict[NID, RouteEntry]:
        """
        Get a copy of the routing table, useful for UI.
        """
        return dict(self._table)
