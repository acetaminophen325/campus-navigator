"""Campus walking graph: nearest-node snapping, A* routes, walk times.

The graph (data/walk_graph.json) is built once from OpenStreetMap walkable
ways by scripts/fetch_walk_graph.py. Nodes are OSM node ids with lat/lon;
edges carry haversine lengths in meters.
"""

from __future__ import annotations

import heapq
import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Average pedestrian pace (~4.8 km/h).
WALK_SPEED_M_PER_MIN = 80.0

# Straight-line estimates get a detour factor since paths are never straight.
STRAIGHT_LINE_DETOUR = 1.3


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def walk_minutes(dist_m: float) -> float:
    return dist_m / WALK_SPEED_M_PER_MIN


def straight_line_walk_minutes(dist_m: float) -> float:
    """Fallback estimate when no graph is available."""
    return walk_minutes(dist_m * STRAIGHT_LINE_DETOUR)


class WalkGraph:
    def __init__(self, nodes: Dict[str, Tuple[float, float]],
                 adj: Dict[str, List[Tuple[str, float]]]) -> None:
        self.nodes = nodes
        self.adj = adj

    @classmethod
    def load(cls, path: str | Path) -> "WalkGraph":
        with Path(path).open("r", encoding="utf-8") as f:
            raw = json.load(f)
        nodes = {nid: (lat, lon) for nid, (lat, lon) in raw["nodes"].items()}
        adj: Dict[str, List[Tuple[str, float]]] = {nid: [] for nid in nodes}
        for u, v, d in raw["edges"]:
            adj[u].append((v, d))
            adj[v].append((u, d))
        return cls(nodes, adj)

    def nearest_node(self, lat: float, lon: float) -> str:
        """Snap a coordinate to the closest graph node (linear scan)."""
        best_id, best_d = None, float("inf")
        for nid, (nlat, nlon) in self.nodes.items():
            # Cheap comparable metric first; exact enough at campus scale.
            d = (nlat - lat) ** 2 + ((nlon - lon) * 0.83) ** 2
            if d < best_d:
                best_d, best_id = d, nid
        return best_id

    def astar(self, src: str, dst: str) -> Tuple[float, List[str]]:
        """Shortest walking path src -> dst. Returns (meters, node path)."""
        if src == dst:
            return 0.0, [src]

        dlat, dlon = self.nodes[dst]

        def h(nid: str) -> float:
            lat, lon = self.nodes[nid]
            return _haversine_m(lat, lon, dlat, dlon)

        dist = {src: 0.0}
        prev: Dict[str, str] = {}
        pq: List[Tuple[float, str]] = [(h(src), src)]
        settled: Set[str] = set()

        while pq:
            _, u = heapq.heappop(pq)
            if u in settled:
                continue
            if u == dst:
                path = [u]
                while path[-1] != src:
                    path.append(prev[path[-1]])
                return dist[dst], path[::-1]
            settled.add(u)
            for v, w in self.adj.get(u, []):
                nd = dist[u] + w
                if nd < dist.get(v, float("inf")):
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(pq, (nd + h(v), v))

        return float("inf"), []

    def dijkstra_multi(self, src: str, targets: Set[str]) -> Dict[str, float]:
        """
        One Dijkstra from src, stopping once every target is settled.
        Returns {target: meters} for the targets that are reachable.
        """
        remaining = set(targets)
        out: Dict[str, float] = {}
        if src in remaining:
            out[src] = 0.0
            remaining.discard(src)

        dist = {src: 0.0}
        pq: List[Tuple[float, str]] = [(0.0, src)]
        settled: Set[str] = set()

        while pq and remaining:
            d, u = heapq.heappop(pq)
            if u in settled:
                continue
            settled.add(u)
            if u in remaining:
                out[u] = d
                remaining.discard(u)
            for v, w in self.adj.get(u, []):
                nd = d + w
                if nd < dist.get(v, float("inf")):
                    dist[v] = nd
                    heapq.heappush(pq, (nd, v))

        return out

    def route_coords(self, path: List[str]) -> List[List[float]]:
        return [[self.nodes[nid][0], self.nodes[nid][1]] for nid in path]


def load_default_graph(data_dir: str | Path) -> Optional[WalkGraph]:
    """Load data/walk_graph.json if present; None means fall back to estimates."""
    path = Path(data_dir) / "walk_graph.json"
    if not path.exists():
        return None
    return WalkGraph.load(path)
