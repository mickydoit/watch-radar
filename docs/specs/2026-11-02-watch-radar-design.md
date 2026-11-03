# watch-radar — design note (2 Nov 2026)

## Intent
The owner wants continuous, unattended research on sales of a few specific watch references: new listings worth looking at, how asking prices are moving, and auction lots coming up. The result should land in the inbox without the owner's Mac being on.

## Decisions (owner approved the chat description on 2 Nov 2026 with "go with your assumptions"; items marked *my call* are Claude's)
- **Runner:** Claude Code scheduled cloud routine, daily 07:00 Australia/Brisbane = `0 21 * * *` UTC. Monday (Brisbane) runs add a weekly price roundup. *My call:* one routine rather than two, so there is one thing to pause.
- **Memory:** this GitHub repo. The routine commits state and a per-run report to `main`. Cloud sessions start empty, so without this every run would repeat itself.
- **Delivery (changed 3 Nov 2026):** no email. A static web app (`index.html`) on GitHub Pages reads the committed `data/` files; the routine's last step is writing `data/latest.json` and pushing. The page shows a fresh/stale/failed status from `run_date`, so a silent failure is still visible. History: owner first ruled out the work Microsoft account (M365 connector detached 2 Nov), Resend to Hotmail was built, then superseded by the web app on 3 Nov.
- **Below-market (added 3 Nov 2026, owner's request):** per watch, a median asking-price benchmark across all readable markets (like-for-like on condition, 30-day median), listings under it ranked by discount and flagged verify / grey-new / clean. *My call:* median not mean; 3% threshold; 25%+ under is auto-flagged verify. Grey-market new sellers added to the source list because that is where below-market new pieces live for non-allocation brands.
- **Watchlist shape:** reference-level entries with condition list, full-set flag, AUD ceiling and markets. Listings over the ceiling feed price history but are not emailed.
- **Sources:** Chrono24, WatchRecon, eBay, named dealers for listings; WatchCharts and eBay sold for price; Phillips, Sotheby's, Christie's, Bonhams, Antiquorum, Everywatch, Leonard Joel, Lawsons for auctions.
- **Model:** `claude-opus-5-5` since 3 Nov 2026 (owner approved after two Sonnet runs under-researched: 8 and 37 fetches, effort floor unmet). Started on `claude-sonnet-5-5`.
- **Privacy:** repo must be **public** for GitHub Pages on a free account (decided 3 Nov; owner said they don't mind). Watchlist and reports are therefore visible.
- **Initial watchlist:** four example references chosen by Claude so the first runs are real. The email nags until they are replaced.

## Non-goals
- Not a sniping tool. Daily cadence; the minimum a routine allows is hourly anyway.
- No bidding, offers, seller contact, account creation or block evasion.
- No price prediction. Numbers and dates only.

## Open items / to verify from the cloud
1. The routine can push to a private repo on `main`.
2. GitHub Pages is enabled on `main` and redeploys after the routine's push.
3. Chrono24 / eBay / WatchCharts pages are readable through WebFetch at least some of the time.
All three are checked by a manual first run at setup.
