"""Command line entry point: collect guitars from the selected shops."""
import argparse
import logging
from pathlib import Path

from selenium import webdriver

from catalog_matcher.models import Product
from catalog_matcher.scrapers.jam import JamScraper
from catalog_matcher.scrapers.muzikant import MuzikantScraper

SCRAPERS = {scraper.shop: scraper for scraper in (MuzikantScraper, JamScraper)}
LOGS = Path("logs")
LOG_FORMAT = "[{asctime}] {levelname:<7} {name}: {message}"

log = logging.getLogger("app")


def setup_logging() -> None:
    """Console + logs/application.log (all), logs/scraper.log (scrapers), logs/errors.log (errors)."""
    LOGS.mkdir(exist_ok=True)
    formatter = logging.Formatter(LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S", style="{")

    console = logging.StreamHandler()
    application = logging.FileHandler(LOGS / "application.log", encoding="utf-8")
    scraper = logging.FileHandler(LOGS / "scraper.log", encoding="utf-8")
    scraper.addFilter(logging.Filter("scraper"))
    errors = logging.FileHandler(LOGS / "errors.log", encoding="utf-8")
    errors.setLevel(logging.ERROR)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in (console, application, scraper, errors):
        handler.setFormatter(formatter)
        root.addHandler(handler)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect guitars from Ukrainian music shops.")
    parser.add_argument(
        "--shops",
        nargs="+",
        choices=sorted(SCRAPERS),
        default=sorted(SCRAPERS),
        help="shops to scrape (default: all)",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=1,
        help="catalogue portions per shop: pages or 'show more' clicks (default: 1)",
    )
    return parser.parse_args()


def collect(shops: list[str], pages: int) -> list[Product]:
    products: list[Product] = []
    driver = webdriver.Chrome()
    try:
        for shop in shops:
            try:
                products.extend(SCRAPERS[shop](driver).collect(max_pages=pages))
            except Exception:  # one broken shop must not stop the others
                log.exception("Shop %s failed", shop)
    finally:
        driver.quit()
    return products


def print_summary(products: list[Product]) -> None:
    print()
    print(f"{'Shop':<12}{'Products':>10}{'No price':>10}{'Discounted':>12}")
    for shop in sorted({product.shop for product in products}):
        items = [product for product in products if product.shop == shop]
        no_price = sum(product.price is None for product in items)
        discounted = sum(product.old_price is not None for product in items)
        print(f"{shop:<12}{len(items):>10}{no_price:>10}{discounted:>12}")


def main() -> None:
    setup_logging()
    args = parse_args()
    log.info("Run started: shops=%s pages=%d", args.shops, args.pages)
    products = collect(args.shops, args.pages)
    log.info("Run finished: %d products", len(products))
    print_summary(products)


if __name__ == "__main__":
    main()