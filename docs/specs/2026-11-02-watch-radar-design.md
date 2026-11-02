# watch-radar — design note (2 Nov 2026)

## Intent
The owner wants continuous, unattended research on sales of a few specific watch references: new listings worth looking at, how asking prices are moving, and auction lots coming up. The result should land in the inbox without the owner's Mac being on.

## Decisions (owner approved the chat description on 2 Nov 2026 with "go with your assumptions"; items marked *my call* are Claude's)
- **Runner:** Claude Code scheduled cloud routine, daily 07:00 Australia/Brisbane = `0 21 * * *` UTC. Monday (Brisbane) runs add a weekly price roundup. *My call:* one routine rather than two, so there is one thing to pause.
- **Memory:** this GitHub repo. The routine commits state and a per-run report to `main`. Cloud sessions start empty, so without this every run would repeat itself.
- **Delivery:** one HTML email per run via the Resend HTTP API to the owner's personal address, held in the cloud environment variable `RADAR_TO` with the key in `RESEND_API_KEY`. Owner decided 2 Nov 2026 that no work (CV) Microsoft account may be attached to this project; the M365 connector was detached from the routine. Sender is Resend's `onboarding@resend.dev` until a domain is verified (`RADAR_FROM`). Always sends, even when quiet, so a missing email means the routine failed.
- **Watchlist shape:** reference-level entries with condition list, full-set flag, AUD ceiling and markets. Listings over the ceiling feed price history but are not emailed.
- **Sources:** Chrono24, WatchRecon, eBay, named dealers for listings; WatchCharts and eBay sold for price; Phillips, Sotheby's, Christie's, Bonhams, Antiquorum, Everywatch, Leonard Joel, Lawsons for auctions.
- **Model:** `claude-sonnet-5-5` (routine default). *My call;* switch to Opus if the matching quality disappoints.
- **Privacy:** repo is private (it holds price ceilings).
- **Initial watchlist:** four example references chosen by Claude so the first runs are real. The email nags until they are replaced.

## Non-goals
- Not a sniping tool. Daily cadence; the minimum a routine allows is hourly anyway.
- No bidding, offers, seller contact, account creation or block evasion.
- No price prediction. Numbers and dates only.

## Open items / to verify from the cloud
1. The routine can push to a private repo on `main`.
2. The routine can read `RADAR_TO`/`RESEND_API_KEY` from the environment and Resend accepts the send.
3. Chrono24 / eBay / WatchCharts pages are readable through WebFetch at least some of the time.
All three are checked by a manual first run at setup.
