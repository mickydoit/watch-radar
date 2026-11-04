# Hourly Full-Depth Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every hourly routine run reach a listed, measured set of sellers, and condense all live finds into one ranked list on the site.

**Architecture:** A JSON source registry names every seller and its fetch recipe; a stdlib Python script pulls every structured feed to the last page and writes normalised listings plus per-source coverage; the routine prompt makes the agent run the script first, then research the html and snippet sources, compute deals over all live listings in memory, and publish within a 50-minute budget. The site shows run cadence, new finds and coverage.

**Tech Stack:** Python 3 stdlib (urllib, json, concurrent.futures, unittest), vanilla JS in `index.html`, cloud routine via RemoteTrigger.

**Spec:** `docs/specs/2026-11-04-hourly-full-depth-design.md`

## Global Constraints

- One descriptive User-Agent for all requests: `watch-radar research bot (personal price tracker; github.com/mickydoit/watch-radar)`. Never vary it.
- Shopify throttles `products.json` per client across all stores: at most one Shopify request per second globally, honour `Retry-After` on 429 (default 30 s), give up on a source after 3 consecutive 429s.
- 20 s timeout per request, 40 pages max per source, 0.4 s between pages of one host.
- No new dependencies; `python3 tools/sweep.py` must run in the cloud clone with nothing installed.
- Run budget: publish within 50 minutes; research stops at 40.

## Review Focus

- A feed whose `vendor` is blank but whose title starts with the brand (Teddy sells "MeisterSinger Neo 36" under vendor "MeisterSinger", but some shops leave vendor empty): matched by title prefix. Test in Task 2.
- A Shopify variant with `available: false`: kept with `available: false`, never counted as a deal by the prompt. Test in Task 2.
- Define's WooCommerce price `290909` cents ex-GST: `price_aud` 3200. Test in Task 2.
- A source that times out or returns HTML: coverage `status: "error"` with the exception name, the other sources unaffected. Test in Task 2.
- `first_seen_at` missing on old listings: the site treats a deal as not new rather than throwing. Test in Task 4.

---

### Task 1: Source registry

**Files:**
- Create: `data/sources.json`

**Interfaces:**
- Produces: `{"sources": [{"id","name","domain","country","currency","tier","recipe","feed","search","price_multiplier","brands","status":{"last_ok","last_status","last_listings"}}]}` where `recipe` ∈ shopify | woocommerce | html | snippet, `feed` is a URL template with `{page}` (and `{brand}` for WooCommerce search), `brands` is a list or `"auto"`.

- [ ] **Step 1: Write the registry** from the 4 Nov probe and census: every Shopify and WooCommerce domain that answered, the html sources that gave listings in `data/seen.json`, and the snippet-only blocked sites. Mark Define `price_multiplier: 1.1`; others `1.0`.
- [ ] **Step 2: Validate** `python3 -c "import json;d=json.load(open('data/sources.json'));print(len(d['sources']))"` prints ≥ 55 and every entry has the keys above.
- [ ] **Step 3: Commit** `git commit -m "Source registry: every seller the routine must reach, with its fetch recipe"`.

### Task 2: Feed sweep script

**Files:**
- Create: `tools/sweep.py`, `tools/test_sweep.py`

**Interfaces:**
- Produces: `python3 tools/sweep.py [--rates '{"USD_AUD":1.43,...}'] [--out data/sweep.json] [--sources data/sources.json] [--focus data/focus.json]` writing `{"ran_at","rates","focus":{"brands","bands"},"listings":[...],"coverage":{id:{status,products,listings,pages,error}}}` and updating `status` in `data/sources.json`.
- Pure functions for tests: `match_brand(vendor: str, title: str, brands: list[str]) -> str | None`, `shopify_listings(product: dict, source: dict, rate: float, bands: list) -> list[dict]`, `woo_listings(product: dict, source: dict, rate: float, bands: list) -> list[dict]`, `to_aud(price: float, currency: str, rates: dict) -> int | None`, `in_band(aud: int, bands: list) -> bool`.

- [ ] **Step 1: Write failing tests** in `tools/test_sweep.py` (unittest): `test_match_brand_vendor`, `test_match_brand_title_prefix_when_vendor_blank`, `test_match_brand_alias` ("Nomos" → "NOMOS Glashütte", "Frédérique Constant", "Anordain", "Studio Underdog"), `test_match_king_seiko_not_seiko`, `test_shopify_variant_listings` (two variants → two listings, `?variant=` urls, `available`, `compare_at_price`, `image_url`), `test_woo_define_cents_ex_gst` (290909 → 3200), `test_in_band`, `test_to_aud_unknown_currency_is_none`, `test_fetch_error_lands_in_coverage` (monkeypatched fetch raising → coverage status error).
- [ ] **Step 2: Run** `python3 -m unittest tools.test_sweep -v` → fails with ImportError.
- [ ] **Step 3: Implement** `tools/sweep.py` with those functions plus `run(args)`: global Shopify token bucket (threading.Lock + last-request time), per-source paging, ThreadPoolExecutor(4) across sources, writes output and registry status.
- [ ] **Step 4: Run** tests → PASS. Then a live smoke: `python3 tools/sweep.py --out /tmp/sweep.json` from the repo; expect coverage with ≥ 20 `ok` sources and listings for the selected brands.
- [ ] **Step 5: Commit** `git commit -m "Feed sweep: every structured shop feed paged to the end before the agent starts searching"`.

### Task 3: Routine prompt

**Files:**
- Modify: `ROUTINE_PROMPT.md`

- [ ] **Step 1: Edit** the intro (hourly, not daily), step 0.5 (run type: `daily` at UTC hour 21, `weekly` on Monday at that hour, else `hourly`; `run_id`), step 0.7 (run `python3 tools/sweep.py`, read `data/sweep.json`, treat its listings as page-quality listings, report coverage), §1 source list → "the registry `data/sources.json` is the list; every `html` source for every selected brand every run; `snippet` sources via search", §1B deals over all live listings in `seen.json` (7 days), §1E.1 re-fetch when `checked` ≠ today, §1D and §1F daily only, budget section (50-minute wall clock, stop research at 40), §2 `first_seen_at`, §3 `run_id`/`runs_today`/`coverage`, §4 conflict recipe, reports one file per day with a Runs-today table.
- [ ] **Step 2: Verify** `grep -c "hourly" ROUTINE_PROMPT.md` ≥ 5 and the file still forbids editing itself.
- [ ] **Step 3: Commit** `git commit -m "Routine runs every hour at full depth: registry-driven sources, 50-minute budget, deals over all live listings"`.

### Task 4: Site

**Files:**
- Modify: `index.html` (Today header, deal rows, footer)

- [ ] **Step 1: Edit** Today eyebrow: `Updated HH:MM Brisbane · N runs today · next on the hour` from `latest.run_at_local`, `latest.runs_today`. Deal row: `New` chip when `first_seen_at` within 24 h of `latest.run_at_utc` (fallback: `first_seen === run_date`). Footer: coverage line from `latest.coverage`; runs list limited to 48 with `run_id` time.
- [ ] **Step 2: Verify** with a Playwright harness in the scratchpad: serve the repo on :8881, load with a fixture `latest.json` carrying `coverage`, `runs_today`, one deal with `first_seen_at` an hour ago and one without; assert the chip count is 1, the coverage line renders, 0 console errors, phone scrollWidth 390.
- [ ] **Step 3: Commit** `git commit -m "Site shows the hourly cadence, marks finds from the last day and reports source coverage"`.

### Task 5: Routine and verification

- [ ] **Step 1: Push** `git push origin main`.
- [ ] **Step 2: Update routine** `trig_01C141RVeHnA1zNdtEgnYNrP`: name `watch-radar hourly`, cron `0 * * * *`, prompt text refreshed (no `watchlist.yml`; says hourly; same safety rules).
- [ ] **Step 3: Fire one run**, then `get_run_log`; expect `python3 tools/sweep.py` in the log, a commit `radar: <run_id> hourly`, `latest.json.coverage.reached` ≥ 20.
- [ ] **Step 4: Update memory** `project-watch-radar.md` with the new cadence, registry, script, budget and cost acknowledgement.
