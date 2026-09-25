"""Match the same guitar across shops. Level 1: identical shop code ("Артикул")."""
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

DB_PATH = Path("data") / "catalog.db"

LATEST_OFFERS = """
SELECT s.name, p.name, p.url, f.value,
       (SELECT h.price FROM price_history h WHERE h.product_id = p.id ORDER BY h.id DESC LIMIT 1)
FROM products p
JOIN shops s ON s.id = p.shop_id
JOIN features f ON f.product_id = p.id AND f.label = 'Артикул'
"""


@dataclass
class Offer:
    shop: str
    name: str
    url: str
    code: str
    price: int | None


def load_offers(connection: sqlite3.Connection) -> list[Offer]:
    return [Offer(*row) for row in connection.execute(LATEST_OFFERS)]


def match_by_code(offers: list[Offer]) -> dict[str, list[Offer]]:
    """Group offers by shop code; keep only codes present in two or more shops."""
    groups: dict[str, list[Offer]] = {}
    for offer in offers:
        groups.setdefault(offer.code, []).append(offer)
    return {
        code: sorted(items, key=lambda offer: offer.shop)
        for code, items in groups.items()
        if len({offer.shop for offer in items}) >= 2
    }


def print_groups(groups: dict[str, list[Offer]]) -> None:
    for code, items in sorted(groups.items(), key=lambda pair: pair[1][0].name):
        prices = {offer.price for offer in items}
        mark = "same price" if len(prices) == 1 else "PRICE DIFFERS"
        print(f"\n[{code}] {items[0].name}  ({mark})")
        for offer in items:
            print(f"    {offer.shop:<12} {offer.price!s:>7}  {offer.url}")
    print(f"\nGroups matched by code: {len(groups)}")


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DB_PATH
    connection = sqlite3.connect(str(path))
    try:
        print_groups(match_by_code(load_offers(connection)))
    finally:
        connection.close()


if __name__ == "__main__":
    main()