#!/usr/bin/env python3
"""
URC Data Scraper v3 — All Things Rugby (single-fetch, full-data edition)

One request to the competition page gets everything:
  - standings          -> urc_standings.csv    (one row per team)
  - full player stats  -> urc_players.csv      (one row per player, 16 metrics)
  - full team stats    -> urc_team_stats.csv   (one row per team, 21 metrics —
                           includes 5 stats that are only tracked at team level:
                           turnover-won, lineouts-lost, lineout-steals,
                           scrums-won, scrums-lost)

Each row is tagged with the date the script ran, so the CSVs grow over time.

Usage:
    python urc_scraper.py                  # live fetch from the web
    python urc_scraper.py --source FILE    # parse a local saved HTML file instead (for testing)
    python urc_scraper.py --force          # append even if today's date is already in the CSV
"""

import argparse
import csv
import json
import os
import re
import sys
from datetime import date

URL = "https://allthingsrugby.com/competitions/united-rugby-championship"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}

STANDINGS_CSV = "urc_standings.csv"
PLAYERS_CSV = "urc_players.csv"
TEAM_STATS_CSV = "urc_team_stats.csv"

STANDINGS_FIELDS = [
    "date_scraped", "season", "rank", "team", "played", "won", "drawn",
    "lost", "points_diff", "bonus_points", "points", "form",
]

# Metrics tracked per-player (column id -> csv column name)
PLAYER_METRICS = [
    ("points", "points"), ("try-scored", "try_scored"), ("conversion", "conversion"),
    ("penalty-goal", "penalty_goal"), ("drop-goal", "drop_goal"),
    ("carries", "carries"), ("metres-made", "metres_made"), ("clean-break", "clean_break"),
    ("defender-beaten", "defender_beaten"), ("offload", "offload"),
    ("tackle", "tackle"), ("missed-tackle", "missed_tackle"), ("turnovers-conceded", "turnovers_conceded"),
    ("penalty-conceded", "penalty_conceded"), ("yellow-card", "yellow_card"), ("red-card", "red_card"),
    ("lineout-throws-won", "lineout_throws_won"),
]
# Metrics tracked per-team (superset — includes 5 the site never breaks down by player)
TEAM_METRICS = PLAYER_METRICS + [
    ("turnover-won", "turnover_won"), ("lineouts-lost", "lineouts_lost"),
    ("lineout-steals", "lineout_steals"), ("scrums-won", "scrums_won"), ("scrums-lost", "scrums_lost"),
]

PLAYERS_FIELDS = ["date_scraped", "season", "team", "player"] + [c for _, c in PLAYER_METRICS]
TEAM_STATS_FIELDS = ["date_scraped", "season", "team"] + [c for _, c in TEAM_METRICS]


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


def rows_from_standings(pagedata: dict, run_date: str) -> list:
    rows = []
    for table in pagedata.get("standings", {}).get("tables", []):
        season = table.get("seasonName", "")
        for r in table.get("rows", []):
            rows.append({
                "date_scraped": run_date, "season": season, "rank": r.get("rank"),
                "team": r.get("team"), "played": r.get("played"), "won": r.get("won"),
                "drawn": r.get("drawn"), "lost": r.get("lost"), "points_diff": r.get("pd"),
                "bonus_points": r.get("bp"), "points": r.get("pts"),
                "form": "-".join(r.get("form", []) or []),
            })
    return rows


def rows_from_player_stats(pagedata: dict, run_date: str) -> list:
    stats_block = pagedata.get("stats", {})
    season = get_season_label(stats_block)
    table_cats = stats_block.get("players", {}).get("tableCategories", [])

    # Merge every category's rows into one dict per (player, team)
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
        out = {"date_scraped": run_date, "season": season, "team": team, "player": name}
        for json_id, col in PLAYER_METRICS:
            out[col] = values.get(json_id, "")
        rows.append(out)
    return rows


def rows_from_team_stats(pagedata: dict, run_date: str) -> list:
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
        out = {"date_scraped": run_date, "season": season, "team": team}
        for json_id, col in TEAM_METRICS:
            out[col] = values.get(json_id, "")
        rows.append(out)
    return rows


def append_csv(path: str, rows: list, fieldnames: list, run_date: str, force: bool) -> str:
    file_exists = os.path.exists(path)
    if file_exists and not force:
        with open(path, "r", newline="", encoding="utf-8") as f:
            existing = list(csv.DictReader(f))
        if any(r.get("date_scraped") == run_date for r in existing):
            return f"Skipped {path} — already has an entry for {run_date} (use --force to add anyway)"
    mode = "a" if file_exists else "w"
    with open(path, mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)
    return f"{'Appended' if file_exists else 'Created'} {path} with {len(rows)} rows for {run_date}"


def main():
    parser = argparse.ArgumentParser(description="Scrape URC standings + full player/team stats")
    parser.add_argument("--source", default=URL, help="URL to fetch, or path to a local HTML file")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--outdir", default=".")
    args = parser.parse_args()

    run_date = date.today().isoformat()
    os.makedirs(args.outdir, exist_ok=True)

    print(f"Fetching: {args.source}")
    html = get_html(args.source)
    print(f"Got {len(html):,} characters of HTML")

    pagedata = extract_pagedata(html)
    print(f"Found pageData for: {pagedata.get('league', {}).get('name', 'unknown league')}")

    standings_rows = rows_from_standings(pagedata, run_date)
    player_rows = rows_from_player_stats(pagedata, run_date)
    team_rows = rows_from_team_stats(pagedata, run_date)
    print(f"Extracted {len(standings_rows)} standings, {len(player_rows)} players, {len(team_rows)} team-stat rows")

    print()
    print(append_csv(os.path.join(args.outdir, STANDINGS_CSV), standings_rows, STANDINGS_FIELDS, run_date, args.force))
    print(append_csv(os.path.join(args.outdir, PLAYERS_CSV), player_rows, PLAYERS_FIELDS, run_date, args.force))
    print(append_csv(os.path.join(args.outdir, TEAM_STATS_CSV), team_rows, TEAM_STATS_FIELDS, run_date, args.force))


if __name__ == "__main__":
    sys.exit(main())
