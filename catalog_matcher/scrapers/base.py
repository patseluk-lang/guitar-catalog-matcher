"""Base class for shop scrapers: waits, paging loop, pauses, screenshots, logging."""
import logging
import re
import time
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from catalog_matcher.models import Product

SCREENSHOTS = Path("screenshots")


def text_of(element: WebElement) -> str:
    """Element text with collapsed spaces, even if the element is not visible."""
    return " ".join(element.get_attribute("textContent").split())


def to_int(text: str) -> int | None:
    """'Ціна:7 699 грн.' -> 7699; text without digits -> None."""
    digits = re.sub(r"\D", "", text)
    return int(digits) if digits else None


def first_text(parent: WebElement, selector: str) -> str:
    """Text of the first element matching selector, or '' if there is none."""
    found = parent.find_elements(By.CSS_SELECTOR, selector)
    return text_of(found[0]) if found else ""


def cards_more_than(selector: str, count: int):
    """Custom wait condition: true when the page holds more than `count` cards."""
    def condition(driver: WebDriver) -> bool:
        return len(driver.find_elements(By.CSS_SELECTOR, selector)) > count
    return condition


class BaseScraper(ABC):
    """Common scraping flow. A shop subclass defines selectors, parse_card and next_page."""

    shop: str = ""
    start_url: str = ""
    card_selector: str = ""
    opens_product_pages: bool = False
    pause_seconds: float = 3.0  # rate limit to be polite to the shop, not a wait for elements
    wait_seconds: int = 15

    def __init__(self, driver: WebDriver):
        self.driver = driver
        self.wait = WebDriverWait(driver, self.wait_seconds)
        self.log = logging.getLogger(f"scraper.{self.shop}")

    @abstractmethod
    def parse_card(self, card: WebElement) -> Product:
        """Turn one catalogue card into a Product."""

    @abstractmethod
    def next_page(self, page_number: int) -> bool:
        """Bring the next portion of cards onto the page. Return False when the catalogue ends."""

    def enrich(self, product: Product) -> Product:
        """Open the product page and add details. Used only when opens_product_pages is True."""
        return product

    def cards(self) -> list[WebElement]:
        return self.driver.find_elements(By.CSS_SELECTOR, self.card_selector)

    def wait_for_cards(self) -> list[WebElement]:
        return self.wait.until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, self.card_selector))
        )

    def pause(self) -> None:
        time.sleep(self.pause_seconds)

    def screenshot(self, reason: str) -> Path:
        SCREENSHOTS.mkdir(exist_ok=True)
        path = SCREENSHOTS / f"{self.shop}_{reason}_{datetime.now():%Y%m%d_%H%M%S}.png"
        self.driver.save_screenshot(str(path))
        self.log.info("Screenshot saved: %s", path)
        return path

    def collect(self, max_pages: int, known_detail_urls: set[str] | None = None) -> list[Product]:
        """Walk up to max_pages portions of the catalogue and return unique products.

        known_detail_urls: product pages that need not be opened again
        because their characteristics are already stored.
        """
        self.log.info("Started %s", self.start_url)
        products: list[Product] = []
        seen_urls: set[str] = set()

        try:
            self.driver.get(self.start_url)
            self.wait_for_cards()
        except (TimeoutException, WebDriverException) as error:
            self.log.error("Catalogue did not load: %s", type(error).__name__)
            self.screenshot("catalogue_not_loaded")
            return products

        page = 1
        while True:
            new_count = 0
            for index, card in enumerate(self.cards(), start=1):
                try:
                    product = self.parse_card(card)
                except Exception as error:  # one broken card must not stop the run
                    self.log.warning("Card %d on page %d skipped: %s", index, page, error)
                    continue
                if product.url in seen_urls:
                    continue
                if product.price is None:
                    self.log.warning("Product has no price: %s", product.name)
                seen_urls.add(product.url)
                products.append(product)
                new_count += 1
            self.log.info("Page %d: %d new products, %d in total", page, new_count, len(products))

            if page >= max_pages:
                break
            self.pause()
            try:
                if not self.next_page(page + 1):
                    self.log.info("Catalogue finished")
                    break
            except (TimeoutException, WebDriverException) as error:
                self.log.error("Could not open page %d: %s", page + 1, type(error).__name__)
                self.screenshot(f"page{page + 1}_failed")
                break
            page += 1

        if self.opens_product_pages:
            products = self._enrich_all(products, known_detail_urls or set())

        self.log.info("Completed: %d products", len(products))
        return products

    def _enrich_all(self, products: list[Product], known_detail_urls: set[str]) -> list[Product]:
        skipped = sum(product.url in known_detail_urls for product in products)
        if skipped:
            self.log.info("Product pages skipped (details already stored): %d", skipped)

        enriched = []
        for product in products:
            if product.url in known_detail_urls:
                enriched.append(product)
                continue
            self.pause()
            try:
                enriched.append(self.enrich(product))
            except (TimeoutException, WebDriverException) as error:
                self.log.error("Unable to open product page %s: %s", product.url, type(error).__name__)
                self.screenshot("product_page_failed")
                enriched.append(product)
        return enriched