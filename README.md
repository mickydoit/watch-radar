# watch-radar

A research agent, run on request, that scans the market for the **watch brands and price bands you choose**, works out what each model it finds is really asking across marketplaces, dealers and grey-market sites, and shows the listings priced **below that market** on a small web app.

**Site:** https://mickydoit.github.io/watch-radar/ (GitHub Pages, served from this repo's `main`).

It runs as a Claude Code **cloud routine with no schedule**: the owner starts it by hand (Run now at claude.ai/code/routines) whenever a fresh scan is wanted, with photos and auction lots fetched on the same run. Each run clones this repo, reads `data/watchlist.json`, gathers every listing it can find for each reference, computes a median benchmark (like-for-like on condition, smoothed over 30 days), flags listings under it, records price history and auction lots, writes `data/latest.json`, commits and pushes. Pages redeploys on the push. Nothing is emailed and no mail account is attached.

## Files

| Path | Purpose |
|---|---|
| `data/focus.json` | **The main control.** Which brands (from a fixed list of 22) and which AUD price bands the agent researches. Set from the site's Focus section. |
| `data/watchlist.json` | Optional specific references to track exactly, in addition to the brand focus. Edited from the site or by hand. |
| `ROUTINE_PROMPT.md` | The agent's instructions. The routine itself only says "follow this file", so behaviour changes are a commit here, not a routine edit. |
| `index.html` | The web app. Static, no build step; reads the `data/` files directly. |
| `data/latest.json` | What the site shows: today's benchmark per watch, ranked below-market deals with flags, price drops, auction changes, run notes. |
| `data/runs.json` | One line per run for the Runs section. |
| `data/images.json`, `images/` | One freely licensed photo per watch with its credit. The owner can set an image URL on a watchlist entry instead; the routine looks on Wikimedia Commons for watches that have neither. |
| `data/seen.json` | Every listing seen in the last 90 days, with match flag and below-market %. Drives "new" and "price drop". |
| `data/prices.csv` | Append-only price history: min / median asking, WatchCharts market price, eBay sold median. |
| `data/auctions.json` | Upcoming and closed auction lots for the tracked references. |
| `reports/YYYY-MM-DD.md` | Full record of each run. The email is the summary; this is the detail. |
| `docs/specs/` | Design note. |

## Choosing what gets researched

Open the site's **Focus** section, tick the brands and the price bands you care about, and press Save, then enter the Watch Radar password. Settings live in a small Supabase table (`supabase/watch_radar.sql`); the password is checked by the database, writes go through a server-side function, and the routine reads the same table each run and mirrors it into `data/focus.json` and `data/watchlist.json`. If `data/backend.json` has no database URL, the site falls back to saving straight to GitHub with a fine-grained token. The next run researches those brands inside those bands, picks up to five models per brand with the most stock, benchmarks each, and lists what sits under market. Specific references can be added underneath if you want a particular watch tracked regardless of band.

## Editing the reference list

Open the site's **Watchlist** section. You can switch whole brands on or off, pause or resume a reference, edit its criteria, add a new one, or remove one. Saving writes `data/watchlist.json` back to this repo through the GitHub API using a fine-grained personal access token that you create once (repository: this one; permission: Contents, read and write). The token is kept only in your browser's local storage and is sent only to api.github.com. The next run uses the new list. Editing the JSON by hand and pushing works too. Keep each `id` stable; it keys the data files.

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
