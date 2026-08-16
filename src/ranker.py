# src/ranker.py
from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Tuple

from .models import Building, Meeting, RankedResult
from .search import BM25Index


@dataclass(frozen=True)
class RankConfig:
    time_window_min: int = 60       # look-ahead window in minutes
    max_distance_m: float = 1200.0  # hard distance cutoff

    # Weights when no text query is given
    w_time: float = 0.6
    w_dist: float = 0.4

    # Weights when a text query is active (must sum to 1.0)
    w_time_text: float = 0.5
    w_dist_text: float = 0.25
    w_text:      float = 0.25


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi   = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def occurs_today(meeting: Meeting, day_token: str) -> bool:
    """day_token: 'M', 'Tu', 'W', 'Th', 'F', 'Sa', 'Su'"""
    return day_token in meeting.days


def minutes_until_start(meeting: Meeting, now_min: int) -> int:
    return meeting.start_min - now_min


def extract_section_type(meeting_id: str) -> str:
    """
    Parses the section type from a meeting_id like AC_ENG_20A-20001-Lec-B.
    Returns the type token (e.g. 'Lec', 'Lab', 'Dis') or '' if unparseable.
    """
    parts = meeting_id.split("-")
    if len(parts) >= 3:
        return parts[-2]
    return ""


def extract_course_level(course_id: str) -> str:
    """
    Buckets a UCI course number into 'lower' (<100), 'upper' (100-199),
    'grad' (200+), or 'other'.
    """
    m = re.search(r"\b(\d+)", course_id)
    if m:
        n = int(m.group(1))
        if n < 100:
            return "lower"
        elif n < 200:
            return "upper"
        else:
            return "grad"
    return "other"


def filter_candidates(
    meetings: List[Meeting],
    buildings: Dict[str, Building],
    user_latlon: Tuple[float, float],
    day_token: str,
    now_min: int,
    cfg: RankConfig,
    include_ongoing: bool = True,
    dept_filter: str = "",
    level_filters: List[str] = [],
    type_filters: List[str] = [],
) -> List[Tuple[Meeting, int, float]]:
    """
    Pre-filters the meeting list before scoring.
    Returns (meeting, minutes_until_start, distance_m) tuples.
    """
    user_lat, user_lon = user_latlon
    out: List[Tuple[Meeting, int, float]] = []

    for m in meetings:
        if not occurs_today(m, day_token):
            continue

        b = buildings.get(m.building_code)
        if b is None:
            continue

        if dept_filter and dept_filter.lower() not in m.dept.lower():
            continue

        if level_filters and extract_course_level(m.course_id) not in level_filters:
            continue

        if type_filters and extract_section_type(m.meeting_id) not in type_filters:
            continue

        mins_until = minutes_until_start(m, now_min)
        if mins_until < 0:
            if not (include_ongoing and now_min < m.end_min):
                continue
        elif mins_until > cfg.time_window_min:
            continue

        dist = haversine_m(user_lat, user_lon, b.lat, b.lon)
        if dist > cfg.max_distance_m:
            continue

        out.append((m, mins_until, dist))

    return out


def score_candidate(
    min_until: int,
    dist_m: float,
    cfg: RankConfig,
    text_score: float = 0.0,
    has_query: bool = False,
) -> Tuple[float, float, float]:
    """
    Returns (final_score, time_score, dist_score).
    When has_query is True, blends in the pre-computed text_score using
    the text-mode weights from cfg.
    """
    time_score = max(0.0, min(1.0,
        1.0 - (min_until / float(cfg.time_window_min)) if cfg.time_window_min > 0
        else (1.0 if min_until <= 0 else 0.0)
    ))

    dist_score = max(0.0, min(1.0,
        1.0 - (dist_m / float(cfg.max_distance_m)) if cfg.max_distance_m > 0
        else (1.0 if dist_m == 0 else 0.0)
    ))

    if has_query:
        final = cfg.w_time_text * time_score + cfg.w_dist_text * dist_score + cfg.w_text * text_score
    else:
        final = cfg.w_time * time_score + cfg.w_dist * dist_score

    return final, time_score, dist_score


def rank_meetings(
    meetings: List[Meeting],
    buildings: Dict[str, Building],
    user_latlon: Tuple[float, float],
    day_token: str,
    now_min: int,
    cfg: RankConfig,
    top_k: int = 10,
    include_ongoing: bool = True,
    dept_filter: str = "",
    level_filters: List[str] = [],
    type_filters: List[str] = [],
    query: str = "",
    bm25: Optional[BM25Index] = None,
) -> List[RankedResult]:
    """
    Full ranking pipeline: filter -> score -> sort -> top-k.

    If a non-empty query is provided and a BM25Index is supplied, text
    relevance scores are computed and blended into the final score using
    the text-mode weights in cfg.
    """
    candidates = filter_candidates(
        meetings=meetings,
        buildings=buildings,
        user_latlon=user_latlon,
        day_token=day_token,
        now_min=now_min,
        cfg=cfg,
        include_ongoing=include_ongoing,
        dept_filter=dept_filter,
        level_filters=level_filters,
        type_filters=type_filters,
    )

    has_query = bool(query.strip()) and bm25 is not None
    text_scores: Dict[str, float] = bm25.score_map(query) if has_query else {}

    ranked: List[RankedResult] = []
    for m, mins_until, dist_m in candidates:
        t_score_val = text_scores.get(m.meeting_id, 0.0)
        score, t_score, d_score = score_candidate(
            mins_until, dist_m, cfg,
            text_score=t_score_val,
            has_query=has_query,
        )
        ranked.append(RankedResult(
            meeting=m,
            score=score,
            minutes_until_start=mins_until,
            distance_m=dist_m,
            time_score=t_score,
            dist_score=d_score,
            text_score=t_score_val,
        ))

    ranked.sort(key=lambda r: r.score, reverse=True)
    return ranked[:top_k]


# When the primary search finds nothing, widen to the rest of the day and a
# larger radius so the app always shows the nearest upcoming classes rather
# than a dead end.
FALLBACK_WINDOW_MIN = 24 * 60
FALLBACK_DISTANCE_FACTOR = 3.0


def rank_with_fallback(
    meetings: List[Meeting],
    buildings: Dict[str, Building],
    user_latlon: Tuple[float, float],
    day_token: str,
    now_min: int,
    cfg: RankConfig,
    top_k: int = 10,
    include_ongoing: bool = True,
    dept_filter: str = "",
    level_filters: List[str] = [],
    type_filters: List[str] = [],
    query: str = "",
    bm25: Optional[BM25Index] = None,
) -> Tuple[List[RankedResult], str]:
    """
    Rank, and if nothing is found in the configured window/radius, widen once.

    Returns (results, mode):
      - "primary": results found within the normal window and distance
      - "widened": nothing nearby soon, so results come from a longer
                   look-ahead window and a larger radius
      - "none":    still nothing (e.g. no classes meet on this day at all)
    """
    kwargs = dict(
        meetings=meetings, buildings=buildings, user_latlon=user_latlon,
        day_token=day_token, now_min=now_min, top_k=top_k,
        include_ongoing=include_ongoing, dept_filter=dept_filter,
        level_filters=level_filters, type_filters=type_filters,
        query=query, bm25=bm25,
    )

    results = rank_meetings(cfg=cfg, **kwargs)
    if results:
        return results, "primary"

    wide_cfg = replace(
        cfg,
        time_window_min=FALLBACK_WINDOW_MIN,
        max_distance_m=cfg.max_distance_m * FALLBACK_DISTANCE_FACTOR,
    )
    results = rank_meetings(cfg=wide_cfg, **kwargs)
    if results:
        return results, "widened"

    return [], "none"


def day_has_meetings(meetings: List[Meeting], day_token: str) -> bool:
    """True if any meeting occurs on the given day, ignoring time and distance."""
    return any(occurs_today(m, day_token) for m in meetings)


def fmt_time(mins: int) -> str:
    mins = int(mins)
    h24 = mins // 60
    m   = mins % 60
    ampm = "am" if h24 < 12 else "pm"
    h12  = h24 % 12 or 12
    return f"{h12}:{m:02d}{ampm}"
