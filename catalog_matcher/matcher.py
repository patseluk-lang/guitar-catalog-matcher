"""Match the same guitar across shops.

Level 1: identical shop code ("Артикул").
Level 2: identical normalised name (brand + model + colour code).
"""
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

DB_PATH = Path("data") / "catalog.db"

LATEST_OFFERS = """
SELECT p.id, s.name, p.name, p.url, f.value,
       (SELECT h.price FROM price_history h WHERE h.product_id = p.id ORDER BY h.id DESC LIMIT 1)
FROM products p
JOIN shops s ON s.id = p.shop_id
LEFT JOIN features f ON f.product_id = p.id AND f.label = 'Артикул'
"""

# Words shops put in front of the model name.
PREFIXES = (
    "ЕЛЕКТРОАКУСТИЧНА ГІТАРА",
    "АКУСТИЧНА ГІТАРА",
    "ГІТАРА АКУСТИЧНА",
    "КЛАСИЧНА ГІТАРА",
)

# Colour / finish names -> one code. Longest phrases first.
# "SB" is deliberately absent: shops use it both for Sunburst and for Sunset Blue.
COLOURS = {
    "TOBACCO BROWN SUNBURST": "TBS",
    "TABACCO BROWN SUNBURST": "TBS",
    "SATIN SUNBURST": "SSB",
    "NATURAL SATIN": "NS",
    "NATURAL GLOSS": "NAT",
    "BLACK SATIN": "BKS",
    "BLACK GLOSS": "BK",
    "OPEN PORE": "OP",
    "AUTUMN BURST": "AB",
    "SUNSET BLUE": "SUNSETBLUE",
    "SMOKY BLACK": "SMB",
    "NATURAL": "NAT",
    "BLACK": "BK",
    "NT": "NAT",
    "BLK": "BK",
}


@dataclass
class Offer:
    product_id: int
    shop: str
    name: str
    url: str
    code: str | None
    price: int | None


def load_offers(connection: sqlite3.Connection) -> list[Offer]:
    return [Offer(*row) for row in connection.execute(LATEST_OFFERS)]


def name_key(name: str) -> str:
    """'Акустична гітара CORT AD810 (Open Pore)' and 'Cort AD810 OP' -> 'CORTAD810OP'."""
    text = name.upper()
    for prefix in PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    text = re.sub(r"[()\[\],]", " ", text)
    text = " ".join(text.split())
    for phrase, code in COLOURS.items():
        text = re.sub(rf"(?<![A-Z0-9]){phrase}(?![A-Z0-9])", code, text)
    return re.sub(r"[^A-Z0-9А-ЯІЇЄҐ]", "", text)


class Groups:
    """Union-find over offers; remembers which evidence joined them."""

    def __init__(self, offers: list[Offer]):
        self.parent = {offer.product_id: offer.product_id for offer in offers}
        self.evidence: dict[int, set[str]] = {offer.product_id: set() for offer in offers}

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def join(self, first: int, second: int, reason: str) -> None:
        root_a, root_b = self.find(first), self.find(second)
        if root_a != root_b:
            self.parent[root_b] = root_a
            self.evidence[root_a] |= self.evidence.pop(root_b)
        self.evidence[root_a].add(reason)


def link_by(offers: list[Offer], groups: Groups, key, reason: str) -> None:
    buckets: dict[str, list[Offer]] = {}
    for offer in offers:
        value = key(offer)
        if value:
            buckets.setdefault(value, []).append(offer)
    for items in buckets.values():
        for other in items[1:]:
            groups.join(items[0].product_id, other.product_id, reason)


def match(offers: list[Offer]) -> list[tuple[set[str], list[Offer]]]:
    """Return (evidence, offers) for every group that spans two or more shops."""
    groups = Groups(offers)
    link_by(offers, groups, lambda offer: offer.code, "code")
    link_by(offers, groups, lambda offer: name_key(offer.name), "name")

    members: dict[int, list[Offer]] = {}
    for offer in offers:
        members.setdefault(groups.find(offer.product_id), []).append(offer)
    result = []
    for root, items in members.items():
        if len({offer.shop for offer in items}) >= 2:
            result.append((groups.evidence[root], sorted(items, key=lambda offer: offer.shop)))
    return sorted(result, key=lambda pair: name_key(pair[1][0].name))


def print_groups(groups: list[tuple[set[str], list[Offer]]]) -> None:
    for evidence, items in groups:
        prices = {offer.price for offer in items}
        price_mark = "same price" if len(prices) == 1 else "PRICE DIFFERS"
        print(f"\n{name_key(items[0].name)}  [matched by: {', '.join(sorted(evidence))}]  ({price_mark})")
        for offer in items:
            print(f"    {offer.shop:<12} {offer.price!s:>7}  {offer.name}")
    shops_per_group = [len({offer.shop for offer in items}) for _, items in groups]
    print(f"\nGroups: {len(groups)}, of them in all three shops: {shops_per_group.count(3)}")


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DB_PATH
    connection = sqlite3.connect(str(path))
    try:
        print_groups(match(load_offers(connection)))
    finally:
        connection.close()


if __name__ == "__main__":
    main()