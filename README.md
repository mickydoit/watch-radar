# watch-radar

A daily research agent that watches the second-hand market for a short list of specific watches and emails a digest of what is new.

It runs as a Claude Code **scheduled cloud routine** every morning at 07:00 Brisbane. Each run clones this repo, reads `watchlist.yml`, searches Chrono24, WatchRecon, eBay, dealers, WatchCharts and the auction houses, compares against what it has already seen, commits the updated state and reports, and sends one email.

## Files

| Path | Purpose |
|---|---|
| `watchlist.yml` | **The only file you normally edit.** One entry per watch: reference, acceptable condition, full-set requirement, price ceiling, markets. |
| `ROUTINE_PROMPT.md` | The agent's instructions. The routine itself only says "follow this file", so behaviour changes are a commit here, not a routine edit. |
| `data/seen.json` | Listings already reported (90-day memory). Drives "new" and "price drop". |
| `data/prices.csv` | Append-only price history: min / median asking, WatchCharts market price, eBay sold median. |
| `data/auctions.json` | Upcoming and closed auction lots for the tracked references. |
| `reports/YYYY-MM-DD.md` | Full record of each run. The email is the summary; this is the detail. |
| `docs/specs/` | Design note. |

## Editing the watchlist

Change `watchlist.yml`, commit, push. The next run picks it up. Keep each watch's `id` stable; it is the key in the data files. To stop tracking a watch, delete its entry; its history stays in the data files.

## Managing the routine

The routine lives at https://claude.ai/code/routines. From there you can pause it, run it now, or change the schedule. To change *what it does*, edit `ROUTINE_PROMPT.md`.

## Caveats

- Chrono24 and eBay restrict automated access. The agent reads public pages for a handful of references, which generally works, but a blocked source is reported in the email's run notes rather than retried aggressively.
- Prices are asking prices as listed, converted to AUD with a rate looked up each run. Treat them as indicative.
- The agent never contacts sellers or bids.
