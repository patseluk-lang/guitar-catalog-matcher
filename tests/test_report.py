"""Reports: price changes between runs, one group key per guitar, CSV for Excel."""
import csv
from datetime import datetime

import pytest

from catalog_matcher.database import Database
from catalog_matcher.matcher import build_groups, load_offers
from catalog_matcher.models import Product
from catalog_matcher.report import LATEST, PRICE_CHANGES, group_keys, price_changes_section, write_csv


def item(shop, name, url, price, old_price=None, **features):
    return Product(shop=shop, name=name, url=url, price=price, old_price=old_price,
                   availability="В наявності", features=dict(features),
                   collected_at=datetime(2026, 9, 26, 10, 0))


@pytest.fixture
def db():
    database = Database(":memory:")
    first = database.start_run(["jam", "muzikant"])
    database.save_products(first, [
        item("jam", "Yamaha FG820 (Sunset Blue)", "https://jam/fg820", 22011, Артикул="33545"),
        item("muzikant", "Yamaha FG820 SB", "https://muzikant/fg820", 22011),
        item("muzikant", "Cort AD810 OP", "https://muzikant/ad810", 5499),
    ])
    second = database.start_run(["jam", "muzikant"])
    database.save_products(second, [
        item("jam", "Yamaha FG820 (Sunset Blue)", "https://jam/fg820", 20999, old_price=22011),
        item("muzikant", "Yamaha FG820 SB", "https://muzikant/fg820", 22011),
        item("muzikant", "Cort AD810 OP", "https://muzikant/ad810", 5699),
    ])
    yield database
    database.close()


def test_price_changes_between_last_two_runs(db):
    rows = db.connection.execute(PRICE_CHANGES).fetchall()
    changes = {name: (before, now) for _, name, _, before, now, _ in rows}
    assert changes == {
        "Yamaha FG820 (Sunset Blue)": (22011, 20999),  # drop
        "Cort AD810 OP": (5499, 5699),  # rise
    }


def test_price_drop_is_marked(db):
    section = price_changes_section(db.connection)
    assert section.count("price drop") == 1
    assert section.count("price rise") == 1


def test_csv_has_one_group_key_per_guitar(db, tmp_path):
    offers = load_offers(db.connection)
    latest = {row[0]: (row[1], row[2]) for row in db.connection.execute(LATEST)}
    _, members = build_groups(offers)
    path = tmp_path / "offers.csv"

    write_csv(path, offers, group_keys(members), latest)

    with path.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file, delimiter=";"))
    groups = {row["url"]: row["group"] for row in rows}
    assert groups["https://jam/fg820"] == groups["https://muzikant/fg820"]
    assert groups["https://muzikant/ad810"] != groups["https://jam/fg820"]
    fg820_jam = next(row for row in rows if row["url"] == "https://jam/fg820")
    assert (fg820_jam["price"], fg820_jam["old_price"]) == ("20999", "22011")
