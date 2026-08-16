const UCI_CENTER = [33.6405, -117.8443];
const UCI_ZOOM   = 16;
const DAY_TOKENS = ["Su", "M", "Tu", "W", "Th", "F", "Sa"];
const DAY_NAMES  = {
  Su: "Sunday", M: "Monday", Tu: "Tuesday", W: "Wednesday",
  Th: "Thursday", F: "Friday", Sa: "Saturday",
};

// Live mode tuning
const LIVE_TICK_MS        = 30000; // clock/re-rank cadence
const LIVE_MOVE_THRESH_M  = 30;    // re-rank when we move at least this far

// App state
let mode            = "custom";  // "live" | "custom"
let userLatLon      = null;
let availableDays   = [];        // day tokens that actually have classes in the data
let buildingsData   = [];
let buildingMarkers = {};
let resultMarkers   = [];
let userMarker      = null;
let routeLine       = null;
let activeCardIndex = null;
let lastResults     = [];
let watchId         = null;
let liveTimer       = null;
let lastSearchPos   = null;      // [lat, lon] at the time of the last live search
let lastSearchMin   = null;      // minutes-since-midnight of the last live search
let searching       = false;
let firstSearchDone = false;

// Map
const map = L.map("map").setView(UCI_CENTER, UCI_ZOOM);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 19,
}).addTo(map);

// DOM
const modeLiveBtn        = document.getElementById("mode-live");
const modeCustomBtn      = document.getElementById("mode-custom");
const modeHint           = document.getElementById("mode-hint");
const btnGeolocate       = document.getElementById("btn-geolocate");
const buildingSelect     = document.getElementById("building-select");
const daySelect          = document.getElementById("day-select");
const timeInput          = document.getElementById("time-input");
const btnNow             = document.getElementById("btn-now");
const chkOngoing         = document.getElementById("chk-ongoing");
const btnSearch          = document.getElementById("btn-search");
const locationStatus     = document.getElementById("location-status");
const searchError        = document.getElementById("search-error");
const searchView         = document.getElementById("search-view");
const resultsView        = document.getElementById("results-view");
const btnBack            = document.getElementById("btn-back");
const resultsList        = document.getElementById("results-list");
const resultsCount       = document.getElementById("results-count");
const resultsContext     = document.getElementById("results-context");
const resultsNote        = document.getElementById("results-note");
const btnFiltersToggle   = document.getElementById("btn-filters-toggle");
const filtersPanel       = document.getElementById("filters-panel");
const filtersActiveBadge = document.getElementById("filters-active-badge");
const filterDept         = document.getElementById("filter-dept");
const chkLevels          = document.querySelectorAll(".chk-level");
const chkTypes           = document.querySelectorAll(".chk-type");
const btnFiltersClear    = document.getElementById("btn-filters-clear");
const queryInput         = document.getElementById("query-input");
const btnQueryClear      = document.getElementById("btn-query-clear");

// Helpers
function nowDayToken() { return DAY_TOKENS[new Date().getDay()]; }

function nowTimeStr() {
  const d = new Date();
  return `${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}`;
}

function nowMinOfDay() {
  const d = new Date();
  return d.getHours() * 60 + d.getMinutes();
}

function timeStrToMin(t) {
  const [h, m] = t.split(":").map(Number);
  return h * 60 + m;
}

function clockStr() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function haversineM(lat1, lon1, lat2, lon2) {
  const R = 6371000, rad = Math.PI / 180;
  const dphi = (lat2 - lat1) * rad, dlam = (lon2 - lon1) * rad;
  const a = Math.sin(dphi/2)**2 + Math.cos(lat1*rad) * Math.cos(lat2*rad) * Math.sin(dlam/2)**2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function scoreColor(score) {
  if (score >= 0.7) return "#22c55e";
  if (score >= 0.4) return "#f59e0b";
  return "#ef4444";
}

const FEAS = {
  easy:    { cls: "feas-easy",    label: (r) => `make it with ${r.spare_min} min to spare` },
  tight:   { cls: "feas-tight",   label: (r) => r.spare_min > 0 ? `tight — ${r.spare_min} min to spare` : "tight — arrive right at start" },
  late:    { cls: "feas-late",    label: () => "can't make it before start" },
  ongoing: { cls: "feas-ongoing", label: (r) => `in progress — ${r.walk_min} min away` },
};

function setUserPin(lat, lon, tooltip) {
  userLatLon = [lat, lon];
  if (userMarker) userMarker.remove();
  userMarker = L.circleMarker([lat, lon], {
    radius: 9, color: "#fff", weight: 2.5,
    fillColor: "#ef4444", fillOpacity: 1,
  }).addTo(map).bindTooltip(tooltip || "You are here");
  map.setView([lat, lon], Math.max(map.getZoom(), UCI_ZOOM));
  btnSearch.disabled = false;
  searchError.textContent = "";
}

function clearRoute() {
  if (routeLine) { routeLine.remove(); routeLine = null; }
}

// Sidebar has two swappable views: the controls and the results.
function showView(name) {
  const results = name === "results";
  resultsView.hidden = !results;
  searchView.hidden = results;
}

function min12(m) {
  let h = Math.floor(m / 60);
  const mm = m % 60;
  const ap = h < 12 ? "AM" : "PM";
  h = h % 12 || 12;
  return `${h}:${String(mm).padStart(2, "0")} ${ap}`;
}

function contextLabel(live, day, now_min) {
  if (live) return `Live · updated ${clockStr()}`;
  return `${DAY_NAMES[day] || day} · ${min12(now_min)}`;
}

btnBack.addEventListener("click", () => showView("search"));

/* ================================================================
   Mode switching: Live (continuous GPS + clock) vs Custom (simulated)
================================================================ */
function setModeButtons() {
  const live = mode === "live";
  modeLiveBtn.classList.toggle("is-active", live);
  modeCustomBtn.classList.toggle("is-active", !live);
  modeLiveBtn.setAttribute("aria-pressed", String(live));
  modeCustomBtn.setAttribute("aria-pressed", String(!live));
  // Simulated inputs only make sense in custom mode.
  daySelect.disabled = live;
  timeInput.disabled = live;
  btnNow.disabled = live;
  btnGeolocate.disabled = live;
  buildingSelect.disabled = live;
  document.body.classList.toggle("live-mode", live);
}

function enterLiveMode() {
  if (!navigator.geolocation) {
    modeHint.textContent = "Geolocation is unavailable in this browser, staying in custom mode.";
    enterCustomMode();
    return;
  }
  mode = "live";
  setModeButtons();
  modeHint.textContent = "Following your location and the clock. Results refresh automatically.";
  daySelect.value = nowDayToken();
  timeInput.value = nowTimeStr();

  watchId = navigator.geolocation.watchPosition(
    (pos) => {
      const { latitude: lat, longitude: lon } = pos.coords;
      const first = !userLatLon;
      setUserPin(lat, lon, "You are here (live)");
      locationStatus.textContent = `LIVE · GPS ${lat.toFixed(5)}, ${lon.toFixed(5)} · ${clockStr()}`;
      const moved = lastSearchPos
        ? haversineM(lat, lon, lastSearchPos[0], lastSearchPos[1]) : Infinity;
      if (first || moved >= LIVE_MOVE_THRESH_M) doSearch(true);
    },
    (err) => {
      modeHint.textContent = `Location error: ${err.message}. Switched to custom mode.`;
      enterCustomMode();
    },
    { enableHighAccuracy: true, maximumAge: 5000 }
  );

  liveTimer = setInterval(() => {
    if (mode !== "live") return;
    daySelect.value = nowDayToken();
    timeInput.value = nowTimeStr();
    if (userLatLon) {
      locationStatus.textContent =
        `LIVE · GPS ${userLatLon[0].toFixed(5)}, ${userLatLon[1].toFixed(5)} · ${clockStr()}`;
      // Re-rank when the clock has moved to a new minute since the last search.
      if (lastSearchMin === null || nowMinOfDay() !== lastSearchMin) doSearch(true);
    }
  }, LIVE_TICK_MS);
}

function enterCustomMode() {
  mode = "custom";
  if (watchId !== null) { navigator.geolocation.clearWatch(watchId); watchId = null; }
  if (liveTimer !== null) { clearInterval(liveTimer); liveTimer = null; }
  setModeButtons();
  modeHint.textContent = "Simulate any position and time: pick a building, click the map, and set day and time.";
}

modeLiveBtn.addEventListener("click", () => { if (mode !== "live") enterLiveMode(); });
modeCustomBtn.addEventListener("click", () => { if (mode !== "custom") enterCustomMode(); });

// Map click simulates a position in custom mode.
map.on("click", (e) => {
  if (mode !== "custom") return;
  const { lat, lng } = e.latlng;
  buildingSelect.value = "";
  setUserPin(lat, lng, "Simulated position");
  locationStatus.textContent = `Simulated: ${lat.toFixed(5)}, ${lng.toFixed(5)}`;
});

/* ================================================================
   Filters
================================================================ */
btnFiltersToggle.addEventListener("click", () => {
  const open = btnFiltersToggle.getAttribute("aria-expanded") === "true";
  btnFiltersToggle.setAttribute("aria-expanded", String(!open));
  filtersPanel.hidden = open;
});

function updateFiltersBadge() {
  let count = 0;
  if (filterDept.value) count++;
  chkLevels.forEach(c => { if (c.checked) count++; });
  chkTypes.forEach(c =>  { if (c.checked) count++; });
  filtersActiveBadge.textContent = count;
  filtersActiveBadge.hidden = count === 0;
}

filterDept.addEventListener("change", updateFiltersBadge);
chkLevels.forEach(c => c.addEventListener("change", updateFiltersBadge));
chkTypes.forEach(c =>  c.addEventListener("change", updateFiltersBadge));

btnFiltersClear.addEventListener("click", () => {
  filterDept.value = "";
  chkLevels.forEach(c => { c.checked = false; });
  chkTypes.forEach(c =>  { c.checked = false; });
  updateFiltersBadge();
});

function getFilters() {
  return {
    dept_filter:   filterDept.value,
    level_filters: [...chkLevels].filter(c => c.checked).map(c => c.value),
    type_filters:  [...chkTypes].filter(c =>  c.checked).map(c => c.value),
  };
}

// Query input
queryInput.addEventListener("input", () => {
  btnQueryClear.hidden = queryInput.value.trim() === "";
});

btnQueryClear.addEventListener("click", () => {
  queryInput.value = "";
  btnQueryClear.hidden = true;
  queryInput.focus();
});

/* ================================================================
   Data loading
================================================================ */
async function loadDepartments() {
  try {
    const res  = await fetch("/api/departments");
    const data = await res.json();
    data.departments.forEach(dept => {
      const opt = document.createElement("option");
      opt.value = dept;
      opt.textContent = dept;
      filterDept.appendChild(opt);
    });
  } catch (err) {
    console.warn("Could not load departments:", err);
  }
}

async function loadBuildings() {
  try {
    const res  = await fetch("/api/buildings");
    const data = await res.json();
    buildingsData = data.buildings;

    buildingsData.forEach(b => {
      const opt = document.createElement("option");
      opt.value = b.code;
      opt.textContent = `${b.name} (${b.code})`;
      buildingSelect.appendChild(opt);
    });

    buildingsData.forEach(b => {
      const marker = L.circleMarker([b.lat, b.lon], {
        radius: 7, color: "#0064a4", weight: 2,
        fillColor: "#0064a4", fillOpacity: 0.25,
      }).addTo(map);
      marker.bindTooltip(`<strong>${b.name}</strong><br>${b.code}`, {
        direction: "top", offset: [0, -6],
      });
      buildingMarkers[b.code] = marker;
    });
  } catch (err) {
    console.error("Failed to load buildings:", err);
    locationStatus.textContent = "Could not load buildings.";
  }
}

// Geolocation (custom mode: one-shot fix)
btnGeolocate.addEventListener("click", () => {
  if (!navigator.geolocation) {
    locationStatus.textContent = "Geolocation is not supported by this browser.";
    return;
  }
  locationStatus.textContent = "Detecting your location...";
  btnGeolocate.disabled = true;
  navigator.geolocation.getCurrentPosition(
    pos => {
      const { latitude: lat, longitude: lon } = pos.coords;
      setUserPin(lat, lon);
      buildingSelect.value = "";
      locationStatus.textContent = `GPS: ${lat.toFixed(5)}, ${lon.toFixed(5)}`;
      btnGeolocate.disabled = false;
    },
    err => {
      locationStatus.textContent = `Location error: ${err.message}`;
      btnGeolocate.disabled = false;
    },
    { enableHighAccuracy: true, timeout: 10000 }
  );
});

buildingSelect.addEventListener("change", () => {
  const code = buildingSelect.value;
  if (!code) return;
  const bldg = buildingsData.find(b => b.code === code);
  if (!bldg) return;
  setUserPin(bldg.lat, bldg.lon, "Simulated position");
  locationStatus.textContent = `Selected: ${bldg.name}`;
});

// Time defaults
function preferredDay() {
  const today = nowDayToken();
  if (availableDays.length === 0 || availableDays.includes(today)) return today;
  return availableDays[0]; // today has no classes (e.g. weekend): use the next class day
}
function resetTime() {
  daySelect.value = preferredDay();
  timeInput.value = nowTimeStr();
}
resetTime();
btnNow.addEventListener("click", resetTime);

async function loadDays() {
  try {
    const res  = await fetch("/api/days");
    const data = await res.json();
    availableDays = data.days || [];
    if (mode === "custom" && availableDays.length && !availableDays.includes(daySelect.value)) {
      daySelect.value = preferredDay();
    }
  } catch (err) {
    console.warn("Could not load days:", err);
  }
}

/* ================================================================
   Search
================================================================ */
async function doSearch(auto = false) {
  if (searching) return;
  searchError.textContent = "";
  if (!userLatLon) {
    if (!auto) searchError.textContent = "Please set your location first.";
    return;
  }

  const [lat, lon] = userLatLon;
  const live       = mode === "live";
  const day        = live ? nowDayToken() : daySelect.value;
  const now_min    = live ? nowMinOfDay() : timeStrToMin(timeInput.value);
  const include_ongoing = chkOngoing.checked;
  const query      = queryInput.value.trim();
  const { dept_filter, level_filters, type_filters } = getFilters();

  searching = true;
  btnSearch.textContent = "Searching...";
  btnSearch.disabled = true;

  try {
    const res = await fetch("/api/rank", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        lat, lon, day, now_min, include_ongoing, top_k: 10,
        dept_filter, level_filters, type_filters, query,
      }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error || "Server error");
    }
    const data = await res.json();
    lastSearchPos = [lat, lon];
    lastSearchMin = now_min;
    renderResults(data.results, data.query, data.mode, data.day_has_classes, day);
    resultsContext.textContent = contextLabel(live, day, now_min);
    // Show the results view on an explicit search or the first (live) search;
    // later live auto-refreshes update content without yanking the view.
    if (!auto || !firstSearchDone) {
      showView("results");
      resultsList.scrollTop = 0;
    }
    firstSearchDone = true;
  } catch (err) {
    searchError.textContent = err.message;
    console.error("Rank error:", err);
  } finally {
    searching = false;
    btnSearch.textContent = mode === "live" ? "Refresh Now" : "Find Nearby Classes";
    btnSearch.disabled = false;
  }
}

btnSearch.addEventListener("click", () => doSearch(false));

/* ================================================================
   Results rendering
================================================================ */
function clearResultMarkers() {
  resultMarkers.forEach(m => m && m.remove());
  resultMarkers = [];
  Object.values(buildingMarkers).forEach(m => {
    m.setStyle({ fillColor: "#0064a4", fillOpacity: 0.25, color: "#0064a4" });
    m.setRadius(7);
  });
}

function renderResults(results, activeQuery, rankMode, dayHasClasses, dayToken) {
  const keepIdx = activeCardIndex;
  clearResultMarkers();
  clearRoute();
  resultsList.innerHTML = "";
  activeCardIndex = null;
  lastResults = results;
  resultsCount.textContent = `${results.length} found`;
  resultsNote.hidden = true;
  resultsNote.textContent = "";

  if (results.length === 0) {
    if (dayHasClasses === false) {
      const name = DAY_NAMES[dayToken] || "this day";
      resultsList.innerHTML = `<li class="results-empty">No classes are scheduled on ${name}.<br>Try a weekday.</li>`;
    } else {
      resultsList.innerHTML = `<li class="results-empty">No classes found nearby, even after widening the search.<br>Try a different time or location.</li>`;
    }
    return;
  }

  if (rankMode === "widened") {
    resultsNote.hidden = false;
    resultsNote.textContent = "No classes within the next hour nearby — showing the closest upcoming classes instead.";
  }

  const showTextScore = Boolean(activeQuery);

  const typeLabels = {
    Lec: "Lecture", Dis: "Discussion", Lab: "Lab",
    Sem: "Seminar", Stu: "Studio",    Tut: "Tutorial",
    Res: "Research", Fld: "Field",    Col: "Colloquium",
  };

  results.forEach((r, idx) => {
    const li        = document.createElement("li");
    li.className    = "result-card";
    li.dataset.idx  = idx;

    const color     = scoreColor(r.score);
    const scorePct  = Math.round(r.score * 100);
    const distStr   = r.distance_m < 100
      ? `${Math.round(r.distance_m)}m`
      : `${(r.distance_m / 1000).toFixed(2)}km`;
    const minsStr   = r.minutes_until_start < 0
      ? `${Math.abs(r.minutes_until_start)}min ago`
      : r.minutes_until_start === 0 ? "Starting now" : `in ${r.minutes_until_start}min`;
    const typeLabel = r.section_type ? (typeLabels[r.section_type] || r.section_type) : "";

    // "Can I make it?" badge from walking time vs. minutes until start.
    const feas = FEAS[r.feasibility];
    const est  = r.walk_estimated ? "~" : "";
    const feasBadge = feas ? `
      <div class="feas-badge ${feas.cls}">
        &#128694; ${est}${Math.round(r.walk_min)} min walk &middot; ${feas.label(r)}
      </div>` : "";

    // Score breakdown shown when a text query is active
    const textBar = showTextScore ? `
      <div class="score-breakdown">
        <span class="score-pill" title="Time score">T ${Math.round(r.time_score*100)}%</span>
        <span class="score-pill" title="Distance score">D ${Math.round(r.dist_score*100)}%</span>
        <span class="score-pill score-pill-text" title="BM25 text relevance">Q ${Math.round(r.text_score*100)}%</span>
      </div>` : "";

    li.innerHTML = `
      <div class="card-top">
        <span class="card-course">${r.course_id}${typeLabel ? `<span class="card-type-badge">${typeLabel}</span>` : ""}</span>
        <span class="card-score" style="background:${color}">${scorePct}%</span>
      </div>
      <div class="card-dept">${r.dept}</div>
      <div class="card-title">${r.title}</div>
      <div class="card-meta">
        <span>&#128337; ${r.start_time}&#8211;${r.end_time}</span>
        <span>&#127968; ${r.building_name} ${r.room}</span>
        <span>&#128205; ${distStr}</span>
        <span>&#9201; ${minsStr}</span>
      </div>
      ${feasBadge}
      ${textBar}
      <div class="score-bar-track">
        <div class="score-bar-fill" style="width:${scorePct}%;background:${color}"></div>
      </div>`;

    li.addEventListener("click", () => highlightResult(idx, results));
    resultsList.appendChild(li);

    if (r.lat != null && r.lon != null) {
      const bMarker = buildingMarkers[r.building_code];
      if (bMarker) {
        bMarker.setStyle({ fillColor: color, fillOpacity: 0.6, color });
        bMarker.setRadius(10);
      }
      const rMarker = L.circleMarker([r.lat, r.lon], { radius: 0, opacity: 0, fillOpacity: 0 }).addTo(map);
      resultMarkers.push(rMarker);
    } else {
      resultMarkers.push(null);
    }
  });

  // In live mode, keep the selected card's route on screen across refreshes.
  if (keepIdx !== null && keepIdx < results.length) highlightResult(keepIdx, results);
}

async function drawRoute(r) {
  clearRoute();
  if (!userLatLon || !r.building_code) return;
  try {
    const res = await fetch("/api/route", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        from_lat: userLatLon[0], from_lon: userLatLon[1], to_code: r.building_code,
      }),
    });
    if (!res.ok) return; // routing unavailable: keep the simple highlight
    const data = await res.json();
    routeLine = L.polyline(data.polyline, {
      color: "#0064a4", weight: 5, opacity: 0.75, lineJoin: "round",
    }).addTo(map);
    routeLine.bindTooltip(`${data.walk_min} min walk (${Math.round(data.distance_m)} m)`, { sticky: true });
    map.fitBounds(routeLine.getBounds(), { padding: [40, 40], maxZoom: 17 });
  } catch (err) {
    console.warn("Route error:", err);
  }
}

function highlightResult(idx, results) {
  if (activeCardIndex !== null) {
    const prev = resultsList.querySelector(`[data-idx="${activeCardIndex}"]`);
    if (prev) prev.classList.remove("active");
  }
  activeCardIndex = idx;
  const card = resultsList.querySelector(`[data-idx="${idx}"]`);
  if (card) {
    card.classList.add("active");
    card.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
  const r = results[idx];
  if (r.lat != null && r.lon != null) {
    const bMarker = buildingMarkers[r.building_code];
    if (bMarker) bMarker.openTooltip();
    drawRoute(r);
  }
}

/* ================================================================
   Boot
================================================================ */
loadBuildings();
loadDepartments();
loadDays();
// Default to Google-Maps-style live tracking; falls back to custom if
// geolocation is denied or unavailable.
enterLiveMode();
