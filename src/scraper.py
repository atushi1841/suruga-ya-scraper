"""
Suruga-ya (駿河屋) Scraper v4 — Production Ready
Extracts: name, used/new/list price, brand, release date, stock, image, category, condition badge
Strategy: httpx (with retry+backoff) → Playwright (Cloudflare fallback)
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import urllib.parse
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

DATA_DIR = Path(__file__).parent.parent / "data"
BASE_URL = "http://www.suruga-ya.jp"
SEARCH_URL = f"{BASE_URL}/search"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0"
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja-JP,ja;q=0.9,en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "TE": "trailers",
}

# robots.txt 準拠: 30秒以上の間隔
CRAWL_DELAY = 15
MAX_RETRIES = 2  # Suruga-ya blocks non-browser traffic; fast-fail to Playwright


def _price(text: str) -> int | None:
    m = re.search(r"[¥￥]\s*([\d,]+)", text)
    return int(m.group(1).replace(",", "")) if m else None


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class SurugaItem:
    name: str = ""
    url: str = ""
    used_price_jpy: int | None = None
    new_price_jpy: int | None = None
    list_price_jpy: int | None = None  # 定価（差別化ポイント）
    marketplace_price_jpy: int | None = None  # マケプレ価格
    brand: str = ""  # 出版社/ブランド（差別化ポイント）
    release_date: str = ""  # 発売日（差別化ポイント）
    category: str = ""
    condition_badge: str = ""  # 新入荷/限定 etc
    in_stock: bool = True
    image_url: str = ""
    scraped_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["scraped_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return d


# ── HTTP モード ──

def _fetch_page(keyword: str, page: int, proxy_url: str | None = None) -> tuple[str | None, bool]:
    """
    1ページ取得。
    Strategy: direct connection first (Apify DC IP), no proxy for httpx.
    If blocked, Playwright fallback will handle proxy.
    Returns: (html, used_playwright) — html=None if blocked permanently
    used_playwright=True means this page needed Playwright
    """
    url = f"{SEARCH_URL}?search_word={quote(keyword)}&page={page}"
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # Apify proxy is passed to Playwright only; httpx goes direct.
            # The Apify runtime sets HTTP_PROXY environment variable which httpx
            # picks up by default — disable that with trust_env=False.
            with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=30, trust_env=False) as client:
                resp = client.get(url)
                
                if resp.status_code == 200 and len(resp.content) > 1000:
                    html = resp.text
                    # Cloudflareチャレンジ判定
                    if "Just a moment" in html[:500] or "challenge-platform" in html:
                        print(f"  [CF] Cloudflare challenge on attempt {attempt}")
                        time.sleep(5 * attempt)
                        continue
                    return html, False
                
                if resp.status_code in (403, 429):
                    print(f"  [HTTP {resp.status_code}] ブロックされました (attempt {attempt})")
                    time.sleep(5 * attempt)
                    continue
                    
                if len(resp.content) == 0:
                    print(f"  [空レスポンス] Empty response (attempt {attempt})")
                    time.sleep(5 * attempt)
                    continue
                    
                print(f"  [HTTP {resp.status_code}] size={len(resp.content)} (attempt {attempt})")
                time.sleep(5 * attempt)
                
        except Exception as e:
            print(f"  [ERROR] {e} (attempt {attempt})")
            time.sleep(5 * attempt)
    
    return None, False


# ── HTML パーサー ──

def _parse_item_block(html_block: str) -> SurugaItem | None:
    """1つのitemブロックから全データを抽出"""
    item = SurugaItem()
    
    try:
        # 商品名
        nm = re.search(r'class="product-name"[^>]*>(.*?)</div>', html_block, re.DOTALL)
        if nm:
            name_content = nm.group(1)
            item.name = _clean(re.sub(r"<[^>]+>", " ", name_content))
            # ブランド抽出: [出版社名] パターンおよび出版社/発売元プレフィックス強化
            # 例: フィギュア王 334<br>フィギュア王<br>[ワールド・フォト・プレス]
            brand_match = re.search(r'\[([^\]]{2,40})\]\s*(?:$|</)', name_content, re.MULTILINE)
            if not brand_match:
                brand_match = re.search(r'\[([^\]]{2,40})\]', name_content.split("<br")[-1] if "<br" in name_content else "")
            if not brand_match:
                # 出版社, 発売元, ブランド キーワード＋値
                brand_match = re.search(
                    r'(?:出版社|発売元|ブランド)[：:]?\s*([^<]{2,40})',
                    name_content,
                )
            if brand_match:
                candidate = brand_match.group(1).strip()
                # Skip if it's a number (like "TMH-13" which is a model number)
                if not re.match(r'^[\dA-Z-]+$', candidate):
                    item.brand = candidate
            # 発売日
            date_m = re.search(r'発売日[：:](\d{4}/\d{1,2}/\d{1,2})', html_block)
            if not date_m:
                date_m = re.search(r'発売日[：:](\d{4}/\d{2}/\d{2})', html_block)
            if date_m:
                item.release_date = date_m.group(1)

        # 価格ブロック (item_price内)
        pr = re.search(r'class="item_price[^"]*"[^>]*>(.*?)</div>', html_block, re.DOTALL)
        if pr:
            price_html = pr.group(1)
            used_m = re.search(r'中古.*?([¥￥][\d,]+)', price_html)
            if used_m:
                item.used_price_jpy = _price(used_m.group(1))
            else:
                fallback = re.search(r'([¥￥][\d,]+)', price_html)
                if fallback:
                    item.used_price_jpy = _price(fallback.group(1))
                    
            new_m = re.search(r'新品.*?([¥￥][\d,]+)', price_html)
            if new_m:
                item.new_price_jpy = _price(new_m.group(1))
                
            market_m = re.search(r'マケプレ.*?([¥￥][\d,]+)', price_html)
            if market_m:
                item.marketplace_price_jpy = _price(market_m.group(1))

        # 定価 (price_teika - item_priceの外にある)
        list_m = re.search(r'class="price_teika"[^>]*>定価[：:]\s*([¥￥][\d,]+)', html_block)
        if list_m:
            item.list_price_jpy = _price(list_m.group(1))

        # 画像
        im = re.search(r'<img[^>]*src="(https://[^"]+)"', html_block)
        if im and "logo" not in im.group(1).lower():
            item.image_url = im.group(1)

        # URL
        ln = re.search(r'href="(https?://[^"]+/product/[^"]+)"', html_block)
        if ln:
            item.url = ln.group(1)

        # 在庫
        if "品切" in html_block or "売切" in html_block:
            item.in_stock = False

        # コンディションバッジ
        cond_m = re.search(r'class="condition[^"]*"[^>]*>([^<]+)', html_block)
        if cond_m:
            item.condition_badge = cond_m.group(1).strip()
            # Clean up whitespace-only badges
            if not item.condition_badge.strip() or item.condition_badge == "&nbsp;":
                item.condition_badge = ""

        # カテゴリ (ページ上部のパンくずから)
        cat_m = re.search(r'class="breadcrumb"[^>]*>.*?<a[^>]*>([^<]+)', html_block, re.DOTALL)
        if cat_m:
            item.category = _clean(cat_m.group(1))

    except Exception:
        pass

    if item.name or item.used_price_jpy or item.new_price_jpy:
        return item
    return None


def _parse_html(html: str) -> list[SurugaItem]:
    """完全なHTMLから全商品を抽出"""
    results: list[SurugaItem] = []

    # item_box分割（各boxに複数item）
    boxes = re.split(r'<div\s+class="[^"]*item_box[^"]*">', html)[1:]
    
    for box in boxes:
        # item分割
        items_html = re.findall(r'<div\s+class="item"[^>]*>.*?</div>\s*</div>', box, re.DOTALL)
        
        for item_html in items_html:
            item = _parse_item_block(item_html)
            if item:
                results.append(item)

        # itemなし → product-name直接検索
        if not items_html:
            names = re.findall(r'class="product-name"[^>]*>(.*?)</div>', box, re.DOTALL)
            prices = re.findall(r'class="item_price[^"]*"[^>]*>(.*?)</div>', box, re.DOTALL)
            for i in range(max(len(names), len(prices))):
                name_html = names[i] if i < len(names) else ""
                price_html = prices[i] if i < len(prices) else ""
                # Reconstruct a minimal block for parsing
                block = f"<div class='item'>{name_html}{price_html}</div>"
                item = _parse_item_block(block)
                if item:
                    results.append(item)

    return results


def _has_next_page(html: str) -> bool:
    return 'rel="next"' in html


# ── Playwright フォールバック ──

async def _fetch_with_playwright_async(keyword: str, max_pages: int, proxy_url: str | None = None) -> list[SurugaItem]:
    """httpxがブロックされた場合のPlaywrightフォールバック (Async version)"""
    import asyncio
    print("  [PW] Switching to Playwright (Async)...")

    # Skip Scrapling StealthyFetcher in async (Apify) mode — uses Playwright Sync API.
    try:
        # Check if we're in an async loop (Apify mode)
        asyncio.get_running_loop()
        in_async = True
    except RuntimeError:
        in_async = False

    all_items: list[SurugaItem] = []

    if not in_async:
        # Sync mode: try Scrapling StealthyFetcher first (best Cloudflare bypass)
        try:
            from scrapling.fetchers import StealthyFetcher
            print("  [SC] Trying StealthyFetcher (Camoufox)...")
            all_items: list[SurugaItem] = []

            for p in range(1, max_pages + 1):
                url = f"{SEARCH_URL}?search_word={quote(keyword)}&page={p}"
                print(f"  [SC PAGE {p}]")

                page = StealthyFetcher.fetch(
                    url,
                    headless=True,
                    network_idle=False,
                    timeout=120,
                )

                if page is None:
                    print("  [SC] Failed to fetch page")
                    break

                # Get HTML content
                html = page.content if hasattr(page, 'content') else str(page)
                if not html or len(html) < 500:
                    print("  [SC] Empty or too small response")
                    break

                # Check for Cloudflare
                if "Just a moment" in html[:500] or "しばらくお待ち" in html[:500]:
                    print("  [SC] Still blocked by Cloudflare")
                    break

                print(f"  [SC OK] {len(html)} bytes")
                items = _parse_html(html)
                print(f"  [SC] {len(items)} items found")
                all_items.extend(items)

                # Check for next page (simple heuristic)
                if 'rel="next"' not in html:
                    break

                await asyncio.sleep(2)

            if all_items:
                return all_items

        except ImportError:
            print("  [SC] scrapling not installed, falling back to Playwright")
        except Exception as e:
            print(f"  [SC] Error: {e}, falling back to Playwright")

    # Fall back to regular Playwright Async
    print("  [PW] Fallback to regular Playwright (Async)...")
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("  [ERROR] playwright not installed")
        return []

    all_items = []

    # Parse Apify proxy URL for Playwright
    pw_proxy = None
    # Use Apify ACTOR proxy (included with all plans) for Playwright.
    # HTTP target avoids HTTPS CONNECT tunnel issues with the proxy.
    if proxy_url:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(str(proxy_url))
            pw_proxy = {
                "server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}",
                "username": parsed.username or "",
                "password": parsed.password or "",
            }
            print(f"  [PW] ACTOR proxy ({parsed.username[:20]}...)")
        except Exception as e:
            print(f"  [PW] proxy error: {e}")

    async with async_playwright() as pw:
        browser_kwargs = {"headless": True}
        browser = await pw.chromium.launch(
            **browser_kwargs,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=ChromeWhatsNewUI",
                "--no-default-browser-check",
                "--disable-component-update",
            ],
        )
        context_kwargs = {
            "user_agent": UA,
            "locale": "ja-JP",
            "timezone_id": "Asia/Tokyo",
            "viewport": {"width": 1920, "height": 1080},
        }
        if pw_proxy:
            context_kwargs["proxy"] = pw_proxy
        context = await browser.new_context(**context_kwargs)
        # Stealth: override webdriver detection
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['ja-JP', 'ja']});
            window.chrome = {runtime: {}};
        """)
        page = await context.new_page()
        page.set_default_timeout(90000)

        try:
            for p in range(1, max_pages + 1):
                url = f"{SEARCH_URL}?search_word={quote(keyword)}&page={p}"
                print(f"  [PW PAGE {p}]")

                try:
                    await page.goto(url, wait_until="networkidle", timeout=120000)
                except Exception as e:
                    print(f"  [PW ERROR] goto: {e}")
                    # Try once more with domcontentloaded if networkidle fails
                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    except Exception as e2:
                        print(f"  [PW ERROR] retry: {e2}")
                        break

                # Cloudflare待機（英語＋日本語対応）
                for _ in range(60):  # 最大120秒（2秒×60）
                    t = await page.title()
                    if "Just a moment" in t or "しばらくお待ち" in t or "challenge" in t.lower():
                        await asyncio.sleep(2)
                    else:
                        break

                if "Just a moment" in await page.title():
                    print("  [PW] Cloudflare bypass failed")
                    break

                html = await page.content()
                # Debug: print first 500 chars of HTML to understand structure
                print(f"  [PW HTML] title={(await page.title())[:80]}, len={len(html)}, sample={html[:300]}")
                items = _parse_html(html)
                if not items:
                    print("  [PW] No items")
                    break

                print(f"  [PW OK] {len(items)} items")
                all_items.extend(items)

                if not await page.query_selector("a[rel='next']"):
                    break

                await asyncio.sleep(2)

        finally:
            await browser.close()

    return all_items


def _fetch_with_playwright(keyword: str, max_pages: int, proxy_url: str | None = None) -> list[SurugaItem]:
    """httpxがブロックされた場合のPlaywrightフォールバック (sync wrapper).
    
    Uses existing event loop if running in async context (Apify mode),
    otherwise creates a new loop."""
    try:
        loop = asyncio.get_running_loop()
        # Inside an async context (Apify mode) — use run_coroutine_threadsafe
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                lambda: asyncio.run(_fetch_with_playwright_async(keyword, max_pages, proxy_url))
            )
            return future.result()
    except RuntimeError:
        # No running loop (standalone mode) — create a new loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_fetch_with_playwright_async(keyword, max_pages, proxy_url))
        finally:
            loop.close()


# ── メイン ──

def scrape(
    keyword: str,
    max_pages: int = 3,
    in_stock_only: bool = False,
    proxy: str | None = None,
    output: str = "suruga_results.json",
) -> Path | None:
    """メインエントリポイント"""
    print(f"🔍 Suruga-ya Scraper v4 — '{keyword}' (max {max_pages} pages)")
    
    all_items: list[SurugaItem] = []
    last_fetch_time = 0.0

    # HTTPモード
    for page in range(1, max_pages + 1):
        # Crawl-delay遵守
        elapsed = time.time() - last_fetch_time
        if elapsed < CRAWL_DELAY:
            wait = CRAWL_DELAY - elapsed
            print(f"  [RATE] Waiting {wait:.0f}s (crawl-delay)")
            time.sleep(wait)

        html, used_pw = _fetch_page(keyword, page, proxy_url=proxy)
        last_fetch_time = time.time()

        if html is None:
            print("  → HTTP blocked, switching to Playwright...")
            pw_items = _fetch_with_playwright(keyword, max_pages - page + 1, proxy_url=proxy)
            all_items.extend(pw_items)
            break

        items = _parse_html(html)
        if not items:
            print("  [END] No items")
            break

        print(f"  [OK] {len(items)} items")
        all_items.extend(items)

        if not _has_next_page(html):
            print("  [END] Last page")
            break

    if in_stock_only:
        all_items = [i for i in all_items if i.in_stock]

    if not all_items:
        print("\n❌ No items scraped")
        return None

    # 保存
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / output
    data = {
        "source": "suruga-ya.jp",
        "keyword": keyword,
        "count": len(all_items),
        "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "items": [i.to_dict() for i in all_items],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # サマリー
    used_prices = [i.used_price_jpy for i in all_items if i.used_price_jpy]
    new_prices = [i.new_price_jpy for i in all_items if i.new_price_jpy]
    list_prices = [i.list_price_jpy for i in all_items if i.list_price_jpy]
    in_stock_count = sum(1 for i in all_items if i.in_stock)
    with_brand = sum(1 for i in all_items if i.brand)
    with_date = sum(1 for i in all_items if i.release_date)

    print(f"\n✅ Saved: {path}")
    print(f"📊 Summary: {len(all_items)} items ({in_stock_count} in stock)")
    if used_prices:
        print(f"   Used:  ¥{min(used_prices):,} ~ ¥{max(used_prices):,} (avg ¥{sum(used_prices)//len(used_prices):,})")
    if new_prices:
        print(f"   New:   ¥{min(new_prices):,} ~ ¥{max(new_prices):,}")
    if list_prices:
        print(f"   List:  ¥{min(list_prices):,} ~ ¥{max(list_prices):,}")
    if with_brand:
        print(f"   Brand: {with_brand}/{len(all_items)} items")
    if with_date:
        print(f"   Date:  {with_date}/{len(all_items)} items")

    return path


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Suruga-ya Scraper v4")
    parser.add_argument("keyword", help="Search keyword")
    parser.add_argument("--pages", type=int, default=2, help="Max pages")
    parser.add_argument("--in-stock", action="store_true", help="In stock only")
    parser.add_argument("--output", default="suruga_results.json")
    args = parser.parse_args()
    scrape(args.keyword, args.pages, args.in_stock, output=args.output)


if __name__ == "__main__":
    main()
