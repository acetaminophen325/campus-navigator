"""
src/api.py
Flask API server for the campus navigator web UI.

Run with:
    python -m src.api
Then open http://localhost:5000
"""
from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from .io import load_buildings_csv, load_meetings_csv
from .ranker import RankConfig, fmt_time, rank_meetings, extract_section_type, extract_course_level

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.parent  # project root
DATA_DIR = BASE_DIR / "data"
FRONTEND_DIR = BASE_DIR / "frontend"

# ---------------------------------------------------------------------------
# Load data once at startup
# ---------------------------------------------------------------------------
BUILDINGS = load_buildings_csv(DATA_DIR / "buildings.csv")
MEETINGS = load_meetings_csv(DATA_DIR / "meetings.csv")

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")


@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/api/buildings")
def api_buildings():
    """Return all known buildings with coordinates."""
    result = [
        {
            "code": b.code,
            "name": b.name,
            "lat": b.lat,
            "lon": b.lon,
        }
        for b in BUILDINGS.values()
    ]
    result.sort(key=lambda b: b["name"])
    return jsonify({"buildings": result})


@app.route("/api/departments")
def api_departments():
    """Return all unique departments found in the meetings data, sorted alphabetically."""
    depts = sorted({m.dept for m in MEETINGS if m.dept})
    return jsonify({"departments": depts})


@app.route("/api/rank", methods=["POST"])
def api_rank():
    """
    Rank nearby meetings.

    Expected JSON body:
        lat           float  – user latitude
        lon           float  – user longitude
        day           str    – day token: M Tu W Th F Sa Su
        now_min       int    – minutes since midnight
        include_ongoing bool – whether to include in-progress meetings
        top_k         int    – max results (default 10)
    """
    body = request.get_json(force=True, silent=True) or {}

    # --- validate required fields ---
    missing = [f for f in ("lat", "lon", "day", "now_min") if f not in body]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400

    try:
        user_lat = float(body["lat"])
        user_lon = float(body["lon"])
        day_token = str(body["day"])
        now_min = int(body["now_min"])
        include_ongoing = bool(body.get("include_ongoing", True))
        top_k = int(body.get("top_k", 10))
        dept_filter = str(body.get("dept_filter", ""))
        level_filters = [str(x) for x in body.get("level_filters", [])]
        type_filters  = [str(x) for x in body.get("type_filters", [])]
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400

    cfg = RankConfig()
    ranked = rank_meetings(
        meetings=MEETINGS,
        buildings=BUILDINGS,
        user_latlon=(user_lat, user_lon),
        day_token=day_token,
        now_min=now_min,
        cfg=cfg,
        top_k=top_k,
        include_ongoing=include_ongoing,
        dept_filter=dept_filter,
        level_filters=level_filters,
        type_filters=type_filters,
    )

    results = []
    for r in ranked:
        m = r.meeting
        bldg = BUILDINGS.get(m.building_code)
        results.append(
            {
                "course_id": m.course_id,
                "title": m.title,
                "dept": m.dept,
                "days": m.days,
                "start_time": fmt_time(m.start_min),
                "end_time": fmt_time(m.end_min),
                "building_code": m.building_code,
                "building_name": bldg.name if bldg else m.building_code,
                "room": m.room,
                "lat": bldg.lat if bldg else None,
                "lon": bldg.lon if bldg else None,
                "score": round(r.score, 4),
                "time_score": round(r.time_score, 4),
                "dist_score": round(r.dist_score, 4),
                "minutes_until_start": r.minutes_until_start,
                "distance_m": round(r.distance_m, 1),
                "section_type": extract_section_type(m.meeting_id),
                "course_level": extract_course_level(m.course_id),
            }
        )

    return jsonify({"results": results})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, port=port)
