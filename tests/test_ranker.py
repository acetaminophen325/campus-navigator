"""Tests for the ranking pipeline and the empty-state fallback."""

from src.models import Building, Meeting
from src.ranker import (
    RankConfig,
    haversine_m,
    occurs_today,
    extract_section_type,
    extract_course_level,
    filter_candidates,
    score_candidate,
    rank_meetings,
    rank_with_fallback,
    day_has_meetings,
)


def _bldg(code, lat, lon):
    return Building(code=code, name=code, lat=lat, lon=lon)


def _meet(mid, code, days="M", start=600, end=650, course="CS 101", title="Intro", dept="CS"):
    return Meeting(
        meeting_id=mid, course_id=course, title=title, dept=dept, days=days,
        start_min=start, end_min=end, building_code=code, room="1", term="T",
    )


def _fixture():
    buildings = {
        "NEAR": _bldg("NEAR", 33.600, -117.800),
        "FAR":  _bldg("FAR",  33.700, -117.900),
    }
    meetings = [
        _meet("soon-near",  "NEAR", days="M",  start=610),   # 10 min out, at NEAR
        _meet("later-near", "NEAR", days="M",  start=800),   # 200 min out
        _meet("soon-far",   "FAR",  days="M",  start=615),   # soon but ~15 km away
        _meet("tue-near",   "NEAR", days="Tu", start=610),   # wrong day
    ]
    return buildings, meetings, (33.600, -117.800)  # user standing at NEAR


def test_haversine_zero_distance():
    assert haversine_m(33.6, -117.8, 33.6, -117.8) == 0.0


def test_haversine_known_distance():
    # 0.001 deg of latitude is ~111 m
    d = haversine_m(33.6, -117.8, 33.601, -117.8)
    assert 100 < d < 120


def test_occurs_today():
    m = _meet("m", "NEAR", days="TuTh")
    assert occurs_today(m, "Tu")
    assert occurs_today(m, "Th")
    assert not occurs_today(m, "M")


def test_extract_section_type():
    assert extract_section_type("AC_ENG_20A-20001-Lec-B") == "Lec"
    assert extract_section_type("unparseable") == ""


def test_extract_course_level():
    assert extract_course_level("CS 46") == "lower"
    assert extract_course_level("CS 101") == "upper"
    assert extract_course_level("CS 201") == "grad"
    assert extract_course_level("SEMINAR") == "other"


def test_score_candidate_sooner_scores_higher():
    cfg = RankConfig()
    sooner = score_candidate(0, 100, cfg)[0]
    later  = score_candidate(cfg.time_window_min, 100, cfg)[0]
    assert sooner > later


def test_score_candidate_closer_scores_higher():
    cfg = RankConfig()
    closer = score_candidate(10, 0, cfg)[0]
    farther = score_candidate(10, cfg.max_distance_m, cfg)[0]
    assert closer > farther


def test_filter_respects_window_distance_and_day():
    buildings, meetings, user = _fixture()
    cands = filter_candidates(meetings, buildings, user, "M", 600, RankConfig())
    ids = {m.meeting_id for m, _, _ in cands}
    assert "soon-near" in ids
    assert "later-near" not in ids   # outside the 60 min window
    assert "soon-far" not in ids     # beyond the 1200 m radius
    assert "tue-near" not in ids     # not meeting today


def test_rank_orders_by_score_and_limits_top_k():
    buildings, meetings, user = _fixture()
    ranked = rank_meetings(meetings, buildings, user, "M", 600, RankConfig(), top_k=1)
    assert len(ranked) == 1
    assert ranked[0].meeting.meeting_id == "soon-near"


def test_fallback_returns_primary_when_matches_exist():
    buildings, meetings, user = _fixture()
    results, mode = rank_with_fallback(meetings, buildings, user, "M", 600, RankConfig())
    assert mode == "primary"
    assert results


def test_fallback_widens_when_nothing_soon():
    buildings, meetings, user = _fixture()
    # 6:40am: the first class is 210 min away, outside the 60 min window
    results, mode = rank_with_fallback(meetings, buildings, user, "M", 400, RankConfig())
    assert mode == "widened"
    assert results  # nearest upcoming classes surface via the widened window


def test_fallback_none_when_day_has_no_classes():
    buildings, meetings, user = _fixture()
    results, mode = rank_with_fallback(meetings, buildings, user, "Su", 600, RankConfig())
    assert mode == "none"
    assert results == []


def test_day_has_meetings():
    _, meetings, _ = _fixture()
    assert day_has_meetings(meetings, "M")
    assert day_has_meetings(meetings, "Tu")
    assert not day_has_meetings(meetings, "Su")
