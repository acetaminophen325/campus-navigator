#!/usr/bin/env python3
"""
scrape_buildings.py - UCI Campus Building Location Scraper

Fetches building coordinates for the UCI campus from two sources:
  1. OpenStreetMap Overpass API  (live, requires internet)
  2. A curated hardcoded fallback table (always available)

Usage:
  python scripts/scrape_buildings.py              # merge Overpass + fallback -> data/buildings.csv
  python scripts/scrape_buildings.py --fallback   # use fallback table only (no network needed)
  python scripts/scrape_buildings.py --out PATH   # write to a custom CSV path
  python scripts/scrape_buildings.py --show       # print result table, don't write
"""

import argparse
import csv
import sys
import time
from pathlib import Path

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Bounding box that covers the entire UCI main campus
UCI_BBOX = (33.628, -117.862, 33.662, -117.825)   # south, west, north, east

# Keys are substrings that appear in OSM building names; values are building codes.
# Longer / more specific strings should appear first so they match before shorter ones.
NAME_TO_CODE: dict[str, str] = {
    # Engineering
    "Interdisciplinary Science and Engineering": "ISEB",
    "Engineering Gateway":                       "EG",
    "Engineering Computer Technologies":          "ECT",
    "Engineering Lecture Hall":                  "ELH",
    "Engineering Hall":                          "EH",
    "Engineering Tower":                         "ET",
    "Engineering Lab Facility":                  "ELF",
    # Physical / Natural Sciences
    "Frederick Reines Hall":                     "FRH",
    "Physical Sciences Classroom":               "PSCB",
    "Physical Sciences Lecture Hall":            "PSLH",
    "Natural Sciences II":                       "NS2",
    "Natural Sciences I":                        "NS1",
    "Natural Sciences 2":                        "NS2",
    "Natural Sciences 1":                        "NS1",
    "Multipurpose Science and Technology":       "MSTB",
    "Biological Sciences III":                   "BS3",
    "Biological Sciences 3":                     "BS3",
    # Computer / Information Science
    "Donald Bren Hall":                          "DBH",
    "Information and Computer Science":          "ICS",
    # Mathematics
    "Rowland Hall":                              "RH",
    # Social Sciences
    "Social Science Lecture Hall":               "SSLH",
    "Social Science Tower":                      "SST",
    "Social Science Plaza B":                    "SSPB",
    "Social Science Plaza A":                    "SSPA",
    "Social Science Hall":                       "SSH",
    "Social Science Lab":                        "SSL",
    "Social & Behavioral Sciences Gateway":      "SBSG",
    "Social and Behavioral Sciences Gateway":    "SBSG",
    "Social & Behavioral Sciences 2":            "SB2",
    "Social & Behavioral Sciences 1":            "SB1",
    "Krieger Hall":                              "KH",
    # Humanities
    "Humanities Gateway":                        "HG",
    "Humanities Hall":                           "HH",
    "Humanities Instructional Building":         "HIB",
    "Howard Schneiderman Lecture Hall":          "HSLH",
    # Arts
    "Winifred Smith Hall":                       "WSH",
    "Contemporary Arts Center":                  "CAC",
    "Studio Art":                                "ART",
    "Drama":                                     "DRA",
    "Music Hall":                                "MH",
    # Law / Business / Other Schools
    "Law":                                       "LAW",
    "Paul Merage":                               "PCB",
    "Education":                                 "EDUC",
    "Public Health":                             "SPH",
    # Recreation
    "Anteater Recreation Center":                "REC",
    # Administration
    "Information and Administration":            "IAB",
    "Aldrich Park":                              "ALP",
    # Data / Research
    "Calit2":                                    "DS",
    "Data Science":                              "DS",
    # Medical / Health
    "Medical Science 2":                         "MS2",
    "Medical Arts":                              "MAB",
}

# Curated fallback table
# Source: UCI campus maps, official building pages, and cross-referenced coordinates.
# Format: code -> (name, lat, lon)
FALLBACK: dict[str, tuple[str, float, float]] = {
    # Mathematics / Physical Sciences
    "RH":   ("Rowland Hall",                              33.64450, -117.84410),
    "PSLH": ("Physical Sciences Lecture Hall",            33.64340, -117.84395),
    "PSCB": ("Physical Sciences Classroom Building",      33.64330, -117.84515),
    "NS1":  ("Natural Sciences 1",                        33.64220, -117.84590),
    "NS2":  ("Natural Sciences 2",                        33.64417, -117.84528),
    "FRH":  ("Frederick Reines Hall",                     33.64130, -117.84540),
    "MSTB": ("Multipurpose Science and Technology Bldg",  33.64200, -117.84440),
    "BS3":  ("Biological Sciences 3",                     33.64110, -117.84360),
    # Engineering
    "ET":   ("Engineering Tower",                         33.64470, -117.84110),
    "EH":   ("Engineering Hall",                          33.64360, -117.84140),
    "EG":   ("Engineering Gateway",                       33.64323, -117.84036),
    "ELH":  ("Engineering Lecture Hall",                  33.64430, -117.84070),
    "ELF":  ("Engineering Lab Facility",                  33.64390, -117.84050),
    "ECT":  ("Engineering Computer Technologies",         33.64450, -117.84080),
    "SE":   ("Science Engineering",                       33.64480, -117.84220),
    "SE2":  ("Science Engineering 2",                     33.64440, -117.83960),
    "ISEB": ("Interdisciplinary Science & Engineering",   33.64280, -117.84400),
    # Computer / Information Science
    "DBH":  ("Donald Bren Hall",                          33.64320, -117.84190),
    "ICS":  ("Information and Computer Science 1",        33.64420, -117.84180),
    # Social Sciences
    "SSL":  ("Social Science Lab",                        33.64590, -117.84000),
    "SSH":  ("Social Science Hall",                       33.64620, -117.84010),
    "SST":  ("Social Science Tower",                      33.64650, -117.84010),
    "SSTR": ("Social Science Tower (annex)",              33.64650, -117.84010),
    "SSLH": ("Social Science Lecture Hall",               33.64720, -117.83970),
    "SSPA": ("Social Science Plaza A",                    33.64690, -117.84040),
    "SSPB": ("Social Science Plaza B",                    33.64730, -117.84130),
    "SB1":  ("Social & Behavioral Sciences 1",            33.64650, -117.84160),
    "SB2":  ("Social & Behavioral Sciences 2",            33.64680, -117.84110),
    "SBSG": ("Social & Behavioral Sciences Gateway",      33.64750, -117.84080),
    "KH":   ("Krieger Hall",                              33.64560, -117.84290),
    "SCS":  ("Social Sciences Computing Suite",           33.64640, -117.84030),
    # Humanities
    "HG":   ("Humanities Gateway",                        33.64830, -117.84470),
    "HH":   ("Humanities Hall",                           33.64730, -117.84400),
    "HHCR": ("Humanities Hall Conference Room",           33.64730, -117.84400),
    "HIB":  ("Humanities Instructional Building",         33.64790, -117.84410),
    "HICF": ("Humanities Instructional Complex F",        33.64810, -117.84370),
    "HSLH": ("Howard Schneiderman Lecture Hall",          33.64550, -117.84470),
    # Arts
    "DRA":  ("Drama",                                     33.64920, -117.84320),
    "MH":   ("Music Hall",                                33.64870, -117.84360),
    "ART":  ("Studio Arts",                               33.64960, -117.84280),
    "CAC":  ("Contemporary Arts Center",                  33.64990, -117.84410),
    "WSH":  ("Winifred Smith Hall",                       33.65080, -117.84330),
    "MPAA": ("Mesa Parking & Arts Annex",                 33.64850, -117.84190),
    # Law / Business / Education
    "LAW":  ("School of Law",                             33.65020, -117.84020),
    "PCB":  ("Paul Merage School of Business",            33.65190, -117.84220),
    "EDUC": ("Education Building",                        33.64870, -117.84090),
    "SPH":  ("School of Public Health",                   33.64180, -117.84280),
    "COHS": ("College of Health Sciences",                33.64190, -117.84300),
    "MAB":  ("Medical Academic Building",                 33.64120, -117.84350),
    "CRH":  ("Crystal Cove Auditorium",                   33.64530, -117.84140),
    # Recreation / Administration
    "REC":  ("Anteater Recreation Center",                33.64840, -117.83940),
    "AIRB": ("Anteater Instruction & Research Bldg",      33.64880, -117.83960),
    "AITR": ("Anteater Instruction & Research",           33.64870, -117.83910),
    "ACT":  ("Activities & Campus Trailers",              33.64640, -117.84210),
    "ALP":  ("Aldrich Park",                              33.64600, -117.84280),
    "IAB":  ("Information & Administration Building",     33.64930, -117.84530),
    "UEA":  ("University Extension Annex",                33.64980, -117.84680),
    "DS":   ("Calit2 / Data Science Building",            33.64440, -117.84280),
    "CTT":  ("Continuing Education/Tech Trailers",        33.64620, -117.84260),
    "PSTU": ("Provost Student Teaching Unit",             33.64500, -117.84230),
    "SH":   ("Sprague Hall",                              33.64270, -117.84470),
    "PH":   ("Peltason Hall",                             33.64380, -117.84490),
    "MS2":  ("Medical Sciences 2",                        33.64100, -117.84330),
    "MOB":  ("Mesa Oak Building",                         33.64120, -117.84380),
    "MDE":  ("Mesa Court Dining East",                    33.64840, -117.84050),
    "MM":   ("Middle Meeting Hall",                       33.64800, -117.84060),
    "STU4": ("Student Housing 4",                         33.64860, -117.84020),
    # ON, VRTL, UCI are intentionally omitted (no GPS coordinates)
}


def fetch_overpass(bbox: tuple) -> list[dict]:
    """Query Overpass for named buildings within bbox and return a flat list."""
    if not _HAS_REQUESTS:
        print("[WARN] 'requests' package not installed; skipping Overpass fetch.", file=sys.stderr)
        return []

    south, west, north, east = bbox
    query = f"""
[out:json][timeout:40];
(
  way["building"]["name"]({south},{west},{north},{east});
  relation["building"]["name"]({south},{west},{north},{east});
  node["amenity"]["name"]({south},{west},{north},{east});
);
out center tags;
"""
    try:
        print("[INFO] Querying Overpass API...", file=sys.stderr)
        r = requests.post(OVERPASS_URL, data={"data": query}, timeout=50)
        r.raise_for_status()
        elements = r.json().get("elements", [])
        print(f"[INFO] Got {len(elements)} elements from Overpass.", file=sys.stderr)
        return elements
    except Exception as exc:
        print(f"[WARN] Overpass query failed: {exc}", file=sys.stderr)
        return []


def parse_overpass_elements(elements: list) -> dict[str, tuple[str, float, float]]:
    """Convert raw Overpass elements into {code: (name, lat, lon)} using NAME_TO_CODE."""
    result: dict[str, tuple[str, float, float]] = {}

    for el in elements:
        tags = el.get("tags", {})
        name: str = tags.get("name", "").strip()
        if not name:
            continue

        # Determine centre coordinates
        if "center" in el:
            lat, lon = el["center"]["lat"], el["center"]["lon"]
        elif "lat" in el:
            lat, lon = el["lat"], el["lon"]
        else:
            continue

        # Check if any key substring matches
        for key, code in NAME_TO_CODE.items():
            if key.lower() in name.lower():
                if code not in result:          # first (longest) match wins
                    result[code] = (name, lat, lon)
                break

    return result


def main():
    parser = argparse.ArgumentParser(description="Scrape UCI campus building coordinates.")
    parser.add_argument("--fallback", action="store_true",
                        help="Use the hardcoded fallback table only (no network request).")
    parser.add_argument("--out", default=None,
                        help="Output CSV path (default: data/buildings.csv relative to project root).")
    parser.add_argument("--show", action="store_true",
                        help="Print the result table to stdout instead of writing a file.")
    args = parser.parse_args()

    # Locate project root (two levels up from scripts/)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    default_out = project_root / "data" / "buildings.csv"
    out_path = Path(args.out) if args.out else default_out

    # Start with the hardcoded fallback
    combined: dict[str, tuple[str, float, float]] = dict(FALLBACK)

    # Overwrite / extend with live Overpass data (unless --fallback flag)
    if not args.fallback:
        elements = fetch_overpass(UCI_BBOX)
        live = parse_overpass_elements(elements)
        print(f"[INFO] Overpass matched {len(live)} building codes.", file=sys.stderr)
        for code, triple in live.items():
            combined[code] = triple   # live data wins over hardcoded

    # Sort by building code and output
    rows = sorted(combined.items(), key=lambda x: x[0])

    if args.show:
        print(f"{'Code':<8} {'Name':<55} {'Lat':>10} {'Lon':>12}")
        print("-" * 90)
        for code, (name, lat, lon) in rows:
            print(f"{code:<8} {name:<55} {lat:>10.5f} {lon:>12.5f}")
        print(f"\n{len(rows)} buildings total.")
    else:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["code", "name", "lat", "lon"])
            for code, (name, lat, lon) in rows:
                writer.writerow([code, name, f"{lat:.5f}", f"{lon:.5f}"])
        print(f"[OK] Wrote {len(rows)} buildings → {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
