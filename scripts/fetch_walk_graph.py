"""One-time: build the campus walking graph from OpenStreetMap.

Queries the Overpass API for walkable ways inside a bounding box around the
UCI campus, converts them into an undirected graph (nodes with coordinates,
edges with haversine lengths in meters), keeps the largest connected
component, and writes data/walk_graph.json for src/graph.py to load.

Usage (from the repo root):
    python -m scripts.fetch_walk_graph
"""

from __future__ import annotations

import json
import math
from collections import defaultdict, deque
from pathlib import Path

import requests

# Bounding box around UCI with margin: (south, west, north, east)
BBOX = (33.635, -117.858, 33.658, -117.830)

# Way types a pedestrian can use.
WALKABLE = (
    "footway|path|pedestrian|steps|cycleway|track|service|living_street|"
    "residential|unclassified|tertiary"
)

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
HEADERS = {"User-Agent": "campus-navigator/1.0 (UCI student project)"}
OUT_PATH = Path(__file__).parent.parent / "data" / "walk_graph.json"


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def fetch_osm():
    s, w, n, e = BBOX
    query = f"""
    [out:json][timeout:90];
    (
      way["highway"~"^({WALKABLE})$"]({s},{w},{n},{e});
    );
    (._;>;);
    out body;
    """
    last_err = None
    for url in OVERPASS_URLS:
        print(f"Querying Overpass API ({url})...")
        try:
            resp = requests.post(url, data={"data": query}, headers=HEADERS, timeout=120)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            last_err = exc
            print(f"  failed: {exc}")
    raise SystemExit(f"All Overpass mirrors failed; last error: {last_err}")


def build_graph(osm):
    coords = {}
    for el in osm["elements"]:
        if el["type"] == "node":
            coords[el["id"]] = (el["lat"], el["lon"])

    adj = defaultdict(set)
    for el in osm["elements"]:
        if el["type"] != "way":
            continue
        nds = [n for n in el.get("nodes", []) if n in coords]
        for u, v in zip(nds, nds[1:]):
            adj[u].add(v)
            adj[v].add(u)

    # Largest connected component so every node can reach every other.
    seen, best = set(), set()
    for start in adj:
        if start in seen:
            continue
        comp, dq = {start}, deque([start])
        while dq:
            cur = dq.popleft()
            for nb in adj[cur]:
                if nb not in comp:
                    comp.add(nb)
                    dq.append(nb)
        seen |= comp
        if len(comp) > len(best):
            best = comp

    nodes = {str(n): [round(coords[n][0], 7), round(coords[n][1], 7)] for n in best}
    edges = []
    done = set()
    for u in best:
        for v in adj[u]:
            if v not in best or (v, u) in done:
                continue
            done.add((u, v))
            d = haversine_m(*coords[u], *coords[v])
            edges.append([str(u), str(v), round(d, 1)])

    return {"bbox": BBOX, "nodes": nodes, "edges": edges}


def main():
    osm = fetch_osm()
    graph = build_graph(osm)
    OUT_PATH.parent.mkdir(exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(graph, f, separators=(",", ":"))
    print(f"Wrote {OUT_PATH}")
    print(f"  nodes: {len(graph['nodes'])}")
    print(f"  edges: {len(graph['edges'])}")


if __name__ == "__main__":
    main()
