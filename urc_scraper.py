#!/usr/bin/env python3
"""
URC Data Scraper — All Things Rugby

Fetches https://allthingsrugby.com/competitions/united-rugby-championship,
pulls out the embedded standings + player stat leaderboards, and appends
them to two running CSV files (urc_standings.csv, urc_stats.csv) tagged
with the date the script ran.

Run it once per round (manually, or on a schedule — see the accompanying
setup notes) and your CSVs grow round by round automatically.

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
    # A normal browser user-agent avoids the request being treated as a bot
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}

STANDINGS_CSV = "urc_standings.csv"
STATS_CSV = "urc_stats.csv"

STANDINGS_FIELDS = [
    "date_scraped", "season", "rank", "team", "played", "won", "drawn",
    "lost", "points_diff", "bonus_points", "points", "form",
]
STATS_FIELDS = [
    "date_scraped", "season", "section", "stat_category", "rank",
    "player", "team", "value",
]


def get_html(source: str) -> str:
    """Fetch live from the web, or read a local file if --source looks like a path."""
    if source.startswith("http"):
        import urllib.request
        req = urllib.request.Request(source, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    else:
        with open(source, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()


def _find_matching_brace(s: str, start_idx: int) -> int:
    """Given s[start_idx] == '{', return the index of its matching '}'."""
    depth = 0
    in_string = False
    escape = False
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
    """
    All Things Rugby (Next.js) streams its page data into the HTML inside
    script tags like:  self.__next_f.push([1,"...escaped json..."])
    The largest such chunk holds the full pageData object (league, news,
    teams, standings, fixtures, stats) regardless of which tab is shown.
    """
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)(?=</script>)', html, re.DOTALL)
    if not chunks:
        raise RuntimeError(
            "No embedded data found in the page. The site may have changed "
            "its structure, or this response is an empty JS shell rather than "
            "the fully rendered page."
        )

    # The chunk containing pageData is the one we want — find it directly
    # rather than assuming it's the largest, in case that changes.
    target = None
    for chunk in chunks:
        if '\\"pageData\\"' in chunk or '"pageData":{' in chunk:
            target = chunk
            break
    if target is None:
        target = max(chunks, key=len)  # fallback: biggest chunk

    unescaped = json.loads('"' + target + '"')

    marker = '"pageData":{'
    start = unescaped.find(marker)
    if start == -1:
        raise RuntimeError("Could not locate 'pageData' in the decoded chunk.")
    start_json = start + len('"pageData":')
    end_idx = _find_matching_brace(unescaped, start_json)
    if end_idx == -1:
        raise RuntimeError("Could not find the end of the pageData JSON object.")

    payload_str = unescaped[start_json:end_idx + 1]
    return json.loads(payload_str)


def rows_from_standings(pagedata: dict, run_date: str) -> list:
    rows = []
    standings = pagedata.get("standings", {})
    for table in standings.get("tables", []):
        season = table.get("seasonName", "")
        for r in table.get("rows", []):
            rows.append({
                "date_scraped": run_date,
                "season": season,
                "rank": r.get("rank"),
                "team": r.get("team"),
                "played": r.get("played"),
                "won": r.get("won"),
                "drawn": r.get("drawn"),
                "lost": r.get("lost"),
                "points_diff": r.get("pd"),
                "bonus_points": r.get("bp"),
                "points": r.get("pts"),
                "form": "-".join(r.get("form", []) or []),
            })
    return rows


def rows_from_stats(pagedata: dict, run_date: str) -> list:
    rows = []
    stats_block = pagedata.get("stats", {})
    stats = stats_block.get("players", {})
    current_id = stats_block.get("currentSeasonId", "")
    season = next(
        (s.get("label") for s in stats_block.get("seasons", []) if s.get("id") == current_id),
        current_id,
    )
    for section in stats.get("sections", []):
        section_title = section.get("title", "")
        for card in section.get("cards", []):
            category = card.get("label", "")
            for e in card.get("entries", []):
                rows.append({
                    "date_scraped": run_date,
                    "season": season,
                    "section": section_title,
                    "stat_category": category,
                    "rank": e.get("rank"),
                    "player": e.get("name"),
                    "team": e.get("team"),
                    "value": e.get("value"),
                })
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
    parser = argparse.ArgumentParser(description="Scrape URC standings + stats and append to CSV")
    parser.add_argument("--source", default=URL, help="URL to fetch, or path to a local HTML file")
    parser.add_argument("--force", action="store_true", help="Append even if today's date already has an entry")
    parser.add_argument("--outdir", default=".", help="Directory to write/append the CSV files in")
    args = parser.parse_args()

    run_date = date.today().isoformat()

    print(f"Fetching from: {args.source}")
    html = get_html(args.source)
    print(f"Got {len(html):,} characters of HTML")

    pagedata = extract_pagedata(html)
    print(f"Found pageData for: {pagedata.get('league', {}).get('name', 'unknown league')}")

    standings_rows = rows_from_standings(pagedata, run_date)
    stats_rows = rows_from_stats(pagedata, run_date)

    print(f"Extracted {len(standings_rows)} standings rows, {len(stats_rows)} stat leaderboard rows")

    os.makedirs(args.outdir, exist_ok=True)
    print(append_csv(os.path.join(args.outdir, STANDINGS_CSV), standings_rows, STANDINGS_FIELDS, run_date, args.force))
    print(append_csv(os.path.join(args.outdir, STATS_CSV), stats_rows, STATS_FIELDS, run_date, args.force))


if __name__ == "__main__":
    sys.exit(main())
