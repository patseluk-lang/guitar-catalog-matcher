"""SQLite storage: shops, products, price history, features, runs and errors."""
import sqlite3
from datetime import datetime
from pathlib import Path

from catalog_matcher.models import Product

SCHEMA = """
CREATE TABLE IF NOT EXISTS shops (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS products (
    id         INTEGER PRIMARY KEY,
    shop_id    INTEGER NOT NULL REFERENCES shops(id),
    url        TEXT NOT NULL UNIQUE,
    name       TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scraping_runs (
    id             INTEGER PRIMARY KEY,
    started_at     TEXT NOT NULL,
    finished_at    TEXT,
    shops          TEXT NOT NULL,
    products_count INTEGER
);

CREATE TABLE IF NOT EXISTS price_history (
    id           INTEGER PRIMARY KEY,
    product_id   INTEGER NOT NULL REFERENCES products(id),
    run_id       INTEGER NOT NULL REFERENCES scraping_runs(id),
    price        INTEGER,
    old_price    INTEGER,
    currency     TEXT NOT NULL,
    availability TEXT NOT NULL,
    collected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS features (
    product_id INTEGER NOT NULL REFERENCES products(id),
    label      TEXT NOT NULL,
    value      TEXT NOT NULL,
    PRIMARY KEY (product_id, label)
);

CREATE TABLE IF NOT EXISTS errors (
    id         INTEGER PRIMARY KEY,
    run_id     INTEGER REFERENCES scraping_runs(id),
    shop       TEXT,
    message    TEXT NOT NULL,
    screenshot TEXT,
    created_at TEXT NOT NULL
);
"""

TABLES = ("shops", "products", "scraping_runs", "price_history", "features", "errors")


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str | Path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path))
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(SCHEMA)

    def close(self) -> None:
        self.connection.close()

    def start_run(self, shops: list[str]) -> int:
        with self.connection:
            cursor = self.connection.execute(
                "INSERT INTO scraping_runs (started_at, shops) VALUES (?, ?)",
                (now(), ",".join(shops)),
            )
        return cursor.lastrowid

    def finish_run(self, run_id: int, products_count: int) -> None:
        with self.connection:
            self.connection.execute(
                "UPDATE scraping_runs SET finished_at = ?, products_count = ? WHERE id = ?",
                (now(), products_count, run_id),
            )

    def save_products(self, run_id: int, products: list[Product]) -> None:
        """Upsert products by URL, append a price_history row, upsert features."""
        with self.connection:
            for product in products:
                shop_id = self._shop_id(product.shop)
                seen = product.collected_at.isoformat(timespec="seconds")
                self.connection.execute(
                    """
                    INSERT INTO products (shop_id, url, name, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(url) DO UPDATE SET name = excluded.name, last_seen = excluded.last_seen
                    """,
                    (shop_id, product.url, product.name, seen, seen),
                )
                product_id = self.connection.execute(
                    "SELECT id FROM products WHERE url = ?", (product.url,)
                ).fetchone()[0]
                self.connection.execute(
                    """
                    INSERT INTO price_history
                        (product_id, run_id, price, old_price, currency, availability, collected_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (product_id, run_id, product.price, product.old_price,
                     product.currency, product.availability, seen),
                )
                for label, value in product.features.items():
                    self.connection.execute(
                        """
                        INSERT INTO features (product_id, label, value) VALUES (?, ?, ?)
                        ON CONFLICT(product_id, label) DO UPDATE SET value = excluded.value
                        """,
                        (product_id, label, value),
                    )

    def urls_with_features(self, shop: str) -> set[str]:
        """URLs of this shop's products whose characteristics are already stored."""
        rows = self.connection.execute(
            """
            SELECT p.url
            FROM products p
            JOIN shops s ON s.id = p.shop_id
            WHERE s.name = ?
              AND EXISTS (SELECT 1 FROM features f WHERE f.product_id = p.id)
            """,
            (shop,),
        ).fetchall()
        return {row[0] for row in rows}

    def log_error(self, run_id: int | None, shop: str | None, message: str,
                  screenshot: str | None = None) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO errors (run_id, shop, message, screenshot, created_at) VALUES (?, ?, ?, ?, ?)",
                (run_id, shop, message, screenshot, now()),
            )

    def counts(self) -> dict[str, int]:
        return {
            table: self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in TABLES
        }

    def _shop_id(self, name: str) -> int:
        self.connection.execute("INSERT OR IGNORE INTO shops (name) VALUES (?)", (name,))
        return self.connection.execute("SELECT id FROM shops WHERE name = ?", (name,)).fetchone()[0]