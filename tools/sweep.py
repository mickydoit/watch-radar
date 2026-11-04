#!/usr/bin/env python3
"""Feed sweep: pull every structured shop feed in data/sources.json to its last page,
keep the products of the owner's selected brands, and write data/sweep.json.

Standard library only. Run from the repository root:

    python3 tools/sweep.py [--rates '{"USD_AUD":1.43,...}'] [--out data/sweep.json]
                           [--sources data/sources.json] [--focus data/focus.json]
                           [--deadline 480]

Shopify throttles products.json per client across every store it hosts, so Shopify
requests are spaced at least one second apart globally, one 429 pauses every Shopify
worker for Retry-After (capped at 60 s), a source gives up after three 429s and the
whole sweep stops asking Shopify after six. The sweep stops itself at --deadline
seconds (default 480) and writes its output after every source, so a kill or a slow
network still leaves data/sweep.json usable; sources it never reached are "skipped".
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import html
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

USER_AGENT = "watch-radar research bot (personal price tracker; github.com/mickydoit/watch-radar)"
TIMEOUT = 20
MAX_PAGES = 40
PAGE_PAUSE = 0.4
SHOPIFY_GAP = 1.0
MAX_429 = 3            # per source, across its pages
MAX_GLOBAL_429 = 6     # across the whole sweep; past this every unfinished Shopify source is "throttled"
MAX_RETRY_AFTER = 60.0
DEFAULT_DEADLINE = 480.0

# Canonical brand -> lower-case aliases that may appear in a vendor field or at the start of a title.
ALIASES = {
    "anOrdain": ["anordain", "an ordain"],
    "Christopher Ward": ["christopher ward"],
    "Doxa": ["doxa"],
    "Frederique Constant": ["frederique constant", "frédérique constant"],
    "Hamilton": ["hamilton"],
    "IWC": ["iwc", "iwc schaffhausen"],
    "King Seiko": ["king seiko"],
    "Longines": ["longines"],
    "MeisterSinger": ["meistersinger"],
    "Mido": ["mido"],
    "NOMOS Glashütte": ["nomos", "nomos glashütte", "nomos glashutte"],
    "Omega": ["omega"],
    "Orient": ["orient", "orient star"],
    "Oris": ["oris"],
    "Paulin": ["paulin"],
    "Seiko": ["seiko"],
    "Sinn": ["sinn"],
    "Studio Underd0g": ["studio underd0g", "studio underdog"],
    "Tissot": ["tissot"],
    "Tudor": ["tudor"],
    "Unimatic": ["unimatic"],
    "Zenith": ["zenith"],
}
# Brands whose name contains another brand's name: the longer name wins and blocks the shorter one.
SHADOWS = {"Seiko": ["king seiko", "grand seiko"]}

# Fallback rates (AUD per unit of currency) used only when no rates are given and the FX fetch fails.
FALLBACK_RATES = {"USD_AUD": 1.43, "EUR_AUD": 1.60, "GBP_AUD": 1.91, "CHF_AUD": 1.74, "JPY_AUD": 0.0090, "SGD_AUD": 1.12, "HKD_AUD": 0.18, "CAD_AUD": 1.02, "NZD_AUD": 0.80, "AUD_AUD": 1.0}


def _has(alias: str, text: str, at_start: bool) -> bool:
    pat = r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])"
    if at_start:
        pat = r"^\W*" + re.escape(alias) + r"(?![a-z0-9])"
    return re.search(pat, text) is not None


def match_brand(vendor: str, title: str, brands: list, anywhere: bool = False) -> str | None:
    """Return the selected brand this product belongs to, or None.

    The brand must sit in the vendor field or at the start of the title, unless
    `anywhere` is set (a feed that was already queried for that brand): then a whole-word
    hit anywhere in the title counts. Shadowed names (King Seiko under Seiko) still win."""
    v = html.unescape(vendor or "").lower().strip()
    t = html.unescape(title or "").lower().strip()
    combined = v + " " + t
    # Longest alias first so "King Seiko" is decided before "Seiko".
    ordered = sorted(brands, key=lambda b: -max(len(a) for a in ALIASES.get(b, [b.lower()])))
    for brand in ordered:
        aliases = ALIASES.get(brand, [brand.lower()])
        if any(s in combined for s in SHADOWS.get(brand, [])):
            continue
        for a in aliases:
            if _has(a, v, False) or _has(a, t, not anywhere):
                return brand
    return None


def to_aud(price, currency: str, rates: dict) -> int | None:
    if price is None:
        return None
    cur = (currency or "").upper()
    rate = 1.0 if cur == "AUD" else rates.get(f"{cur}_AUD")
    if rate is None:
        return None
    return int(round(float(price) * rate))


def in_band(aud, bands: list) -> bool:
    if aud is None:
        return False
    return any(lo <= aud <= hi for lo, hi in bands)


def _num(x):
    try:
        return float(x) if x not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _base(source: dict, brand: str, title: str, url: str, key: str, price, currency: str, image_url, available, rates, bands) -> dict:
    tier = source.get("tier", "unknown")
    aud = to_aud(price, currency, rates)
    return {
        "key": key,
        "brand": brand,
        "source": source.get("name"),
        "source_id": source.get("id"),
        "url": url,
        "title": title,
        "variant": None,
        "price": price,
        "currency": currency,
        "price_aud": aud,
        "in_band": in_band(aud, bands),
        "condition": "new" if tier in ("authorised", "grey", "microbrand") else "unknown",
        "seller_type": tier,
        "seller_country": source.get("country"),
        "source_quality": "page",
        "image_url": image_url,
        "available": bool(available),
        "compare_at_price": None,
    }


def shopify_listings(product: dict, source: dict, brand: str, rates: dict, bands: list) -> list:
    out = []
    mult = float(source.get("price_multiplier", 1.0) or 1.0)
    cur = source.get("currency", "USD")
    images = product.get("images") or []
    product_image = images[0].get("src") if images and isinstance(images[0], dict) else None
    handle = product.get("handle")
    base_url = f"https://{source['domain']}/products/{handle}"
    variants = product.get("variants") or []
    single_default = len(variants) == 1 and (variants[0].get("title") or "").strip().lower() == "default title"
    for v in variants:
        price = _num(v.get("price"))
        if price is None:
            continue
        price = round(price * mult, 2)
        vtitle = (v.get("title") or "").strip()
        variant = None if single_default or vtitle.lower() == "default title" else vtitle
        url = base_url if single_default else f"{base_url}?variant={v.get('id')}"
        fi = v.get("featured_image")
        image_url = fi.get("src") if isinstance(fi, dict) and fi.get("src") else product_image
        row = _base(source, brand, html.unescape(product.get("title") or ""), url, f"{source['id']}:{v.get('id')}", price, cur, image_url, v.get("available", True), rates, bands)
        row["variant"] = variant
        cap = _num(v.get("compare_at_price"))
        row["compare_at_price"] = round(cap * mult, 2) if cap and cap > price else None
        out.append(row)
    return out


def woo_listings(product: dict, source: dict, brand: str, rates: dict, bands: list) -> list:
    prices = product.get("prices") or {}
    minor = int(prices.get("currency_minor_unit", 2) or 2)
    raw = _num(prices.get("price"))
    if raw is None:
        return []
    mult = float(source.get("price_multiplier", 1.0) or 1.0)
    price = round(raw / (10 ** minor) * mult, 2)
    cur = prices.get("currency_code") or source.get("currency", "AUD")
    images = product.get("images") or []
    image_url = images[0].get("src") if images and isinstance(images[0], dict) else None
    row = _base(source, brand, html.unescape(re.sub(r"<[^>]+>", "", product.get("name") or "")), product.get("permalink"), f"{source['id']}:{product.get('id')}", price, cur, image_url, product.get("is_in_stock", True), rates, bands)
    reg = _num(prices.get("regular_price"))
    if reg is not None:
        reg = round(reg / (10 ** minor) * mult, 2)
        row["compare_at_price"] = reg if reg > price else None
    return [row]


# ---- fetching -------------------------------------------------------------

_shopify_lock = threading.Lock()
_shopify_last = [0.0]
_shopify_until = [0.0]   # monotonic time before which no Shopify request may go out (set by a 429)
GLOBAL_429 = [0]
_deadline = [None]


def reset_throttle() -> None:
    _shopify_last[0] = 0.0
    _shopify_until[0] = 0.0
    GLOBAL_429[0] = 0


def set_deadline(monotonic_at) -> None:
    """Absolute time.monotonic() value after which no request is made; None disables it."""
    _deadline[0] = monotonic_at


def past_deadline() -> bool:
    return _deadline[0] is not None and time.monotonic() >= _deadline[0]


class Deadline(Exception):
    pass


def pause(seconds: float) -> None:
    time.sleep(seconds)


def _shopify_slot() -> None:
    with _shopify_lock:
        now = time.monotonic()
        wait = max(SHOPIFY_GAP - (now - _shopify_last[0]), _shopify_until[0] - now)
        if wait > 0:
            time.sleep(wait)
        _shopify_last[0] = time.monotonic()


class Blocked(Exception):
    pass


def _retry_after(headers) -> float:
    try:
        secs = float(headers.get("Retry-After") or 30)
    except (TypeError, ValueError):
        secs = 30.0
    return min(max(secs, 1.0), MAX_RETRY_AFTER)


def fetch_json(url: str, shopify: bool = False, state: dict | None = None) -> dict:
    """GET a JSON document. `state` is the calling source's dict; its "429" count persists across pages."""
    state = state if state is not None else {}
    while True:
        if past_deadline():
            raise Deadline()
        if shopify:
            if GLOBAL_429[0] >= MAX_GLOBAL_429:
                raise Blocked("throttled: sweep-wide 429 budget spent")
            _shopify_slot()
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as f:
                return json.loads(f.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                state["429"] = state.get("429", 0) + 1
                GLOBAL_429[0] += 1
                if state["429"] >= MAX_429 or GLOBAL_429[0] >= MAX_GLOBAL_429:
                    raise Blocked("HTTP 429 (throttled)") from None
                wait = _retry_after(e.headers)
                if shopify:
                    _shopify_until[0] = max(_shopify_until[0], time.monotonic() + wait)
                pause(wait)
                continue
            if e.code in (401, 403, 430):
                raise Blocked(f"HTTP {e.code}") from None
            raise


def _page_urls(source: dict, brands: list):
    feed = source["feed"]
    if "{brand}" in feed:
        for b in brands:
            yield b, feed.replace("{brand}", urllib.parse.quote(b))
    else:
        yield None, feed


def sweep_source(source: dict, brands: list, rates: dict, bands: list) -> tuple:
    """Pull one source to its last page. Returns (listings, coverage)."""
    cov = {"status": "ok", "products": 0, "listings": 0, "pages": 0, "error": None}
    listings = []
    recipe = source.get("recipe")
    parse = shopify_listings if recipe == "shopify" else woo_listings
    state = {}
    try:
        for brand_q, template in _page_urls(source, brands):
            for page in range(1, MAX_PAGES + 1):
                if past_deadline():
                    raise Deadline()
                data = fetch_json(template.replace("{page}", str(page)), shopify=(recipe == "shopify"), state=state)
                products = data.get("products") if isinstance(data, dict) else data
                if not products:
                    break
                cov["pages"] += 1
                cov["products"] += len(products)
                for p in products:
                    title = re.sub(r"<[^>]+>", "", p.get("title") or p.get("name") or "")
                    brand = match_brand(p.get("vendor") or "", title, brands, anywhere=brand_q is not None)
                    if brand is None:
                        continue
                    rows = parse(p, source, brand, rates, bands)
                    listings.extend(rows)
                pause(PAGE_PAUSE)
    except Deadline:
        cov["status"] = "partial" if cov["pages"] else "skipped"
        cov["error"] = "deadline"
    except Blocked as e:
        cov["status"] = "blocked"
        cov["error"] = str(e)
    except Exception as e:  # one bad source never stops the sweep
        cov["status"] = "error"
        cov["error"] = f"{type(e).__name__}: {e}"[:200]
    cov["listings"] = len(listings)
    if cov["status"] == "ok" and cov["pages"] == 0:
        cov["status"] = "empty"
    # Partial data from a source that failed mid-way is still data.
    return listings, cov


# ---- rates -----------------------------------------------------------------

def fetch_rates() -> tuple:
    """AUD per unit of each currency, from frankfurter.app (ECB). Returns (rates, source)."""
    try:
        data = fetch_json("https://api.frankfurter.app/latest?from=AUD")
        per_aud = data.get("rates") or {}
        rates = {f"{c}_AUD": round(1.0 / v, 6) for c, v in per_aud.items() if v}
        rates["AUD_AUD"] = 1.0
        return rates, f"frankfurter.app {data.get('date')}"
    except Exception as e:
        return dict(FALLBACK_RATES), f"fallback (fetch failed: {type(e).__name__})"


# ---- main ------------------------------------------------------------------

def run(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rates", help="JSON object of <CUR>_AUD rates; fetched from frankfurter.app when omitted")
    ap.add_argument("--out", default="data/sweep.json")
    ap.add_argument("--sources", default="data/sources.json")
    ap.add_argument("--focus", default="data/focus.json")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--deadline", type=float, default=DEFAULT_DEADLINE, help="seconds after which no more requests are made (0 = none)")
    args = ap.parse_args(argv)

    with open(args.focus, encoding="utf-8") as f:
        focus = json.load(f)
    brands = focus.get("brands") or []
    bands = focus.get("bands") or []
    with open(args.sources, encoding="utf-8") as f:
        registry = json.load(f)
    sources = [s for s in registry.get("sources", []) if s.get("recipe") in ("shopify", "woocommerce") and s.get("feed")]

    if args.rates:
        rates, rates_source = json.loads(args.rates), "argument"
    else:
        rates, rates_source = fetch_rates()

    started = datetime.now(timezone.utc)
    reset_throttle()
    set_deadline(time.monotonic() + args.deadline if args.deadline and args.deadline > 0 else None)
    coverage = {}
    listings = []

    def write_out(final: bool) -> dict:
        rows = sorted(listings, key=lambda r: (r["brand"], r["price_aud"] if r["price_aud"] is not None else 10**9))
        out = {
            "ran_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "seconds": int((datetime.now(timezone.utc) - started).total_seconds()),
            "complete": final,
            "deadline_seconds": args.deadline,
            "rates": rates,
            "rates_source": rates_source,
            "focus": {"brands": brands, "bands": bands},
            "listings": rows,
            "coverage": coverage,
        }
        tmp = args.out + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        os.replace(tmp, args.out)
        return out

    out = write_out(False)
    try:
        if brands and sources:
            with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
                futures = {ex.submit(sweep_source, s, brands, rates, bands): s for s in sources}
                for fut in cf.as_completed(futures):
                    s = futures[fut]
                    rows, cov = fut.result()
                    coverage[s["id"]] = cov
                    listings.extend(rows)
                    write_out(False)
    finally:
        today = started.strftime("%Y-%m-%d")
        for s in registry.get("sources", []):
            cov = coverage.get(s["id"])
            if cov:
                st = s.setdefault("status", {})
                st["last_status"] = cov["status"]
                st["last_listings"] = cov["listings"]
                st["last_checked"] = today
                if cov["status"] == "ok":
                    st["last_ok"] = today
        out = write_out(True)
        with open(args.sources, "w", encoding="utf-8") as f:
            json.dump(registry, f, ensure_ascii=False, indent=2)
            f.write("\n")
    listings = out["listings"]
    ok = sum(1 for c in coverage.values() if c["status"] == "ok")
    inb = sum(1 for r in listings if r["in_band"])
    print(f"sweep: {len(sources)} feeds, {ok} ok, {len(listings)} listings for {len(brands)} brands, {inb} in band, {out['seconds']} s, rates from {rates_source}")
    for sid, c in sorted(coverage.items()):
        print(f"  {sid:28} {c['status']:8} pages={c['pages']:2} products={c['products']:5} listings={c['listings']:4} {c['error'] or ''}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
