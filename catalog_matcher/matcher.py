"""Match the same guitar across shops.

Level 1: identical shop code ("Артикул")                         -> same guitar.
Level 2: identical normalised name (brand + model + colour code) -> same guitar.
Level 3: same brand and base model, different suffix/extra words -> for a human to decide.

Shop conventions:
- no colour in the name means Natural;
- a bare "SB" means Sunburst, except Yamaha, where SB is its code for Sunset Blue;
- "-12" after the model means 12 strings, otherwise 6.
"""
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

DB_PATH = Path("data") / "catalog.db"

OFFERS = """
SELECT p.id, s.name, p.name, p.url,
       (SELECT h.price FROM price_history h WHERE h.product_id = p.id ORDER BY h.id DESC LIMIT 1)
FROM products p
JOIN shops s ON s.id = p.shop_id
"""
FEATURES = "SELECT product_id, label, value FROM features"

# Words shops put in front of the model name.
PREFIXES = (
    "ЕЛЕКТРОАКУСТИЧНА ГІТАРА",
    "АКУСТИЧНА ГІТАРА",
    "ГІТАРА АКУСТИЧНА",
    "КЛАСИЧНА ГІТАРА",
)

# Colour / finish names -> one code. Longest phrases first.
# A bare "SB" stays "SB" here: name_key reads it through DEFAULT_COLOUR / BRAND_COLOUR.
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
    "SUNBURST": "SUNBURST",
    "NATURAL": "NAT",
    "BLACK": "BK",
    "NT": "NAT",
    "BLK": "BK",
}
# Default meaning of a bare abbreviation (used for automatic matching).
DEFAULT_COLOUR = {"SB": "SUNBURST"}
# Manufacturer's own colour codes that override the default.
BRAND_COLOUR = {"YAMAHA": {"SB": "SUNSETBLUE"}}
# Other colours the same abbreviation is sometimes used for (shown to a human, level 3).
AMBIGUOUS = {"SB": {"SUNSETBLUE", "SMB"}}
# Natural is the default colour, so it is not part of the name.
DEFAULT_TOKENS = {"NAT"}

# Characteristics shown next to level 3 candidates.
SHOWN_FEATURES = ("Верхня дека", "Нижня дека", "Накладка грифа", "Гриф")


@dataclass
class Offer:
    product_id: int
    shop: str
    name: str
    url: str
    price: int | None
    features: dict[str, str] = field(default_factory=dict)

    @property
    def code(self) -> str | None:
        return self.features.get("Артикул")


def load_offers(connection: sqlite3.Connection) -> list[Offer]:
    offers = {row[0]: Offer(*row) for row in connection.execute(OFFERS)}
    for product_id, label, value in connection.execute(FEATURES):
        if product_id in offers:
            offers[product_id].features[label] = value
    return list(offers.values())


def name_tokens(name: str) -> list[str]:
    """'Акустична гітара CORT AD810 (Open Pore)' -> ['CORT', 'AD810', 'OP']
    'YAMAHA F310 Natural' -> ['YAMAHA', 'F310'] (Natural is the default colour)"""
    text = name.upper()
    for prefix in PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    text = re.sub(r"[()\[\],]", " ", text)
    text = " ".join(text.split())
    for phrase, code in COLOURS.items():
        text = re.sub(rf"(?<![A-Z0-9]){phrase}(?![A-Z0-9])", code, text)
    return [token for token in text.split() if token not in DEFAULT_TOKENS]


def name_key(name: str) -> str:
    """'Акустична гітара CORT AD810 (Open Pore)' and 'Cort AD810 OP' -> 'CORTAD810OP'.
    'Maxtone WGC4010 SB' and 'Maxtone WGC4010 Sunburst' -> 'MAXTONEWGC4010SUNBURST'.
    'Yamaha FG820 SB' and 'Yamaha FG820 (Sunset Blue)' -> 'YAMAHAFG820SUNSETBLUE'."""
    tokens = name_tokens(name)
    colours = {**DEFAULT_COLOUR, **BRAND_COLOUR.get(tokens[0] if tokens else "", {})}
    tokens = [colours.get(token, token) for token in tokens]
    return re.sub(r"[^A-Z0-9А-ЯІЇЄҐ]", "", "".join(tokens))


def string_count(name: str) -> int:
    """'Cort AD810-12 OP' -> 12, 'Cort AD810 OP' -> 6."""
    text = " ".join(name_tokens(name))
    twelve = re.search(r"\d-12(?!\d)|(?<![0-9])12[- ]?(?:STRING|STR|СТРУН)", text)
    return 12 if twelve else 6


def model_parts(name: str) -> tuple[str, str, frozenset[str]]:
    """Split a name into (brand + base model, model suffix, other words).

    'Cort AD810M OP'             -> ('CORT AD810', 'M', {'OP'})
    'Cort EARTH 60M (Open Pore)' -> ('CORT EARTH60', 'M', {'OP'})
    'Yamaha JR2S TBS'            -> ('YAMAHA JR2', 'S', {'TBS'})
    """
    tokens = name_tokens(name)
    if len(tokens) < 2:
        return " ".join(tokens), "", frozenset()
    brand, rest = tokens[0], tokens[1:]

    joined = re.fullmatch(r"([A-Z]+)-?(\d+)(.*)", rest[0])
    split = (
        re.fullmatch(r"[A-Z]+", rest[0]) and len(rest) > 1 and re.fullmatch(r"(\d+)(.*)", rest[1])
    )
    if joined:
        base, suffix, used = joined.group(1) + joined.group(2), joined.group(3), 1
    elif split:
        base, suffix, used = rest[0] + split.group(1), split.group(2), 2
    else:
        base, suffix, used = rest[0], "", 1

    def clean(text: str) -> str:
        return re.sub(r"[^A-Z0-9А-ЯІЇЄҐ]", "", text)

    others = frozenset(clean(token) for token in rest[used:]) - {""}
    return f"{brand} {clean(base)}", clean(suffix), others


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


def build_groups(offers: list[Offer]) -> tuple[Groups, dict[int, list[Offer]]]:
    groups = Groups(offers)
    link_by(offers, groups, lambda offer: offer.code, "code")
    link_by(offers, groups, lambda offer: name_key(offer.name), "name")
    members: dict[int, list[Offer]] = {}
    for offer in offers:
        members.setdefault(groups.find(offer.product_id), []).append(offer)
    return groups, members


def matched_groups(groups: Groups, members: dict[int, list[Offer]]):
    """Levels 1-2: groups spanning two or more shops."""
    result = [
        (groups.evidence[root], sorted(items, key=lambda offer: offer.shop))
        for root, items in members.items()
        if len({offer.shop for offer in items}) >= 2
    ]
    return sorted(result, key=lambda pair: name_key(pair[1][0].name))


COLOUR_CODES = set(COLOURS.values()) | set(DEFAULT_COLOUR)


def colour_of(others: frozenset[str]) -> frozenset[str]:
    """Colour words among the extra words; no colour means Natural.

    {'OP', 'W', 'BAG'} -> {'OP'};  {'W', 'BAG'} -> {'NAT'}
    """
    return (others & COLOUR_CODES) or frozenset({"NAT"})


def colours_compatible(others_a: frozenset[str], others_b: frozenset[str]) -> bool:
    """Could these two sets of extra words describe the same colour?

    Same colour (other words such as w/bag are ignored),
    or an abbreviation that is sometimes used for the other side's colour.
    """
    colour_a, colour_b = colour_of(others_a), colour_of(others_b)
    if colour_a == colour_b:
        return True
    for short, meanings in AMBIGUOUS.items():
        for one, other in ((colour_a, colour_b), (colour_b, colour_a)):
            if short in one and (one - {short}) == (other - meanings) and other & meanings:
                return True
    return False


def needs_human(first: Offer, second: Offer) -> bool:
    """Same brand + base model and compatible colour, but the names still differ.

    'AD810M OP' / 'AD810 OP'    -> True  (index differs, colour the same)
    'AD810M OP' / 'AD810 BKS'   -> False (different colour: simply another product)
    'AD810 OP'  / 'AD810-12 OP' -> False (6 and 12 strings: different guitars)
    'WGC4010 SB' / 'WGC4010 Sunset Blue' -> True (SB may be used for Sunset Blue)
    """
    if string_count(first.name) != string_count(second.name):
        return False
    _, suffix_a, others_a = model_parts(first.name)
    _, suffix_b, others_b = model_parts(second.name)
    if (suffix_a, others_a) == (suffix_b, others_b):
        return False
    return colours_compatible(others_a, others_b)


def candidates(members: dict[int, list[Offer]]) -> list[tuple[Offer, Offer]]:
    """Level 3: offers from different groups and shops sharing brand + base model,
    where no shop sells both of them side by side."""
    by_base: dict[str, list[tuple[int, Offer]]] = {}
    for root, items in members.items():
        for offer in items:
            by_base.setdefault(model_parts(offer.name)[0], []).append((root, offer))

    shops_of = {root: {offer.shop for offer in items} for root, items in members.items()}

    pairs, seen = [], set()
    for items in by_base.values():
        for i, (root_a, offer_a) in enumerate(items):
            for root_b, offer_b in items[i + 1:]:
                if root_a == root_b or offer_a.shop == offer_b.shop:
                    continue
                # If some shop sells both products side by side, they are different products.
                if shops_of[root_a] & shops_of[root_b]:
                    continue
                if not needs_human(offer_a, offer_b):
                    continue
                pair_key = tuple(sorted((root_a, root_b)))
                if pair_key in seen:
                    continue
                seen.add(pair_key)
                pairs.append(tuple(sorted((offer_a, offer_b), key=lambda offer: offer.shop)))
    return sorted(pairs, key=lambda pair: model_parts(pair[0].name)[0])


def print_groups(groups) -> None:
    print("=== Levels 1-2: same guitar ===")
    for evidence, items in groups:
        prices = {offer.price for offer in items}
        price_mark = "same price" if len(prices) == 1 else "PRICE DIFFERS"
        print(f"\n{name_key(items[0].name)}  [matched by: {', '.join(sorted(evidence))}]  ({price_mark})")
        for offer in items:
            print(f"    {offer.shop:<12} {offer.price!s:>7}  {offer.name}")
    shops_per_group = [len({offer.shop for offer in items}) for _, items in groups]
    print(f"\nGroups: {len(groups)}, of them in all three shops: {shops_per_group.count(3)}")


def print_candidates(pairs: list[tuple[Offer, Offer]]) -> None:
    print("\n=== Level 3: similar model, different index - decide manually ===")
    for first, second in pairs:
        print(f"\n{model_parts(first.name)[0]}")
        for offer in (first, second):
            shown = "; ".join(
                f"{label}: {offer.features[label]}" for label in SHOWN_FEATURES if label in offer.features
            )
            print(f"    {offer.shop:<12} {offer.price!s:>7}  {offer.name}")
            if shown:
                print(f"    {'':<12} {'':>7}  {shown}")
    print(f"\nCandidates for manual check: {len(pairs)}")


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DB_PATH
    connection = sqlite3.connect(str(path))
    try:
        offers = load_offers(connection)
    finally:
        connection.close()
    groups, members = build_groups(offers)
    print_groups(matched_groups(groups, members))
    print_candidates(candidates(members))


if __name__ == "__main__":
    main()