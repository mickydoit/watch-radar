# watch-radar: hourly full-depth research, condensed into one list

> **Status 4 Nov 2026, evening:** built and run once hourly, then the owner reverted the cadence to **once a day at 07:00 Brisbane** on usage grounds. The registry, feed sweep, coverage reporting, New chips and the condensed deal pool stay; only the schedule changed.

Date: 4 November 2026. Decided by the owner in chat; the "how" is Claude's call unless marked otherwise.

## Intent

The owner wants the research agents to search as many sellers, retail shops and verified resellers as possible, not a light pass, and to do it **every hour**, so that the ranked list on the site is the best possible list at the start of every day. The owner chose full-depth research every hour over a cheaper hourly sweep, knowing it costs roughly 24 times the single daily run.

## What exists (4 Nov)

One cloud routine (`trig_01C141RVeHnA1zNdtEgnYNrP`, Opus 5.5) fires at 07:00 Brisbane, follows `ROUTINE_PROMPT.md`, and pushes `data/latest.json` for the GitHub Pages site. Today's run: 23 minutes, 108 searches, 707 fetch attempts, 17 brands, 74 models, 131 deals, 1,129 listings remembered from about 40 sources. Depth is uneven: the prompt sets only a floor (6 searches, 10 fetches, 4 domains per brand), names four shops, and nothing records which sellers were reached.

## Goals

1. **Breadth that is listed and measured.** Every seller the agent should visit lives in a registry file, with its fetch recipe. Each run reports how many registry sources it reached, which were blocked, and how many listings each gave. The site shows that coverage line.
2. **Hourly full-depth runs.** The same research every hour, Opus, within a hard time budget so runs never overlap.
3. **One condensed list.** The Today list is computed over everything still for sale in memory (not only what this hour's searches surfaced), ranked by discount against the benchmark, within the owner's brands, bands and styles. New finds are marked so the owner sees what the night brought.

## Non-goals

- No new ways around sites that block the fetcher (Chrono24, eBay, WatchCharts, Catawiki, WatchPatrol, Watchfinder stay snippet-only).
- No change to the Focus model, bands, styles, password flow or Supabase schema.
- No email, no notifications.

## Anti-goals

- Hourly runs that collide on `main` and corrupt the data files.
- Photo and auction work repeated 24 times a day (Openverse allows 200 calls a day; Wikimedia throttles).
- A prompt that is longer but no more specific.

## Design

### 1. Source registry: `data/sources.json`

One entry per seller: `id`, `name`, `domain`, `country`, `currency`, `tier` (`authorised`, `grey`, `preowned`, `aggregator`, `microbrand`, `auction`), `recipe` (`shopify`, `woocommerce`, `html`, `snippet`), recipe details (`feed` URL template, `price_multiplier` for Define's ex-GST cents, `search` URL template for html sources), `brands` (known carried brands, or `"auto"` when the feed's vendor field decides), and a status block the routine maintains: `last_ok`, `last_status` (`ok` | `blocked` | `empty` | `error`), `last_listings`. Blocked-by-design sources carry `recipe: "snippet"` so the agent knows to use search snippets only.

Registry seeded from the 4 Nov probe: every domain that answered a Shopify `products.json` or WooCommerce Store API request, plus the html sources that worked in past runs (WatchRecon, Wristler, Everywatch, Bezel, Bob's, The 1916 Company, Crown & Caliber, Subdial, Tropical, European Watch Co, Jomashop, Prestige Time, Authentic Watches, Creation Watches, Chronext, Watchdeal, Goldsmiths, Beaverbrooks, Ernest Jones, Watches of Switzerland AU, The Hour Glass, Grays, Vintage Watch Co) and the snippet-only ones.

### 2. Feed sweep script: `tools/sweep.py`

Standard-library Python 3 (the cloud has Python). Reads `data/focus.json` (brands, bands), `data/sources.json`, FX rates (`--rates` JSON or fetched from frankfurter.app), and pulls every `shopify` and `woocommerce` source **to the last page**, in parallel across hosts, serial within a host, 0.4 s between pages, 20 s timeout per request, 40 pages max. It keeps every product whose vendor or title matches a selected brand (aliases included), emits one listing per variant with its own URL and image, converts to AUD, marks `in_band`, and writes `data/sweep.json`: `{ran_at, rates, listings[], coverage{source_id: {status, products, listings, pages, error}}}`. Never crashes on one source; errors land in coverage. Also updates the status block in `data/sources.json`.

Listing shape matches `seen.json` listings: `key`, `source`, `source_id`, `url`, `title`, `variant`, `price`, `currency`, `price_aud`, `in_band`, `condition` ("new" for authorised and grey tiers, "unknown" otherwise), `seller_type` (tier), `seller_country`, `source_quality: "page"`, `image_url`, `available`, `compare_at_price`.

The agent runs the script first every hour, then spends its own effort on html and snippet sources, model grouping, benchmarks and deals.

### 3. Run modes in `ROUTINE_PROMPT.md`

Every run is a full research run. The **07:00 Brisbane** run (UTC hour 21) is additionally the `daily` run: photos (§1F), auctions (§1D), the day's report rewrite, and on Mondays the weekly refresh. Every other hour is an `hourly` run: no photo phase, no auction search; everything else identical.

Hard budget: a run must push within **50 minutes** of starting. At 40 minutes the agent stops research and publishes what it has (`status: partial`). The push step pulls with rebase first; if data files conflict, the agent takes the remote version of `seen.json`, `prices.csv`, `auctions.json`, `marks.json`, re-applies this run's merge on top, and pushes again.

Condensed list: `deals[]` is computed over all listings in `seen.json` with `status` active or unverified and `last_seen` within the last 7 days, not only this run's finds. Each deal's page is re-fetched when its `checked` date is not today or the listing is new; vanished-listing re-checks stay at 40 per run. Listings gain `first_seen_at` (ISO UTC datetime) alongside `first_seen`.

`latest.json` gains `run_id` (`YYYY-MM-DDTHHMM` Brisbane), `runs_today`, `coverage` (`{sources: N, reached: N, blocked: [ids], listings_by_source: {id: n}}`), and `deals[].first_seen_at`. `runs.json` entries gain `run_id` and `coverage: {sources, reached}`. Reports: one file per day, `reports/YYYY-MM-DD.md`, rewritten by each run with a "Runs today" table at the top.

`prices.csv` stays one row per model, metric and day; reruns replace the day's rows (already the rule), so benchmark history remains daily.

### 4. Site (`index.html`)

- Today header shows the run time and runs today: "Updated 14:05 Brisbane · 8 runs today · next on the hour".
- Deal rows found in the last 24 hours get a `New` chip (from `first_seen_at`); the list order stays by discount.
- Footer coverage line: "Sources: 41 of 56 reached this run · blocked: Chrono24, eBay, …".
- Runs list in the footer shows the last 48 runs with their time.

### 5. Routine

The existing routine is updated, not duplicated: name `watch-radar hourly`, cron `0 * * * *`, model unchanged (Opus 5.5), prompt text refreshed to drop the stale `watchlist.yml` mention and to say the run is hourly. One manual run after the push validates the new mode.

## Constraints

- Cloud fetcher: no logins, no evasion, one descriptive User-Agent, never rotate UAs (classifier). Try one alternative URL shape on a block, then move on.
- Owner marks remain final; sold checks stay as in §1E.
- `index.html`, `ROUTINE_PROMPT.md`, `data/backend.json` are never edited by the routine. `tools/` and `data/sources.json` status fields may be.
- Minimum routine interval is 1 hour; a run that overruns delays nothing but risks a conflict, hence the 50-minute budget.

## Left to the builder

Exact alias lists and brand handles per shop; the WooCommerce GST assumption for Gregory Jewellers and Kalmar (take the product page price when unsure); the `New` chip styling in the site's existing language.
