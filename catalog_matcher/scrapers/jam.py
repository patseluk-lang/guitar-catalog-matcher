"""JAM: "Show more" button on the catalogue, characteristics on product pages."""
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC

from catalog_matcher.models import Product
from catalog_matcher.scrapers.base import (
    BaseScraper,
    cards_more_than,
    first_text,
    text_of,
    to_int,
)


class JamScraper(BaseScraper):
    shop = "jam"
    start_url = "https://jam.ua/ua/acoustic_guitars"
    card_selector = ".catalog_section .product-card--catalog"
    show_more_selector = "a.catalogue-more"
    spec_rows_selector = ".product-characteristics__table tr"
    opens_product_pages = True

    def parse_card(self, card: WebElement) -> Product:
        link = card.find_element(By.CSS_SELECTOR, ".product__title a")
        discounted = first_text(card, ".product__price-action .new")
        if discounted:
            price = to_int(discounted)
            old_price = to_int(first_text(card, ".product__price-action .old"))
        else:
            price = to_int(first_text(card, ".product__price"))
            old_price = None
        return Product(
            shop=self.shop,
            name=text_of(link),
            url=link.get_attribute("href"),
            price=price,
            old_price=old_price,
            availability=first_text(card, ".product-presence"),
        )

    def next_page(self, page_number: int) -> bool:
        if not self.driver.find_elements(By.CSS_SELECTOR, self.show_more_selector):
            return False
        before = len(self.cards())
        button = self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, self.show_more_selector))
        )
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
        button.click()
        self.wait.until(cards_more_than(self.card_selector, before))
        return True

    def enrich(self, product: Product) -> Product:
        self.driver.get(product.url)
        rows = self.wait.until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, self.spec_rows_selector))
        )
        for row in rows:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) == 2:
                product.features[text_of(cells[0])] = text_of(cells[1])
        return product