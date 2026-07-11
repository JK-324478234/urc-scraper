# URC Data Auto-Scraper

Runs weekly, pulls the latest United Rugby Championship standings + stat leaderboards
from All Things Rugby, and appends them to `urc_standings.csv` and `urc_stats.csv` —
no manual copying needed.

## Files

- `urc_scraper.py` — the scraper itself (pure Python, no dependencies to install)
- `.github/workflows/scrape.yml` — tells GitHub to run it every Monday automatically
- `urc_standings.csv`, `urc_stats.csv` — created on first run (or bring your own — see below)

## Setup (5–10 minutes, one time)

1. **Create a new repo on GitHub** (github.com → New repository). Public or private both work
   fine — private just needs a free GitHub account, no paid plan required for this.

2. **Add the files**, keeping the folder structure exactly as-is:
   ```
   your-repo/
     urc_scraper.py
     .github/
       workflows/
         scrape.yml
   ```
   Easiest way: on the repo's GitHub page, use "Add file → Upload files" and drag both in
   (GitHub will recreate the `.github/workflows/` folder automatically from the path).

3. **(Optional) Keep your existing data.** If you want the automated data to continue on
   from what you've already collected, add your current CSVs to the repo root as
   `urc_standings.csv` and `urc_stats.csv`, with these exact column headers:

   - `urc_standings.csv`: `date_scraped, season, rank, team, played, won, drawn, lost, points_diff, bonus_points, points, form`
   - `urc_stats.csv`: `date_scraped, season, section, stat_category, rank, player, team, value`

   If your existing file uses different column names, either rename the headers to match, or
   just skip this step — the first automated run will create fresh files from scratch.

4. **Commit.**

5. **Test it once manually:** go to the **Actions** tab → "Scrape URC Data" → **Run workflow**
   button → Run workflow. It takes about 15 seconds. Refresh and check the CSVs updated.

That's it — from here it runs on its own every Monday at 7am Dublin time.

## Adjusting the schedule

Edit the `cron` line in `.github/workflows/scrape.yml`. Format is `minute hour day month weekday`
(weekday: 1 = Monday). For example, `'0 18 * * 5'` would run Fridays at 6pm instead.

## Things worth knowing

- **Timing isn't exact.** GitHub runs scheduled workflows on shared infrastructure, so a run can
  fire 5–30 minutes late (occasionally more) during busy periods. Fine for this use case, just
  don't expect second-by-second precision.
- **Off-season weeks still get logged.** Once the season finishes, the standings/stats won't
  change, but the workflow still runs and records a snapshot each week — harmless, just means
  a few repeated rows until the next season's fixtures start.
- **The `last_checked.txt` file** isn't really data — it's there to guarantee a commit every
  week. GitHub auto-disables scheduled workflows after 60 days with *zero* commits to the repo,
  which would otherwise silently trip during the close season. This file exists purely to stop
  that from happening.
- **If a run ever fails**, the Actions tab will show a red ✕ with logs. Most likely cause would
  be the site changing its page structure — ping me with the error and I'll fix the parsing.
