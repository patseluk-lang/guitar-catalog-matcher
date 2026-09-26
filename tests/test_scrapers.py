"""Selenium integration tests: every scraper against small local copies of the shop markup.

No internet: the pages live in tests/pages and are opened as file:// URLs in headless Chrome.
Run only these:  pytest -m selenium
"""
import logging

import pytest
from selenium.webdriver.support.ui import WebDriverWait

from catalog_matcher.models import Product
from catalog_matcher.scrapers.dommuzyki import DommuzykiScraper
from catalog_matcher.scrapers.guitarhouse import GuitarHouseScraper
from catalog_matcher.scrapers.jam import JamScraper
from catalog_matcher.scrapers.muzikant import MuzikantScraper
from tests.conftest import page_url

pytestmark = pytest.mark.selenium


def make(scraper_class, driver, start_page: str):
    """A scraper pointed at a local catalogue page, without polite pauses."""
    scraper = scraper_class(driver)
    scraper.start_url = page_url(scraper_class.shop, start_page)
    scraper.pause_seconds = 0
    scraper.opens_product_pages = False  # product pages are tested separately through enrich()
    return scraper


def product(shop: str, page: str) -> Product:
    return Product(shop=shop, name="test", url=page_url(shop, page), price=1)


# --- catalogue pages and pagination ---------------------------------------------------------

def test_muzikant_two_pages_and_broken_card_skipped(driver, caplog):
    scraper = make(MuzikantScraper, driver, "catalogue.html")
    with caplog.at_level(logging.WARNING):
        products = scraper.collect(max_pages=2)

    assert [p.name for p in products] == [
        "Акустична гітара Cort AD810 (Open Pore)",
        "Акустична гітара Yamaha F310",
        "Акустична гітара Cort AF510 OP",
    ]
    first, second, third = products
    assert (first.price, first.old_price, first.availability) == (5499, None, "В наявності")
    assert first.features == {"Верхня дека": "Ялина"}
    assert (second.price, second.old_price) == (7699, 8100)
    assert third.availability == "Немає в наявності"
    assert "Card 3 on page 1 skipped" in caplog.text


def test_muzikant_stops_at_max_pages(driver):
    products = make(MuzikantScraper, driver, "catalogue.html").collect(max_pages=1)
    assert len(products) == 2


def test_jam_show_more_adds_cards(driver):
    products = make(JamScraper, driver, "catalogue.html").collect(max_pages=2)

    assert [p.name for p in products] == [
        "Yamaha FG820 (Sunset Blue)",
        "Cort AD810 (Open Pore)",
        "Maxtone WGC4010 (Natural)",
    ]
    assert products[0].price == 22011
    assert (products[1].price, products[1].old_price) == (5499, 5999)  # discounted card
    assert products[2].availability == "Під замовлення"


def test_guitarhouse_code_duplicates_and_missing_price(driver, caplog):
    scraper = make(GuitarHouseScraper, driver, "catalogue.html")
    with caplog.at_level(logging.WARNING):
        products = scraper.collect(max_pages=2)

    # FG820 is on both pages but counted once
    assert [p.name for p in products] == [
        "Акустична гітара YAMAHA FG820 (Sunset Blue)",
        "Акустична гітара Sigma 000M-1E-MFP",
        "Акустична гітара CORT AD MINI M (Open Pore)",
    ]
    assert products[0].features == {"Артикул": "33545"}
    assert (products[1].price, products[1].old_price) == (29900, 31000)
    assert products[2].price is None
    assert "Product has no price" in caplog.text


def test_dommuzyki_price_from_right_block_and_last_page(driver):
    products = make(DommuzykiScraper, driver, "catalogue.html").collect(max_pages=5)

    # page 2 has a disabled "next" without a link: the catalogue ends there
    assert [p.name for p in products] == ["CORT AD810 (Open Pore)", "MAXTONE WGC4010 NAT", "STAGG SA20D BLK"]
    assert products[0].price == 5499  # not the "1 грн" from the left block
    assert (products[1].price, products[1].old_price) == (4099, 4695)


# --- product pages --------------------------------------------------------------------------

def test_muzikant_product_page(driver):
    result = MuzikantScraper(driver).enrich(product("muzikant", "product.html"))
    assert result.features == {
        "Верхня дека": "Ялина",
        "Накладка грифа": "Палісандр",
        "Артикул виробника": "AD810OP",
    }  # "Місто" (delivery cities) is skipped


def test_jam_product_page(driver):
    result = JamScraper(driver).enrich(product("jam", "product.html"))
    assert result.features == {
        "Верхня дека": "Цілісна ялина (Solid Spruce)",
        "Гриф": "Нато (Nato) з накладкою з горіха (Walnut)",
        "Артикул": "33545",
    }


def test_guitarhouse_table_wins_over_description(driver):
    result = GuitarHouseScraper(driver).enrich(product("guitarhouse", "product-table.html"))
    assert result.features == {"Верхня дека": "Ялина", "Бридж": "Палісандр"}


def test_guitarhouse_description_list_when_no_table(driver):
    result = GuitarHouseScraper(driver).enrich(product("guitarhouse", "product-list.html"))
    assert result.features == {
        "Матеріал верхньої деки": "ситхінська ялина (Sitka Spruce)",
        "Кількість струн": "6",
    }


def test_guitarhouse_no_characteristics_is_a_warning(driver, caplog):
    with caplog.at_level(logging.WARNING):
        result = GuitarHouseScraper(driver).enrich(product("guitarhouse", "product-empty.html"))
    assert result.features == {}
    assert "No characteristics on the product page" in caplog.text


def test_dommuzyki_product_page(driver):
    result = DommuzykiScraper(driver).enrich(product("dommuzyki", "product.html"))
    assert result.features == {
        "Верхня дека": "Ялина",
        "Підкладка з грифом": "Палісандр",
        "Чехол / кейс в наборі": "Ні",
    }


# --- failures ------------------------------------------------------------------------------

def test_catalogue_without_cards_logs_error_and_saves_screenshot(driver, caplog, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # screenshots/ is created here, not in the project
    scraper = make(GuitarHouseScraper, driver, "product-empty.html")  # a page with no cards
    scraper.wait = WebDriverWait(driver, 1)

    with caplog.at_level(logging.ERROR):
        products = scraper.collect(max_pages=1)

    assert products == []
    assert "Catalogue did not load: TimeoutException" in caplog.text
    assert len(list((tmp_path / "screenshots").glob("guitarhouse_catalogue_not_loaded_*.png"))) == 1
