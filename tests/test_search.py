"""Tests for the BM25 text index."""

from src.models import Meeting
from src.search import BM25Index


def _m(mid: str, title: str, dept: str = "General") -> Meeting:
    return Meeting(
        meeting_id=mid, course_id=mid, title=title, dept=dept, days="M",
        start_min=600, end_min=650, building_code="B", room="1", term="T",
    )


def _index():
    meetings = [
        _m("m1", "Introduction to Machine Learning"),
        _m("m2", "Organic Chemistry"),
        _m("m3", "Machine Learning Theory"),
    ]
    return BM25Index(meetings)


def test_relevant_docs_score_higher():
    sm = _index().score_map("machine learning")
    assert sm["m1"] > sm["m2"]
    assert sm["m3"] > sm["m2"]


def test_scores_normalized_to_unit_interval():
    scores = _index().normalized_scores("machine learning")
    assert scores
    assert all(0.0 <= s <= 1.0 for s in scores)
    assert max(scores) == 1.0  # normalized by the corpus maximum


def test_empty_query_scores_all_zero():
    assert all(s == 0.0 for s in _index().normalized_scores(""))


def test_unmatched_query_scores_all_zero():
    assert all(s == 0.0 for s in _index().normalized_scores("zzz-not-a-real-term"))


def test_score_map_covers_every_meeting():
    idx = _index()
    sm = idx.score_map("chemistry")
    assert set(sm.keys()) == {"m1", "m2", "m3"}
