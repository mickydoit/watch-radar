# watch-radar

A daily research agent that scans the market for a short list of specific watches, works out what each one is really asking across marketplaces, dealers and grey-market sites, and shows the listings priced **below that market** on a small web app.

**Site:** https://mickydoit.github.io/watch-radar/ (GitHub Pages, served from this repo's `main`).

It runs as a Claude Code **scheduled cloud routine** every morning at 07:00 Brisbane. Each run clones this repo, reads `watchlist.yml`, gathers every listing it can find for each reference, computes a median benchmark (like-for-like on condition, smoothed over 30 days), flags listings under it, records price history and auction lots, writes `data/latest.json`, commits and pushes. Pages redeploys on the push. Nothing is emailed and no mail account is attached.

## Files

| Path | Purpose |
|---|---|
| `watchlist.yml` | **The only file you normally edit.** One entry per watch: reference, acceptable condition, full-set requirement, price ceiling, markets. |
| `ROUTINE_PROMPT.md` | The agent's instructions. The routine itself only says "follow this file", so behaviour changes are a commit here, not a routine edit. |
| `index.html` | The web app. Static, no build step; reads the `data/` files directly. |
| `data/latest.json` | What the site shows: today's benchmark per watch, ranked below-market deals with flags, price drops, auction changes, run notes. |
| `data/runs.json` | One line per run for the Runs tab. |
| `data/seen.json` | Every listing seen in the last 90 days, with match flag and below-market %. Drives "new" and "price drop". |
| `data/prices.csv` | Append-only price history: min / median asking, WatchCharts market price, eBay sold median. |
| `data/auctions.json` | Upcoming and closed auction lots for the tracked references. |
| `reports/YYYY-MM-DD.md` | Full record of each run. The email is the summary; this is the detail. |
| `docs/specs/` | Design note. |

## Editing the watchlist

Change `watchlist.yml`, commit, push. The next run picks it up. Keep each watch's `id` stable; it is the key in the data files. To stop tracking a watch, delete its entry; its history stays in the data files.

## How "below market" works

For each watch the agent collects every priced, non-replica listing it can read for the reference, converts to AUD, and takes the **median** asking price of listings that meet your condition and full-set criteria. The median over the last 30 days of runs is the benchmark, so one odd day does not move it. Any qualifying listing at least 3% under the benchmark is a deal, ranked by discount, and flagged **verify** (25%+ under, private seller, or missing papers), **grey new** (new from a grey-market dealer) or **clean**. The figure is an asking-price benchmark; only the eBay sold median is transaction data.

## Managing the routine

The routine lives at https://claude.ai/code/routines. From there you can pause it, run it now, or change the schedule. To change *what it does*, edit `ROUTINE_PROMPT.md`.

## Caveats

- Chrono24 and eBay restrict automated access. The agent reads public pages for a handful of references, which generally works, but a blocked source is reported in the email's run notes rather than retried aggressively.
- Prices are asking prices as listed, converted to AUD with a rate looked up each run. Treat them as indicative.
- Cheap usually means something: the agent flags, it does not authenticate. Check the seller, photos and papers yourself.
- The agent never contacts sellers or bids.
- GitHub Pages on a free account requires the repo to be public, so the watchlist and reports are visible to anyone with the link.
