"""MuzikAnt: classic pagination, next page by clicking the 'next' link."""
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC

from catalog_matcher.models import Product
from catalog_matcher.scrapers.base import BaseScraper, first_text, text_of, to_int


class MuzikantScraper(BaseScraper):
    shop = "muzikant"
    start_url = "https://muzikant.ua/ukr/category/gitary-i-oborudovanie/gitary-akusticheskie/"
    card_selector = ".c-category-page__products .c-product-thumb"
    next_selector = "a.c-pagination-item_next"

    def parse_card(self, card: WebElement) -> Product:
        link = card.find_element(By.CSS_SELECTOR, "a.c-product-thumb__name")
        return Product(
            shop=self.shop,
            name=text_of(link),
            url=link.get_attribute("href"),
            price=to_int(first_text(card, ".c-product-thumb__price")),
            old_price=to_int(first_text(card, ".c-product-thumb__compare-price")),
            availability=first_text(card, ".c-product-thumb__available"),
            features=self._features(card),
        )

    def next_page(self, page_number: int) -> bool:
        if not self.driver.find_elements(By.CSS_SELECTOR, self.next_selector):
            return False
        old_first_card = self.cards()[0]
        link = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, self.next_selector)))
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", link)
        link.click()
        self.wait.until(EC.url_contains(f"page={page_number}"))
        self.wait.until(EC.staleness_of(old_first_card))
        self.wait_for_cards()
        return True

    @staticmethod
    def _features(card: WebElement) -> dict[str, str]:
        """'Верхня дека:' / 'Ялина' pairs -> {'Верхня дека': 'Ялина'}"""
        features = {}
        for item in card.find_elements(By.CSS_SELECTOR, ".c-product-features-overview__item"):
            label = first_text(item, ".c-value__label-text").rstrip(":")
            if label:
                features[label] = first_text(item, ".c-value__value-text")
        return features