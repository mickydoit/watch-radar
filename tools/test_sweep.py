"""Tests for tools/sweep.py. Run: python3 -m unittest tools.test_sweep -v"""
import unittest
from unittest import mock

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
