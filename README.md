# Suruga-ya Scraper — 駿河屋 中古フィギュア・ホビー価格

**Scrape used & new prices from Suruga-ya (駿河屋), Japan's largest second-hand collectibles marketplace.**  
Anime figures, Gundam models, trading cards, video games, manga — with **3 unique data fields** (list price, brand, release date) not available in competing scrapers.

[![Apify Store](https://img.shields.io/badge/Apify-Store-blue)](https://apify.com/fruitful_quintessence/surugaya-japan-hobby-prices)
[![MIT License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## 🚀 Quick Start on Apify

1. Go to [Suruga-ya Scraper on Apify Store](https://apify.com/fruitful_quintessence/surugaya-japan-hobby-prices)
2. Click **"Try"** or **"Start"**
3. Enter a search keyword (e.g., "ポケモン", "フィギュア")
4. Run and get your data as JSON, CSV, or XLSX

**Pricing:** Pay per event — $0.005/run + $0.01/search. Free plan available for testing.

---

## 🔥 Unique Value — 3 Fields No Other Scraper Has

| Field | What It Tells You | Why It Matters |
|-------|-------------------|----------------|
| **List price (定価)** | Original retail price | Spot arbitrage opportunities: find items selling far below MSRP |
| **Brand / Publisher** | e.g., ポケモン, バンダイ, グッドスマイルカンパニー | Filter and analyze by manufacturer, not just category |
| **Release date** | Official launch date (YYYY/MM/DD) | Track price depreciation over time; identify vintage items |

These 3 fields make this scraper uniquely valuable for **resale arbitrage research** — you can instantly spot items where the used price is far below the original retail price.

---

## 📋 All Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Product name (Japanese) |
| `url` | string | Product detail page URL |
| `used_price_jpy` | int\|null | **Second-hand price** in JPY |
| `new_price_jpy` | int\|null | New/sealed price in JPY |
| `list_price_jpy` | int\|null | **Original retail price** (定価) — **unique** |
| `marketplace_price_jpy` | int\|null | Marketplace reseller price (マケプレ) |
| `brand` | string | **Publisher/brand** name — **unique** |
| `release_date` | string | **Release date** (YYYY/MM/DD) — **unique** |
| `category` | string | Product category path |
| `condition_badge` | string | Condition label (e.g., 新入荷, 限定) |
| `in_stock` | boolean | In-stock status |
| `image_url` | string | Product thumbnail URL |
| `scraped_at` | string | ISO 8601 scrape timestamp |

---

## 📊 Example Output

```json
{
  "name": "ポケモンチェンジ ヒトカゲ/リザードン 「ポケットモンスター」",
  "url": "https://www.suruga-ya.jp/product/detail/607226065",
  "used_price_jpy": 1850,
  "new_price_jpy": 1850,
  "list_price_jpy": 2420,
  "marketplace_price_jpy": null,
  "brand": "ポケモン",
  "release_date": "2026/07/25",
  "category": "トレーディングフィギュア",
  "condition_badge": "新入荷",
  "in_stock": true,
  "image_url": "https://www.suruga-ya.jp/database/photo.php?shinaban=607226065&size=m",
  "scraped_at": "2026-07-24T13:30:00Z"
}
```

---

## 🎯 Use Cases

1. **Reseller arbitrage** — Find items where used price is far below list price (定価)
2. **Price trend monitoring** — Track price changes for specific collectibles over days/weeks
3. **Proxy buying integration** — Feed Suruga-ya catalog data into proxy/service platforms
4. **Collector tools** — Build wishlist price alerts for figure, card, and game collectors
5. **Japanese hobby market research** — Analyze pricing trends across 100+ product categories
6. **AI/ML datasets** — Build training data for price prediction and demand forecasting models

---

## 🏗 Architecture

```
User Input → httpx HTTP client (retry + exponential backoff)
                 ↓ failed (Cloudflare challenge / empty response)
            Playwright (Firefox headless) — automatic fallback
                 ↓
            HTML Parser (regex-based, no JavaScript evaluation needed)
                 ↓
            Structured JSON → Apify Dataset → JSON / CSV / XLSX
```

- **Cloudflare resilient:** httpx → Playwright automatic fallback handles most anti-bot measures
- **Polite scraping:** 15-second crawl delay respects robots.txt
- **Batch support:** Comma-separated keywords scrape in a single run

---

## ⚙️ Input Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `searchKeyword` | string | — | Keyword(s) — comma-separated for batch search |
| `maxPages` | int | 3 | Max pages per keyword (~20 items/page) |
| `inStockOnly` | bool | false | Only return in-stock items |
| `maxResults` | int | 50 | Max items per keyword |
| `proxyConfiguration` | proxy | JP | **Japan proxy required** (Suruga-ya blocks non-JP IPs) |

---

## ⚠️ Requirements & Limitations

- **Japan residential proxy is strongly recommended** — Suruga-ya blocks non-Japanese IPs
- **Cloudflare protection:** Occasional blocks are handled by automatic Playwright fallback
- **~20 items per page** — pagination is required for full results
- **15-second crawl delay** between requests (polite scraping policy)

---

## 🔧 Development / Self-Host

```bash
pip install httpx playwright
python3 -m playwright install firefox

# Single keyword
python3 src/scraper.py "ポケモン"

# In stock only, 3 pages
python3 src/scraper.py "フィギュア" --pages 3 --in-stock

# Save to custom file
python3 src/scraper.py "ガンダム" --output gundam.json

# Deploy to Apify
npx apify push
```

---

## 📝 License

MIT — free for commercial and personal use. Please respect Suruga-ya's terms of service and robots.txt when running at scale.

---

*Built for resellers, collectors, and market analysts who need reliable Japanese second-hand pricing data.*
