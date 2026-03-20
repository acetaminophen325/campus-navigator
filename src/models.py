from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Building:
    code: str
    name: str
    lat: float
    lon: float


@dataclass(frozen=True)
class Meeting:
    meeting_id: str
    course_id: str
    title: str
    dept: str
    days: str          # e.g., "MWF", "TuTh"
    start_min: int     # minutes since midnight
    end_min: int       # minutes since midnight
    building_code: str
    room: str
    term: str


@dataclass(frozen=True)
class RankedResult:
    meeting: Meeting
    score: float
    minutes_until_start: int
    distance_m: float
    time_score: float
    dist_score: float
    text_score: float = 0.0
