"""
Tests for Suruga-ya Scraper output data format.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from scraper import SurugaItem


def test_suruga_item_to_dict_defaults():
    """SurugaItem.to_dict() must work with default values."""
    item = SurugaItem(name="テスト商品")
    d = item.to_dict()
    assert d["name"] == "テスト商品"
    assert d["used_price_jpy"] is None
    assert d["new_price_jpy"] is None
    assert d["url"] == ""


def test_suruga_item_to_dict_full():
    """SurugaItem.to_dict() must include unique fields."""
    item = SurugaItem(
        name="ポケモンカード",
        used_price_jpy=500,
        new_price_jpy=800,
        list_price_jpy=1000,
        marketplace_price_jpy=1200,
        brand="ポケモン",
        release_date="2026/01/15",
        url="https://suruga-ya.jp/product/detail/123",
        in_stock=True,
    )
    d = item.to_dict()
    assert d["used_price_jpy"] == 500
    assert d["new_price_jpy"] == 800
    assert d["list_price_jpy"] == 1000  # Unique field
    assert d["brand"] == "ポケモン"  # Unique field
    assert d["release_date"] == "2026/01/15"  # Unique field
    assert d["url"] == "https://suruga-ya.jp/product/detail/123"
    assert d["in_stock"] is True
    assert "scraped_at" in d  # Auto-added timestamp
