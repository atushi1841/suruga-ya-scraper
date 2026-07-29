"""
Apify用エントリーポイント — Suruga-ya Scraper
Apifyプラットフォーム上でこのスクリプトが実行される。
"""

from __future__ import annotations

import sys
from pathlib import Path

# srcをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from scraper import scrape as suruga_scrape


def main() -> None:
    """Apify用メイン関数。環境変数or標準入力から設定を読み込む。"""
    try:
        from apify import Actor
        import asyncio
    except ImportError:
        # ローカル実行: コマンドライン引数から
        import argparse
        parser = argparse.ArgumentParser(description="Suruga-ya Scraper (Apify)")
        parser.add_argument("keyword", help="検索キーワード")
        parser.add_argument("--pages", type=int, default=2)
        parser.add_argument("--in-stock", action="store_true")
        parser.add_argument("--output", default="suruga_results.json")
        args = parser.parse_args()
        suruga_scrape(args.keyword, args.pages, args.in_stock, output=args.output)
        return

    # Apify環境での実行
    async def run_actor():
        async with Actor:
            # 入力読み込み
            actor_input = await Actor.get_input() or {}
            keyword_raw = actor_input.get("searchKeyword", "")
            keywords = [k.strip() for k in keyword_raw.split(",") if k.strip()]
            max_pages = actor_input.get("maxPages", 2)
            in_stock_only = actor_input.get("inStockOnly", False)
            max_results = int(actor_input.get("maxResults", 50))
            if max_results < 1:
                max_results = 1

            if not keywords:
                Actor.log.error("searchKeyword is required")
                return

            # Proxy configuration
            proxy_url = None
            try:
                proxy_input = actor_input.get("proxyConfiguration")
                if proxy_input and proxy_input.get("useApifyProxy", False):
                    import os
                    pwd = os.environ.get("APIFY_PROXY_PASSWORD")
                    if pwd:
                        host = "proxy.apify.com"
                        proxy_url = f"http://groups-auto:{pwd}@{host}:8000"
                        Actor.log.info(f"Using Apify proxy: {host}")
                    else:
                        Actor.log.warning("APIFY_PROXY_PASSWORD not set")
            except Exception as e:
                Actor.log.warning(f"Proxy config failed: {e}")

            all_items: list[dict] = []
            total_files = len(keywords)

            for idx, kw in enumerate(keywords, 1):
                Actor.log.info(f"[{idx}/{total_files}] Scraping keyword: {kw}")

                # 各キーワードごとにスクレイピング実行
                result_path = suruga_scrape(
                    kw,
                    max_pages=max_pages,
                    in_stock_only=in_stock_only,
                    proxy=proxy_url,
                    output=f"suruga_{kw}.json",
                )

                if result_path:
                    import json
                    with open(result_path) as f:
                        data = json.load(f)
                    items_batch = data.get("items", [])
                    Actor.log.info(f"   → {len(items_batch)} items for '{kw}'")
                    all_items.extend(items_batch)
                else:
                    Actor.log.warning(f"   → No data for '{kw}'")

            # 全キーワードの結果を一つのデータセットに統合
            items = all_items[:max_results]
            for item in items:
                await Actor.push_data(item)
            Actor.log.info(f"Pushed {len(items)} items to dataset (total {len(all_items)}, max {max_results})")
            await Actor.set_status_message(f"Returned {len(items)} items (max: {max_results})")

    asyncio.run(run_actor())


if __name__ == "__main__":
    main()
