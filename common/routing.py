# common/routing.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional
from .nid import NID

LinkId = int  # abstract handle for a BLE connection

@dataclass
class RouteEntry:
    link: LinkId
    hop_count: int

class RoutingTable:
    def __init__(self) -> None:
        self._table: Dict[NID, RouteEntry] = {}

    def learn(self, src: NID, incoming_link: LinkId, hop_count: int) -> None:
        """Learn that src is reachable via incoming_link with given hop_count."""
        entry = self._table.get(src)
        if entry is None or hop_count < entry.hop_count:
            self._table[src] = RouteEntry(link=incoming_link, hop_count=hop_count)

    def lookup(self, dst: NID) -> Optional[RouteEntry]:
        return self._table.get(dst)

    def remove_link(self, link: LinkId) -> None:
        to_delete = [nid for nid, e in self._table.items() if e.link == link]
        for nid in to_delete:
            del self._table[nid]

    def snapshot(self) -> Dict[NID, RouteEntry]:
        return dict(self._table)
