"""SQLite storage: one product per URL, a price row per run, features updated in place."""
from datetime import datetime

import pytest

from catalog_matcher.database import Database
from catalog_matcher.models import Product


@pytest.fixture
def db():
    database = Database(":memory:")
    yield database
    database.close()


def guitar(price, **features):
    return Product(
        shop="jam",
        name="Yamaha FG820 (Sunset Blue)",
        url="https://jam.ua/yamaha-guitar-fg820-sb",
        price=price,
        features=dict(features),
        collected_at=datetime(2026, 9, 26, 10, 0),
    )


def test_second_run_adds_price_row_not_product(db):
    first_run = db.start_run(["jam"])
    db.save_products(first_run, [guitar(22011, Артикул="33545")])
    second_run = db.start_run(["jam"])
    db.save_products(second_run, [guitar(20999, Артикул="33545")])

    counts = db.counts()
    assert counts["shops"] == 1
    assert counts["products"] == 1
    assert counts["price_history"] == 2
    assert counts["features"] == 1
    prices = db.connection.execute("SELECT run_id, price FROM price_history ORDER BY id").fetchall()
    assert prices == [(first_run, 22011), (second_run, 20999)]


def test_feature_value_is_updated(db):
    run = db.start_run(["jam"])
    db.save_products(run, [guitar(22011, Бридж="Горіх")])
    db.save_products(run, [guitar(22011, Бридж="Палісандр")])

    rows = db.connection.execute("SELECT label, value FROM features").fetchall()
    assert rows == [("Бридж", "Палісандр")]


def test_urls_with_features_only_for_that_shop(db):
    run = db.start_run(["jam"])
    without_features = Product(shop="jam", name="Cort AD810", url="https://jam.ua/cort", price=5499)
    db.save_products(run, [guitar(22011, Артикул="33545"), without_features])

    assert db.urls_with_features("jam") == {"https://jam.ua/yamaha-guitar-fg820-sb"}
    assert db.urls_with_features("muzikant") == set()


def test_run_and_error_are_recorded(db):
    run = db.start_run(["jam", "muzikant"])
    db.log_error(run, "jam", "Catalogue did not load: TimeoutException", "screenshots/jam.png")
    db.finish_run(run, 0)

    started, finished, shops, count = db.connection.execute(
        "SELECT started_at, finished_at, shops, products_count FROM scraping_runs"
    ).fetchone()
    assert shops == "jam,muzikant"
    assert finished >= started
    assert count == 0
    assert db.connection.execute("SELECT shop, message FROM errors").fetchall() == [
        ("jam", "Catalogue did not load: TimeoutException")
    ]
