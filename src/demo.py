from __future__ import annotations

from .io import load_buildings_csv, load_meetings_csv
from .ranker import RankConfig, rank_meetings, fmt_time


def print_results_table(
    results,
    cfg,
    title: str,
    prompts: dict,
) -> None:
    """
    Helper to print a pretty results table with a title and prompts.
    """
    print("\n" + "=" * 130)
    print(f"SCENARIO: {title}")
    print("-" * 130)
    print("Prompts:")
    for key, value in prompts.items():
        print(f"  {key}: {value}")
    print("=" * 130)
    print(f"{'RANK':<4} {'COURSE':<14} {'TYPE':<6} {'DAYS':<6} {'TIME':<13} {'LOC':<10} "
          f"{'MIN UNTIL':>9} {'DIST(m)':>9} {'SCORE':>7}  {'t':>5} {'d':>5}")
    print("-" * 130)

    for i, r in enumerate(results, start=1):
        m = r.meeting
        section_type = ""  # placeholder for now
        time_str = f"{fmt_time(m.start_min)}-{fmt_time(m.end_min)}"
        loc_str = f"{m.building_code} {m.room}".strip()

        print(f"{i:<4} {m.course_id:<14} {section_type:<6} {m.days:<6} {time_str:<13} {loc_str:<10} "
              f"{r.minutes_until_start:>9d} {r.distance_m:>9.0f} {r.score:>7.3f}  {r.time_score:>5.3f} {r.dist_score:>5.3f}")

    print("=" * 130)

    # Explainability: show WHY the top few were ranked that way
    explain_top_n = min(3, len(results))
    if explain_top_n > 0:
        print("\nExplainability (top results):")
        for i in range(explain_top_n):
            r = results[i]
            m = r.meeting
            print(f"\n#{i+1}: {m.course_id} - {m.title}")
            print(f"  When: {m.days} {fmt_time(m.start_min)}-{fmt_time(m.end_min)}")
            print(f"  Where: {m.building_code} {m.room}")
            print(f"  Minutes until start: {r.minutes_until_start}  -> time_score={r.time_score:.3f}")
            print(f"  Distance (m): {r.distance_m:.0f}           -> dist_score={r.dist_score:.3f}")
            print(f"  Final score: {r.score:.3f} = "
                  f"{cfg.w_time:.2f}*{r.time_score:.3f} + {cfg.w_dist:.2f}*{r.dist_score:.3f}")


def main() -> None:
    buildings = load_buildings_csv("data/buildings.csv")
    meetings = load_meetings_csv("data/meetings.csv")

    cfg = RankConfig()

    # Test Case 1: Include ongoing classes
    user_latlon_1 = (33.6430, -117.8419)  # near DBH
    day_token_1 = "W"
    now_min_1 = 13 * 60 + 10  # 1:10 PM

    prompts_1 = {
        "user_location": "near DBH (33.6430, -117.8419)",
        "day": day_token_1,
        "current_time": fmt_time(now_min_1),
        "include_ongoing": True,
        "time_window": f"{cfg.time_window_min} min",
        "max_distance": f"{cfg.max_distance_m} m",
    }

    results_1 = rank_meetings(
        meetings=meetings,
        buildings=buildings,
        user_latlon=user_latlon_1,
        day_token=day_token_1,
        now_min=now_min_1,
        cfg=cfg,
        top_k=10,
        include_ongoing=True,
    )

    print_results_table(results_1, cfg, "Including Ongoing Classes", prompts_1)

    # Test Case 2: Exclude ongoing classes, different day/time/location
    user_latlon_2 = (33.6410, -117.8290)  # different location (near Engineering Hall)
    day_token_2 = "M"
    now_min_2 = 9 * 60 + 0  # 9:00 AM

    prompts_2 = {
        "user_location": "near Engineering Hall (33.6410, -117.8290)",
        "day": day_token_2,
        "current_time": fmt_time(now_min_2),
        "include_ongoing": False,
        "time_window": f"{cfg.time_window_min} min",
        "max_distance": f"{cfg.max_distance_m} m",
    }

    results_2 = rank_meetings(
        meetings=meetings,
        buildings=buildings,
        user_latlon=user_latlon_2,
        day_token=day_token_2,
        now_min=now_min_2,
        cfg=cfg,
        top_k=10,
        include_ongoing=False,
    )

    print_results_table(results_2, cfg, "Excluding Ongoing Classes", prompts_2)


if __name__ == "__main__":
    main()

