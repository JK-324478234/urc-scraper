#!/usr/bin/env python3
"""
Rugby Data Scraper — All Things Rugby (multi-competition edition)

Fetches one or more competitions from All Things Rugby and appends standings,
full player stats, and full team stats into three shared CSVs, each row tagged
with which competition and date it came from. Same page structure works across
both club leagues (URC, Prem, Top 14...) and international tournaments (Nations
Championship, Nations Cup...) — verified against real saved pages from each.

Outputs (all three grow over time, one snapshot per competition per run):
  - rugby_standings.csv  : one row per team/group per competition
  - rugby_players.csv    : one row per player per competition, 16 stat columns
  - rugby_team_stats.csv : one row per team per competition, 21 stat columns
                            (includes 5 stats only tracked at team level:
                            turnover-won, lineouts-lost, lineout-steals,
                            scrums-won, scrums-lost)

Usage:
    python rugby_scraper.py                        # live fetch, all competitions in COMPETITIONS
    python rugby_scraper.py --only urc,nations-championship   # just these (see slugs in COMPETITIONS)
    python rugby_scraper.py --source-dir DIR        # read local saved HTML files instead (for testing)
    python rugby_scraper.py --force                 # append even if today's date is already recorded
"""

import argparse
import csv
import json
import os
import re
import sys
from datetime import date

# Each entry: short key (for --only and local filenames), display name, and the
# competition's slug on All Things Rugby (goes into the URL).
COMPETITIONS = [
    {"key": "urc", "name": "United Rugby Championship", "slug": "united-rugby-championship"},
    {"key": "nations-championship", "name": "Nations Championship", "slug": "world-rugby-nations-championship"},
    {"key": "nations-cup", "name": "World Rugby Nations Cup", "slug": "world-rugby-nations-cup"},
]

BASE_URL = "https://allthingsrugby.com/competitions/{slug}"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}

STANDINGS_CSV = "rugby_standings.csv"
PLAYERS_CSV = "rugby_players.csv"
TEAM_STATS_CSV = "rugby_team_stats.csv"

STANDINGS_FIELDS = [
    "competition", "date_scraped", "season", "group", "rank", "team", "played", "won", "drawn",
    "lost", "points_diff", "bonus_points", "points", "form",
]

PLAYER_METRICS = [
    ("points", "points"), ("try-scored", "try_scored"), ("conversion", "conversion"),
    ("penalty-goal", "penalty_goal"), ("drop-goal", "drop_goal"),
    ("carries", "carries"), ("metres-made", "metres_made"), ("clean-break", "clean_break"),
    ("defender-beaten", "defender_beaten"), ("offload", "offload"),
    ("tackle", "tackle"), ("missed-tackle", "missed_tackle"), ("turnovers-conceded", "turnovers_conceded"),
    ("penalty-conceded", "penalty_conceded"), ("yellow-card", "yellow_card"), ("red-card", "red_card"),
    ("lineout-throws-won", "lineout_throws_won"),
]
TEAM_METRICS = PLAYER_METRICS + [
    ("turnover-won", "turnover_won"), ("lineouts-lost", "lineouts_lost"),
    ("lineout-steals", "lineout_steals"), ("scrums-won", "scrums_won"), ("scrums-lost", "scrums_lost"),
]

PLAYERS_FIELDS = ["competition", "date_scraped", "season", "team", "player"] + [c for _, c in PLAYER_METRICS]
TEAM_STATS_FIELDS = ["competition", "date_scraped", "season", "team"] + [c for _, c in TEAM_METRICS]


def get_html(source: str) -> str:
    if source.startswith("http"):
        import urllib.request
        req = urllib.request.Request(source, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    else:
        with open(source, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()


def _find_matching_brace(s: str, start_idx: int) -> int:
    depth, in_string, escape = 0, False, False
    for i in range(start_idx, len(s)):
        c = s[i]
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def extract_pagedata(html: str) -> dict:
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)(?=</script>)', html, re.DOTALL)
    if not chunks:
        raise RuntimeError("No embedded data found — page may be an empty JS shell.")
    target = None
    for chunk in chunks:
        if '\\"pageData\\"' in chunk or '"pageData":{' in chunk:
            target = chunk
            break
    if target is None:
        target = max(chunks, key=len)
    unescaped = json.loads('"' + target + '"')
    marker = '"pageData":{'
    start = unescaped.find(marker)
    if start == -1:
        raise RuntimeError("Could not locate 'pageData' in the decoded chunk.")
    start_json = start + len('"pageData":')
    end_idx = _find_matching_brace(unescaped, start_json)
    if end_idx == -1:
        raise RuntimeError("Could not find the end of the pageData JSON object.")
    return json.loads(unescaped[start_json:end_idx + 1])


def get_season_label(stats_block: dict) -> str:
    season = stats_block.get("currentSeasonId", "")
    if season and "/" not in str(season):
        for s in stats_block.get("seasons", []):
            if s.get("id") == season:
                return s.get("label", season)
    return season


def rows_from_standings(pagedata: dict, competition: str, run_date: str) -> list:
    rows = []
    for table in pagedata.get("standings", {}).get("tables", []):
        season = table.get("seasonName", "")
        group = table.get("title", "")
        if group == competition:  # single-table competitions just repeat the comp name — not a real grouping
            group = ""
        for r in table.get("rows", []):
            rows.append({
                "competition": competition, "date_scraped": run_date, "season": season,
                "group": group, "rank": r.get("rank"), "team": r.get("team"),
                "played": r.get("played"), "won": r.get("won"), "drawn": r.get("drawn"),
                "lost": r.get("lost"), "points_diff": r.get("pd"), "bonus_points": r.get("bp"),
                "points": r.get("pts"), "form": "-".join(r.get("form", []) or []),
            })
    return rows


def rows_from_player_stats(pagedata: dict, competition: str, run_date: str) -> list:
    stats_block = pagedata.get("stats", {})
    season = get_season_label(stats_block)
    table_cats = stats_block.get("players", {}).get("tableCategories", [])

    merged = {}
    for cat in table_cats:
        for row in cat.get("rows", []):
            name = row.get("player")
            if not name:
                continue
            key = (name, row.get("team", ""))
            merged.setdefault(key, {}).update(row.get("values", {}))

    rows = []
    for (name, team), values in sorted(merged.items()):
        out = {"competition": competition, "date_scraped": run_date, "season": season,
               "team": team, "player": name}
        for json_id, col in PLAYER_METRICS:
            out[col] = values.get(json_id, "")
        rows.append(out)
    return rows


def rows_from_team_stats(pagedata: dict, competition: str, run_date: str) -> list:
    stats_block = pagedata.get("stats", {})
    season = get_season_label(stats_block)
    table_cats = stats_block.get("team", {}).get("tableCategories", [])

    merged = {}
    for cat in table_cats:
        for row in cat.get("rows", []):
            team = row.get("team")
            if not team:
                continue
            merged.setdefault(team, {}).update(row.get("values", {}))

    rows = []
    for team, values in sorted(merged.items()):
        out = {"competition": competition, "date_scraped": run_date, "season": season, "team": team}
        for json_id, col in TEAM_METRICS:
            out[col] = values.get(json_id, "")
        rows.append(out)
    return rows


def append_csv(path: str, rows: list, fieldnames: list, run_date: str, competition_filter: str, force: bool) -> str:
    file_exists = os.path.exists(path)
    if file_exists and not force:
        with open(path, "r", newline="", encoding="utf-8") as f:
            existing = list(csv.DictReader(f))
        if any(r.get("date_scraped") == run_date and r.get("competition") == competition_filter for r in existing):
            return f"Skipped {path} [{competition_filter}] — already has an entry for {run_date} (use --force to add anyway)"
    mode = "a" if file_exists else "w"
    with open(path, mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)
    return f"{'Appended' if file_exists else 'Created'} {path} with {len(rows)} rows for {competition_filter} ({run_date})"


def main():
    parser = argparse.ArgumentParser(description="Scrape standings + full player/team stats across rugby competitions")
    parser.add_argument("--only", default=None, help="Comma-separated competition keys to run (default: all in COMPETITIONS)")
    parser.add_argument("--source-dir", default=None,
                         help="Directory of locally saved HTML files (for testing), named '<key>.html'. "
                              "If omitted, fetches live from the web.")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--outdir", default=".")
    args = parser.parse_args()

    run_date = date.today().isoformat()
    os.makedirs(args.outdir, exist_ok=True)

    wanted_keys = set(args.only.split(",")) if args.only else None
    competitions = [c for c in COMPETITIONS if not wanted_keys or c["key"] in wanted_keys]

    for comp in competitions:
        print(f"=== {comp['name']} ===")
        source = os.path.join(args.source_dir, f"{comp['key']}.html") if args.source_dir else BASE_URL.format(slug=comp["slug"])

        if args.source_dir and not os.path.exists(source):
            print(f"  [skip] no local file at {source}")
            continue

        try:
            html = get_html(source)
            pagedata = extract_pagedata(html)
        except Exception as e:
            print(f"  [error] {e}")
            continue

        standings_rows = rows_from_standings(pagedata, comp["name"], run_date)
        player_rows = rows_from_player_stats(pagedata, comp["name"], run_date)
        team_rows = rows_from_team_stats(pagedata, comp["name"], run_date)
        print(f"  {len(standings_rows)} standings, {len(player_rows)} players, {len(team_rows)} team-stat rows")

        print("  " + append_csv(os.path.join(args.outdir, STANDINGS_CSV), standings_rows, STANDINGS_FIELDS, run_date, comp["name"], args.force))
        print("  " + append_csv(os.path.join(args.outdir, PLAYERS_CSV), player_rows, PLAYERS_FIELDS, run_date, comp["name"], args.force))
        print("  " + append_csv(os.path.join(args.outdir, TEAM_STATS_CSV), team_rows, TEAM_STATS_FIELDS, run_date, comp["name"], args.force))
        print()


if __name__ == "__main__":
    sys.exit(main())
