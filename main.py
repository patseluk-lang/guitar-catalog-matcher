"""Command line entry point: collect guitars from the selected shops into SQLite."""
import argparse
import logging
from pathlib import Path

from selenium import webdriver

from catalog_matcher.database import Database
from catalog_matcher.models import Product
from catalog_matcher.scrapers.jam import JamScraper
from catalog_matcher.scrapers.muzikant import MuzikantScraper

SCRAPERS = {scraper.shop: scraper for scraper in (MuzikantScraper, JamScraper)}
DB_PATH = Path("data") / "catalog.db"
LOGS = Path("logs")
LOG_FORMAT = "[{asctime}] {levelname:<7} {name}: {message}"

log = logging.getLogger("app")


class DatabaseErrorHandler(logging.Handler):
    """Copy every ERROR log record into the errors table of the current run."""

    def __init__(self, db: Database, run_id: int):
        super().__init__(level=logging.ERROR)
        self.db = db
        self.run_id = run_id

    def emit(self, record: logging.LogRecord) -> None:
        shop = record.name.split(".", 1)[1] if record.name.startswith("scraper.") else None
        try:
            self.db.log_error(self.run_id, shop, record.getMessage())
        except Exception:
            self.handleError(record)


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


def collect(db: Database, run_id: int, shops: list[str], pages: int) -> list[Product]:
    products: list[Product] = []
    driver = webdriver.Chrome()
    try:
        for shop in shops:
            try:
                scraper = SCRAPERS[shop](driver)
                shop_products = scraper.collect(
                    max_pages=pages,
                    known_detail_urls=db.urls_with_features(shop),
                )
            except Exception:  # one broken shop must not stop the others
                log.exception("Shop %s failed", shop)
                continue
            db.save_products(run_id, shop_products)
            log.info("Saved %d products from %s", len(shop_products), shop)
            products.extend(shop_products)
    finally:
        driver.quit()
    return products


def print_summary(products: list[Product], counts: dict[str, int]) -> None:
    print()
    print(f"{'Shop':<12}{'Products':>10}{'No price':>10}{'Discounted':>12}")
    for shop in sorted({product.shop for product in products}):
        items = [product for product in products if product.shop == shop]
        no_price = sum(product.price is None for product in items)
        discounted = sum(product.old_price is not None for product in items)
        print(f"{shop:<12}{len(items):>10}{no_price:>10}{discounted:>12}")
    print()
    print("Database rows: " + ", ".join(f"{table}={count}" for table, count in counts.items()))


def main() -> None:
    setup_logging()
    args = parse_args()
    db = Database(DB_PATH)
    run_id = db.start_run(args.shops)
    logging.getLogger().addHandler(DatabaseErrorHandler(db, run_id))
    log.info("Run %d started: shops=%s pages=%d", run_id, args.shops, args.pages)
    try:
        products = collect(db, run_id, args.shops, args.pages)
        db.finish_run(run_id, len(products))
        log.info("Run %d finished: %d products", run_id, len(products))
        print_summary(products, db.counts())
    finally:
        db.close()


if __name__ == "__main__":
    main()