"""Guitar House (guitarhouse.com.ua): classic pagination, shop code in the card,
characteristics on product pages (a table, or a list in the description)."""
import re

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC

from catalog_matcher.models import Product
from catalog_matcher.scrapers.base import BaseScraper, first_text, text_of, to_int


class GuitarHouseScraper(BaseScraper):
    shop = "guitarhouse"
    start_url = "https://guitarhouse.com.ua/akustichni-gitari/"
    card_selector = ".catalog-grid__item .catalogCard"
    next_selector = "a.pager__item--forth"
    spec_rows_selector = ".product-features__table tr.product-features__row"
    description_items_selector = ".product-description li"
    opens_product_pages = True

    def parse_card(self, card: WebElement) -> Product:
        link = card.find_element(By.CSS_SELECTOR, ".catalogCard-title a")
        code = re.sub(r"\D", "", first_text(card, ".catalogCard-code"))
        return Product(
            shop=self.shop,
            name=text_of(link),
            url=link.get_attribute("href"),
            price=to_int(first_text(card, ".catalogCard-price")),
            old_price=to_int(first_text(card, ".catalogCard-oldPrice")),
            availability=first_text(card, ".catalogCard-availability"),
            features={"Артикул": code} if code else {},
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

    def enrich(self, product: Product) -> Product:
        self.driver.get(product.url)
        # Table and description are part of the page itself: once the title is there, they are too.
        self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
        features = self.table_features() or self.description_features()
        if not features:
            self.log.warning("No characteristics on the product page: %s", product.url)
        product.features.update(features)
        return product

    def table_features(self) -> dict[str, str]:
        """Rows of the 'Характеристики' table: <th>label</th><td>value</td>."""
        features = {}
        for row in self.driver.find_elements(By.CSS_SELECTOR, self.spec_rows_selector):
            label, value = first_text(row, "th"), first_text(row, "td")
            if label and value:
                features[label] = value
        return features

    def description_features(self) -> dict[str, str]:
        """Some products have no table, only a list in the description: 'Label: value'."""
        features = {}
        for item in self.driver.find_elements(By.CSS_SELECTOR, self.description_items_selector):
            label, colon, value = text_of(item).partition(":")
            if colon and label.strip() and value.strip():
                features[label.strip()] = value.strip()
        return features