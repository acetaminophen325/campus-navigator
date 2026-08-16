"""Tests for the walking graph (A*, multi-target Dijkstra) and feasibility."""

import math

from src.graph import (
    WalkGraph,
    walk_minutes,
    straight_line_walk_minutes,
    WALK_SPEED_M_PER_MIN,
    STRAIGHT_LINE_DETOUR,
)
from src.ranker import classify_feasibility


def _graph():
    """
    Four nodes on a line (west to east): A - B - C, plus a direct A-C edge
    that is longer than going through B, and a spur C - D.

        A --100-- B --100-- C --100-- D
         \\_______250_______/
    """
    nodes = {
        "A": (0.0, 0.0),
        "B": (0.0, 0.0005),
        "C": (0.0, 0.0010),
        "D": (0.0, 0.0015),
    }
    adj = {
        "A": [("B", 100.0), ("C", 250.0)],
        "B": [("A", 100.0), ("C", 100.0)],
        "C": [("B", 100.0), ("A", 250.0), ("D", 100.0)],
        "D": [("C", 100.0)],
    }
    return WalkGraph(nodes, adj)


def test_nearest_node():
    g = _graph()
    assert g.nearest_node(0.0, 0.0001) == "A"
    assert g.nearest_node(0.0, 0.0009) == "C"


def test_astar_prefers_shorter_multi_hop_path():
    g = _graph()
    dist, path = g.astar("A", "C")
    assert path == ["A", "B", "C"]   # 200 m beats the direct 250 m edge
    assert dist == 200.0


def test_astar_same_node():
    g = _graph()
    dist, path = g.astar("B", "B")
    assert dist == 0.0
    assert path == ["B"]


def test_astar_unreachable():
    nodes = {"X": (0.0, 0.0), "Y": (0.0, 0.01)}
    g = WalkGraph(nodes, {"X": [], "Y": []})
    dist, path = g.astar("X", "Y")
    assert math.isinf(dist)
    assert path == []

def test_dijkstra_multi_hits_all_targets():
    g = _graph()
    dists = g.dijkstra_multi("A", {"B", "C", "D"})
    assert dists == {"B": 100.0, "C": 200.0, "D": 300.0}


def test_dijkstra_multi_source_is_target():
    g = _graph()
    assert g.dijkstra_multi("A", {"A"}) == {"A": 0.0}


def test_route_coords_follow_path():
    g = _graph()
    _, path = g.astar("A", "D")
    coords = g.route_coords(path)
    assert coords[0] == [0.0, 0.0]
    assert coords[-1] == [0.0, 0.0015]
    assert len(coords) == len(path)


def test_walk_minutes():
    assert walk_minutes(WALK_SPEED_M_PER_MIN * 7) == 7.0


def test_straight_line_estimate_includes_detour_factor():
    assert straight_line_walk_minutes(800) == 800 * STRAIGHT_LINE_DETOUR / WALK_SPEED_M_PER_MIN


def test_feasibility_easy():
    label, spare = classify_feasibility(15, 5.0)
    assert label == "easy"
    assert spare == 10


def test_feasibility_tight():
    label, spare = classify_feasibility(10, 8.0)
    assert label == "tight"
    assert spare == 2


def test_feasibility_late():
    label, spare = classify_feasibility(5, 9.0)
    assert label == "late"
    assert spare == -4


def test_feasibility_ongoing():
    label, _ = classify_feasibility(-5, 2.0)
    assert label == "ongoing"
