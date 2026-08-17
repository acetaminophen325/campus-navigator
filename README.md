# Campus Navigator

A live, location-aware web app for finding the UC Irvine class sections meeting near you right now, ranked by how close and how soon they are, with real walking routes, a "can you make it?" estimate, and optional keyword search. Built in Python.

![Campus Navigator ranking nearby classes with a walking route drawn to Engineering Tower and can-you-make-it badges](assets/demo.png)

## Overview

Campus Navigator answers a specific question: "what classes are meeting close to me, soon, and can I get there in time?" It runs in two modes:

- **Live** (default), like a maps app: it follows your real GPS location and the clock, and re-ranks nearby classes automatically as you move or time passes.
- **Custom**, for exploring or demoing: simulate any position (pick a building or click the map) and any day and time.

For a given position and time it returns the nearby class sections about to start or in progress, ranked and plotted on a Leaflet map. Click a result to draw the walking route to it and see the walking time.

## Features

- **Live tracking and simulation.** Live mode uses the browser Geolocation API (`watchPosition`) plus a ticking clock and auto re-ranking; Custom mode simulates a position (building dropdown or map click) and a chosen day/time.
- **Ranking** by a weighted blend of time-proximity and distance, plus optional **BM25** keyword relevance over course titles and departments.
- **Walking routes.** Clicking a result runs A* over a real OpenStreetMap footpath graph and draws the route with its walking distance and time.
- **"Can I make it?"** Each result shows the walking time versus minutes-until-start as a badge: easy, tight, too late, or in progress.
- **Filters** for department, course level (lower / upper / grad), and section type (lecture, lab, discussion, and so on).
- **Graceful empty state.** If nothing is within the window and radius, the search widens to the rest of the day and a larger radius and says so, instead of dead-ending.
- **Two-view sidebar.** Controls and results swap, so results get the full panel with a "Back to search" button and a context line.

## How It Works

- **Data pipeline.** A WebSoc scraper (`src/websoc/`) pulls UCI's published class schedule; `scripts/parse_websoc_json.py` turns the raw JSON into `data/meetings.csv`, and `scripts/scrape_buildings.py` collects building coordinates into `data/buildings.csv`. `scripts/fetch_walk_graph.py` builds `data/walk_graph.json` from OpenStreetMap walkable ways via the Overpass API.
- **Ranking.** For a day, time, and origin, candidates are kept only if they meet that day, start within the look-ahead window (default 60 min) or are ongoing, and fall within the straight-line distance cutoff (default 1200 m). Each is scored by a blend of time-proximity, distance, and (when a query is present) BM25 relevance, using configurable weights (`RankConfig`); the top-k are returned. If the result is empty, the search widens once.
- **Routing and feasibility.** Buildings are snapped to the nearest walk-graph node at startup. One multi-target Dijkstra per search attaches real walking times to every result (so k results cost one search, not k), and `/api/route` runs A* for a single point-to-building path. Walking time versus minutes-until-start yields the feasibility label. Without the graph file, walk times fall back to straight-line estimates.
- **BM25.** The text index scores each meeting's `title + department` with standard BM25 (k1 = 1.5, b = 0.75), normalized to [0, 1] before blending.

## API

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/rank` | POST | Ranked nearby classes with walk times and feasibility |
| `/api/route` | POST | A* walking polyline from a point to a building |
| `/api/buildings` | GET | Building list with coordinates |
| `/api/departments` | GET | Distinct departments (for the filter) |
| `/api/days` | GET | Day tokens that actually have classes |

## Tech Stack

Python with Flask for the API. The frontend is vanilla HTML/CSS/JavaScript using Leaflet.js and OpenStreetMap tiles. Data acquisition uses `requests`. There is no database; data lives in CSV/JSON files loaded into memory at startup. Runtime deps are in `requirements.txt` (`flask`, `requests`); test deps in `requirements-dev.txt` (`pytest`).

## Project Structure

```text
├─ src/
│  ├─ api.py                    # Flask API (rank, route, buildings, departments, days)
│  ├─ ranker.py                 # filtering, weighted scoring, empty-state fallback, feasibility
│  ├─ search.py                 # BM25 index over course titles + departments
│  ├─ graph.py                  # walking graph: nearest-node snap, A*, multi-target Dijkstra
│  ├─ models.py                 # Building, Meeting, RankedResult dataclasses
│  ├─ io.py                     # CSV loaders for buildings and meetings
│  ├─ demo.py                   # CLI demo: two scenarios with an explainability breakdown
│  └─ websoc/                   # WebSoc (UCI schedule) scraper package
├─ scripts/
│  ├─ fetch_walk_graph.py       # OSM footpaths -> data/walk_graph.json
│  ├─ parse_websoc_json.py      # WebSoc JSON -> data/meetings.csv
│  └─ scrape_buildings.py       # building coordinates -> data/buildings.csv
├─ frontend/
│  ├─ index.html
│  ├─ app.js                    # map, live/custom modes, search, routing, results
│  └─ style.css
├─ data/
│  ├─ buildings.csv             # code, name, lat, lon
│  ├─ meetings.csv              # class sections: id, course, title, dept, days, times, building, room, term
│  ├─ websoc_raw.json           # raw scraped schedule (input to the parser)
│  └─ walk_graph.json           # OSM walking graph: nodes + edges
├─ tests/                       # pytest suite: ranker, BM25, graph/A*, feasibility
├─ requirements.txt
├─ requirements-dev.txt
├─ pytest.ini
└─ README.md
```

## Running it

From the repo root:

```text
pip install -r requirements.txt
python -m src.api        # serves the web app at http://localhost:5000
```

The class, building, and walking-graph data are already checked in under `data/`, so it runs with no setup. Optional data refresh:

```text
python -m scripts.fetch_walk_graph   # rebuild the OSM walking graph
```

Command-line demo instead of the web UI:

```text
python -m src.demo
```

## Testing

```text
pip install -r requirements-dev.txt
pytest
```

31 tests cover the ranker, the BM25 index, the walking graph (A* shortest paths, multi-target Dijkstra), and feasibility classification. A GitHub Actions workflow runs them on every push and pull request.

## Contribution

Group final project for UC Irvine CS 125. Nearly all of the code is mine: the ranking engine, the BM25 search index, the A* routing and walking-graph pipeline, the Flask API, the Leaflet web UI (including live tracking and the route/feasibility layer), the CLI demo, and the building and meeting data parsing. My teammate Jeffrey Li contributed the initial WebSoc scraper and the first raw schedule data file.
