"""Tests for tools/sweep.py. Run: python3 -m unittest tools.test_sweep -v"""
import contextlib
import email.message
import io
import json
import os
import tempfile
import time
import unittest
import urllib.error
import warnings
from unittest import mock

warnings.filterwarnings("ignore", category=ResourceWarning, message=".*HTTPError.*")

from tools import sweep

BRANDS = ["NOMOS Glashütte", "Frederique Constant", "anOrdain", "Studio Underd0g", "Seiko", "King Seiko", "Christopher Ward", "IWC"]
RATES = {"USD_AUD": 1.5, "EUR_AUD": 1.6, "GBP_AUD": 1.9, "AUD_AUD": 1.0}
BANDS = [[1000, 2000]]


class MatchBrand(unittest.TestCase):
    def test_vendor(self):
        self.assertEqual(sweep.match_brand("Seiko", "Presage SPB463", BRANDS), "Seiko")

    def test_title_prefix_when_vendor_blank(self):
        self.assertEqual(sweep.match_brand("", "Christopher Ward C63 Sealander 39", BRANDS), "Christopher Ward")

    def test_aliases(self):
        self.assertEqual(sweep.match_brand("Nomos", "Club Campus 36", BRANDS), "NOMOS Glashütte")
        self.assertEqual(sweep.match_brand("Frédérique Constant", "Classics", BRANDS), "Frederique Constant")
        self.assertEqual(sweep.match_brand("Anordain", "Model 2", BRANDS), "anOrdain")
        self.assertEqual(sweep.match_brand("Studio Underdog", "Watermelon", BRANDS), "Studio Underd0g")
        self.assertEqual(sweep.match_brand("IWC Schaffhausen", "Pilot", BRANDS), "IWC")

    def test_king_seiko_is_not_seiko(self):
        self.assertEqual(sweep.match_brand("Seiko", "King Seiko KSK SPB279", BRANDS), "King Seiko")
        self.assertEqual(sweep.match_brand("King Seiko", "SPB279", BRANDS), "King Seiko")
        self.assertIsNone(sweep.match_brand("King Seiko", "SPB279", ["Seiko"]))

    def test_unselected_brand_is_none(self):
        self.assertIsNone(sweep.match_brand("Rolex", "Submariner", BRANDS))

    def test_anywhere_matches_brand_inside_title_when_asked(self):
        brands = BRANDS + ["Omega"]
        self.assertIsNone(sweep.match_brand("", "Pre-Owned Omega Seamaster", brands))
        self.assertEqual(sweep.match_brand("", "Pre-Owned Omega Seamaster", brands, anywhere=True), "Omega")
        self.assertEqual(sweep.match_brand("", "1965 King Seiko 44KS", brands, anywhere=True), "King Seiko")
        self.assertIsNone(sweep.match_brand("", "1965 King Seiko 44KS", ["Seiko"], anywhere=True))


class Money(unittest.TestCase):
    def test_to_aud(self):
        self.assertEqual(sweep.to_aud(1000, "USD", RATES), 1500)
        self.assertEqual(sweep.to_aud(999.5, "AUD", RATES), 1000)

    def test_unknown_currency_is_none(self):
        self.assertIsNone(sweep.to_aud(100, "XYZ", RATES))

    def test_in_band(self):
        self.assertTrue(sweep.in_band(1000, BANDS))
        self.assertTrue(sweep.in_band(2000, BANDS))
        self.assertFalse(sweep.in_band(2001, BANDS))
        self.assertFalse(sweep.in_band(None, BANDS))


SHOP = {"id": "teddy", "name": "Teddy Baldassarre", "domain": "teddybaldassarre.com", "country": "US", "currency": "USD", "tier": "authorised", "recipe": "shopify", "price_multiplier": 1.0}
PRODUCT = {
    "id": 1, "title": "MeisterSinger Neo 36", "handle": "meistersinger-neo-36", "vendor": "MeisterSinger",
    "images": [{"src": "https://cdn.shopify.com/neo.jpg"}],
    "variants": [
        {"id": 11, "title": "Ivory / Cordovan", "price": "999.00", "compare_at_price": "1250.00", "available": True, "featured_image": {"src": "https://cdn.shopify.com/ivory.jpg"}},
        {"id": 12, "title": "Blue / Steel", "price": "1099.00", "compare_at_price": None, "available": False, "featured_image": None},
    ],
}


class Shopify(unittest.TestCase):
    def test_variant_listings(self):
        out = sweep.shopify_listings(PRODUCT, SHOP, "MeisterSinger", RATES, BANDS)
        self.assertEqual(len(out), 2)
        a, b = out
        self.assertEqual(a["url"], "https://teddybaldassarre.com/products/meistersinger-neo-36?variant=11")
        self.assertEqual(a["key"], "teddy:11")
        self.assertEqual(a["variant"], "Ivory / Cordovan")
        self.assertEqual(a["price"], 999.0)
        self.assertEqual(a["currency"], "USD")
        self.assertEqual(a["price_aud"], 1498)
        self.assertEqual(a["compare_at_price"], 1250.0)
        self.assertTrue(a["available"])
        self.assertTrue(a["in_band"])
        self.assertEqual(a["image_url"], "https://cdn.shopify.com/ivory.jpg")
        self.assertEqual(a["condition"], "new")
        self.assertEqual(a["seller_type"], "authorised")
        self.assertEqual(a["source_quality"], "page")
        self.assertEqual(a["brand"], "MeisterSinger")
        self.assertFalse(b["available"])
        self.assertEqual(b["image_url"], "https://cdn.shopify.com/neo.jpg")

    def test_single_default_variant_has_no_variant_label(self):
        p = dict(PRODUCT, variants=[{"id": 13, "title": "Default Title", "price": "999.00", "compare_at_price": None, "available": True}])
        out = sweep.shopify_listings(p, SHOP, "MeisterSinger", RATES, BANDS)
        self.assertIsNone(out[0]["variant"])
        self.assertEqual(out[0]["url"], "https://teddybaldassarre.com/products/meistersinger-neo-36")


DEFINE = {"id": "define", "name": "Define Watches", "domain": "definewatches.com.au", "country": "AU", "currency": "AUD", "tier": "authorised", "recipe": "woocommerce", "price_multiplier": 1.1}
WOO = {"id": 77, "name": "Sinn 556 I", "permalink": "https://definewatches.com.au/product/sinn-556-i/", "images": [{"src": "https://definewatches.com.au/556.jpg"}],
       "prices": {"price": "290909", "regular_price": "290909", "sale_price": "290909", "currency_code": "AUD", "currency_minor_unit": 2}, "is_in_stock": True}


class Woo(unittest.TestCase):
    def test_define_cents_ex_gst(self):
        out = sweep.woo_listings(WOO, DEFINE, "Sinn", RATES, BANDS)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["price"], 3200.0)
        self.assertEqual(out[0]["price_aud"], 3200)
        self.assertEqual(out[0]["key"], "define:77")
        self.assertEqual(out[0]["url"], "https://definewatches.com.au/product/sinn-556-i/")
        self.assertFalse(out[0]["in_band"])
        self.assertTrue(out[0]["available"])


def _http_error(code, retry_after=None):
    h = email.message.Message()
    if retry_after is not None:
        h["Retry-After"] = str(retry_after)
    return urllib.error.HTTPError("https://x/products.json", code, "Too Many Requests", h, io.BytesIO(b""))


class Throttle(unittest.TestCase):
    def setUp(self):
        sweep.reset_throttle()
        sweep.set_deadline(None)
        self.sleep = mock.patch.object(sweep.time, "sleep").start()   # the Shopify slot's own gap sleep
        self.addCleanup(mock.patch.stopall)

    def test_429_gives_up_after_three_per_source(self):
        state = {}
        with mock.patch("urllib.request.urlopen", side_effect=_http_error(429, 1)), mock.patch.object(sweep, "pause") as p:
            with self.assertRaises(sweep.Blocked):
                sweep.fetch_json("https://x/products.json?page=1", shopify=True, state=state)
        self.assertEqual(p.call_count, 2)   # waits after the 1st and 2nd 429; the 3rd ends the source

    def test_429_count_carries_across_pages_of_one_source(self):
        state = {}
        calls = [0]
        def side(req, timeout=None):
            calls[0] += 1
            if calls[0] in (1, 2):
                raise _http_error(429, 1)
            if calls[0] == 3:
                return io.BytesIO(b'{"products": []}')
            raise _http_error(429, 1)
        with mock.patch("urllib.request.urlopen", side_effect=side), mock.patch.object(sweep, "pause") as p:
            sweep.fetch_json("https://x/products.json?page=1", shopify=True, state=state)  # 2 x 429 then ok
            with self.assertRaises(sweep.Blocked):
                sweep.fetch_json("https://x/products.json?page=2", shopify=True, state=state)  # 3rd 429 ends the source
        self.assertEqual(p.call_count, 2)

    def test_retry_after_is_capped_at_60_seconds(self):
        with mock.patch("urllib.request.urlopen", side_effect=_http_error(429, 3600)), mock.patch.object(sweep, "pause") as p:
            with self.assertRaises(sweep.Blocked):
                sweep.fetch_json("https://x/products.json", shopify=True, state={})
        self.assertEqual(p.call_args_list[0].args[0], 60)

    def test_global_429_budget_blocks_every_shopify_source(self):
        sweep.GLOBAL_429[0] = sweep.MAX_GLOBAL_429
        with mock.patch("urllib.request.urlopen") as u:
            with self.assertRaises(sweep.Blocked) as cm:
                sweep.fetch_json("https://y/products.json", shopify=True, state={})
        self.assertEqual(u.call_count, 0)
        self.assertIn("throttled", str(cm.exception))

    def test_429_pauses_every_shopify_worker(self):
        with mock.patch("urllib.request.urlopen", side_effect=_http_error(429, 5)), mock.patch.object(sweep, "pause"):
            with self.assertRaises(sweep.Blocked):
                sweep.fetch_json("https://x/products.json", shopify=True, state={})
        self.sleep.reset_mock()
        sweep._shopify_slot()
        self.assertTrue(self.sleep.called)
        self.assertGreater(self.sleep.call_args.args[0], 3.5)


class Deadline(unittest.TestCase):
    def setUp(self):
        sweep.reset_throttle()

    def tearDown(self):
        sweep.set_deadline(None)

    def test_past_deadline_skips_source_without_fetching(self):
        sweep.set_deadline(time.monotonic() - 1)
        src = dict(SHOP, feed="https://teddybaldassarre.com/products.json?limit=250&page={page}")
        with mock.patch.object(sweep, "fetch_json") as f:
            listings, cov = sweep.sweep_source(src, BRANDS, RATES, BANDS)
        self.assertEqual(f.call_count, 0)
        self.assertEqual(cov["status"], "skipped")
        self.assertEqual(cov["error"], "deadline")

    def test_deadline_mid_source_keeps_pages_already_read(self):
        sweep.set_deadline(time.monotonic() + 3600)
        src = dict(SHOP, feed="https://teddybaldassarre.com/products.json?limit=250&page={page}")
        def first_page_then_expire(url, shopify=False, state=None):
            sweep.set_deadline(time.monotonic() - 1)
            return {"products": [PRODUCT]}
        with mock.patch.object(sweep, "fetch_json", side_effect=first_page_then_expire), mock.patch.object(sweep, "pause"):
            listings, cov = sweep.sweep_source(src, BRANDS + ["MeisterSinger"], RATES, BANDS)
        self.assertEqual(cov["status"], "partial")
        self.assertEqual(cov["error"], "deadline")
        self.assertEqual(cov["pages"], 1)
        self.assertEqual(len(listings), 2)


class WooMatching(unittest.TestCase):
    def test_woo_matches_brand_anywhere_in_title_and_unescapes_entities(self):
        src = dict(DEFINE, id="kalmar", feed="https://www.kalmarantiques.com.au/wp-json/wc/store/v1/products?search={brand}&per_page=100&page={page}")
        def product(i, name):
            return dict(WOO, id=i, name=name)
        pages = {
            "Omega": [[product(1, "Pre-Owned Omega Seamaster"), product(2, "Omega NATO strap")], []],
            "Frederique Constant": [[product(3, "Fr&eacute;d&eacute;rique Constant Classics")], []],
        }
        def fetch(url, shopify=False, state=None):
            import urllib.parse
            q = urllib.parse.unquote(url.split("search=")[1].split("&")[0])
            return pages[q].pop(0)
        with mock.patch.object(sweep, "fetch_json", side_effect=fetch), mock.patch.object(sweep, "pause"):
            listings, cov = sweep.sweep_source(src, ["Omega", "Frederique Constant"], RATES, BANDS)
        titles = sorted((r["brand"], r["title"]) for r in listings)
        self.assertIn(("Omega", "Pre-Owned Omega Seamaster"), titles)
        self.assertIn(("Frederique Constant", "Frédérique Constant Classics"), titles)


class RunOutput(unittest.TestCase):
    def test_run_writes_output_after_each_source(self):
        d = tempfile.mkdtemp()
        srcs = os.path.join(d, "sources.json"); focus = os.path.join(d, "focus.json"); out = os.path.join(d, "sweep.json")
        a = dict(SHOP, id="a", feed="https://a/products.json?page={page}")
        b = dict(SHOP, id="b", feed="https://b/products.json?page={page}")
        with open(srcs, "w") as f:
            json.dump({"sources": [a, b]}, f)
        with open(focus, "w") as f:
            json.dump({"brands": ["Seiko"], "bands": BANDS}, f)
        seen = {}
        def fake_source(source, brands, rates, bands):
            if source["id"] == "b":   # a finished first; its coverage must reach the file while b is still running
                for _ in range(200):
                    cov = {}
                    if os.path.exists(out):
                        with open(out) as f:
                            cov = json.load(f)["coverage"]
                    if cov:
                        break
                    time.sleep(0.01)
                seen["partial"] = cov
            return [], {"status": "empty", "products": 0, "listings": 0, "pages": 0, "error": None}
        with mock.patch.object(sweep, "sweep_source", side_effect=fake_source), contextlib.redirect_stdout(io.StringIO()):
            sweep.run(["--rates", json.dumps(RATES), "--out", out, "--sources", srcs, "--focus", focus, "--workers", "1"])
        self.assertEqual(set(seen["partial"]), {"a"})
        with open(out) as f:
            final = json.load(f)
        self.assertEqual(set(final["coverage"]), {"a", "b"})
        self.assertIn("deadline_seconds", final)


class Coverage(unittest.TestCase):
    def test_fetch_error_lands_in_coverage(self):
        src = dict(SHOP, feed="https://teddybaldassarre.com/products.json?limit=250&page={page}")
        with mock.patch.object(sweep, "fetch_json", side_effect=TimeoutError("slow")):
            listings, cov = sweep.sweep_source(src, BRANDS, RATES, BANDS)
        self.assertEqual(listings, [])
        self.assertEqual(cov["status"], "error")
        self.assertIn("TimeoutError", cov["error"])

    def test_pages_until_empty(self):
        src = dict(SHOP, feed="https://teddybaldassarre.com/products.json?limit=250&page={page}")
        pages = [{"products": [PRODUCT]}, {"products": [dict(PRODUCT, id=2, handle="x", vendor="Rolex", title="Submariner")]}, {"products": []}]
        with mock.patch.object(sweep, "fetch_json", side_effect=pages), mock.patch.object(sweep, "pause"):
            listings, cov = sweep.sweep_source(src, BRANDS + ["MeisterSinger"], RATES, BANDS)
        self.assertEqual(cov["status"], "ok")
        self.assertEqual(cov["pages"], 2)
        self.assertEqual(cov["products"], 2)
        self.assertEqual(cov["listings"], 2)
        self.assertEqual(len(listings), 2)

    def test_empty_feed_is_empty_status(self):
        src = dict(SHOP, feed="https://teddybaldassarre.com/products.json?limit=250&page={page}")
        with mock.patch.object(sweep, "fetch_json", return_value={"products": []}), mock.patch.object(sweep, "pause"):
            listings, cov = sweep.sweep_source(src, BRANDS, RATES, BANDS)
        self.assertEqual(cov["status"], "empty")


if __name__ == "__main__":
    unittest.main()
