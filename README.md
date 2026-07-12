# Rugby Data Auto-Scraper

Runs weekly, pulls standings, full player stats, and full team stats from All Things
Rugby across multiple competitions, and appends everything into three shared CSVs —
one unified database, not one file per competition.

## Files

- `rugby_scraper.py` — the scraper (pure Python, no dependencies to install)
- `.github/workflows/scrape.yml` — runs it every Monday automatically
- `rugby_standings.csv` — one row per team (or per team per group, for competitions
  split into conferences/pools), tagged with which `competition` it's from
- `rugby_players.csv` — one row per player per competition, 16 stat columns
- `rugby_team_stats.csv` — one row per team per competition, 21 stat columns —
  includes 5 stats only tracked at team level: turnover-won, lineouts-lost,
  lineout-steals, scrums-won, scrums-lost

Every row across all three files has a `competition` column, so you can filter to
one tournament or pivot across all of them in the same table.

## Competitions currently included

- United Rugby Championship
- Nations Championship
- World Rugby Nations Cup

More can be added — see below.

## How it works

Every competition page on All Things Rugby uses the same underlying structure:
standings (one or more tables — a single league table, or several for conferences/
pools/groups), a full player stats table (not capped at a leaderboard), and a full
team stats table. One fetch per competition gets everything for that competition.
Verified against real saved pages from all three competitions above before shipping.

## Setup (5–10 minutes, one time)

1. **Create a new repo on GitHub** (github.com → New repository). Public or private
   both work fine — private just needs a free GitHub account, no paid plan required.

2. **Add the files**, keeping the folder structure exactly as-is:
   ```
   your-repo/
     rugby_scraper.py
     .github/
       workflows/
         scrape.yml
   ```
   Easiest way: on the repo's GitHub page, use "Add file → Upload files" and drag
   both in (GitHub recreates the `.github/workflows/` folder automatically from the
   path).

3. **Commit.**

4. **Test it once manually:** **Actions** tab → "Scrape Rugby Data" → **Run workflow**
   button → Run workflow. Takes a few seconds. Refresh and check the three CSVs
   appeared, each with rows from all three competitions.

That's it — from here it runs on its own every Monday at 7am Dublin time.

## Updating from an earlier (URC-only) version

If you've already got the single-competition version running:

1. Replace `rugby_scraper.py` and `.github/workflows/scrape.yml` with these versions
   (note the script is renamed from `urc_scraper.py`).
2. Delete the old `urc_standings.csv`, `urc_players.csv`, and `urc_team_stats.csv` —
   they don't have a `competition` column, so they can't just be renamed into the
   new files. Since there's only a few days of history in them, starting fresh is
   the simplest option; let me know if you'd rather I write a one-time script to
   migrate that history across instead.
3. Commit, then test via **Actions** → "Scrape Rugby Data" → **Run workflow**.

## Adding more competitions

Each competition is one entry in the `COMPETITIONS` list near the top of
`rugby_scraper.py`:

```python
COMPETITIONS = [
    {"key": "urc", "name": "United Rugby Championship", "slug": "united-rugby-championship"},
    {"key": "nations-championship", "name": "Nations Championship", "slug": "world-rugby-nations-championship"},
    {"key": "nations-cup", "name": "World Rugby Nations Cup", "slug": "world-rugby-nations-cup"},
]
```

`slug` is the part of the URL after `allthingsrugby.com/competitions/`. In
principle, adding a new competition is just adding a new entry here — but each one
should be verified against a real saved page first (structure has held consistent
across all three tested so far, but it's worth confirming rather than assuming,
especially for knockout-style competitions like the Champions Cup and Challenge Cup,
which likely don't have a simple standings table the same way).

## Adjusting the schedule

Edit the `cron` line in `.github/workflows/scrape.yml`. Format is
`minute hour day month weekday` (weekday: 1 = Monday). For example, `'0 18 * * 5'`
would run Fridays at 6pm instead.

## Things worth knowing

- **Timing isn't exact.** GitHub runs scheduled workflows on shared infrastructure,
  so a run can fire 5–30 minutes late (occasionally more) during busy periods.
- **Off-season/quiet weeks still get logged.** If a competition's data hasn't
  changed since the last run, the workflow still records a snapshot — harmless,
  just means a few repeated rows until that competition's next round.
- **The `last_checked.txt` file** isn't data — it guarantees a commit every week so
  GitHub doesn't auto-disable the schedule after 60 days of inactivity during a
  quiet stretch.
- **If a run ever fails**, the Actions tab will show a red ✕ with logs. Most likely
  cause is a competition's page structure changing, or a genuinely different page
  shape (e.g. a knockout bracket) that the current parsing doesn't expect — ping me
  with the error and which competition, and I'll fix it.
