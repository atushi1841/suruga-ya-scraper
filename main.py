"""
Suruga-ya Apify Actor — root entry point
"""
import sys, json, os, asyncio
from pathlib import Path

# Add src to path
SRC_DIR = str(Path(__file__).parent / "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

# Set working directory to project root
os.chdir(Path(__file__).parent)

try:
    from apify import Actor
    from scraper import scrape as suruga_scrape

    async def run_actor():
        async with Actor:
            inp = await Actor.get_input() or {}
            keywords = [k.strip() for k in inp.get("searchKeyword", "").split(",") if k.strip()]
            if not keywords:
                Actor.log.error("searchKeyword is required")
                return
            max_pages = inp.get("maxPages", 3)
            in_stock = inp.get("inStockOnly", False)
            max_results = int(inp.get("maxResults", 50))
            if max_results < 1: max_results = 1

            proxy_url = None
            try:
                pc = await Actor.create_proxy_configuration(actor_input=inp)
                if pc: proxy_url = pc.get_url()
            except:
                pass

            all_items = []
            for idx, kw in enumerate(keywords, 1):
                Actor.log.info(f"[{idx}/{len(keywords)}] Scraping: {kw}")
                rp = suruga_scrape(kw, max_pages=max_pages, in_stock_only=in_stock, proxy=proxy_url)
                if rp:
                    with open(rp) as f:
                        items = json.load(f).get("items", [])
                    Actor.log.info(f"  -> {len(items)} items")
                    all_items.extend(items)

            items = all_items[:max_results]
            for item in items:
                await Actor.push_data(item)
            Actor.log.info(f"Pushed {len(items)} items (max {max_results})")

    asyncio.run(run_actor())

except ImportError as e:
    # Local CLI mode
    from scraper import scrape as suruga_scrape
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("keyword", nargs="?", default="Fgure")
    parser.add_argument("--pages", type=int, default=3)
    parser.add_argument("--in-stock", action="store_true")
    parser.add_argument("--output", default="suruga_results.json")
    args = parser.parse_args()
    suruga_scrape(args.keyword, args.pages, args.in_stock, output=args.output)
except Exception as e:
    print(f"FATAL: {e}", file=sys.stderr)
    raise
