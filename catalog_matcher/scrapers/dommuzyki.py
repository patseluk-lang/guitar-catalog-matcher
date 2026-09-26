"""Dommuzyki (dommuzyki.ua, PrestaShop): classic pagination (?p=N),
characteristics table on product pages."""
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC

from catalog_matcher.models import Product
from catalog_matcher.scrapers.base import BaseScraper, first_text, text_of, to_int


class DommuzykiScraper(BaseScraper):
    shop = "dommuzyki"
    start_url = "https://dommuzyki.ua/uk/294-akustichni-gitari"
    card_selector = "ul.product_list > li.ajax_block_product"
    next_selector = "li.pagination_next a"
    spec_rows_selector = "table.table-data-sheet tr"
    opens_product_pages = True

    def parse_card(self, card: WebElement) -> Product:
        link = card.find_element(By.CSS_SELECTOR, ".right-block a.product-name")
        return Product(
            shop=self.shop,
            name=text_of(link),
            url=link.get_attribute("href"),
            price=to_int(first_text(card, ".right-block .price.product-price")),
            old_price=to_int(first_text(card, ".right-block .old-price")),
        )

    def next_page(self, page_number: int) -> bool:
        if not self.driver.find_elements(By.CSS_SELECTOR, self.next_selector):
            return False
        old_first_card = self.cards()[0]
        link = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, self.next_selector)))
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", link)
        link.click()
        self.wait.until(EC.url_contains(f"p={page_number}"))
        self.wait.until(EC.staleness_of(old_first_card))
        self.wait_for_cards()
        return True

    def enrich(self, product: Product) -> Product:
        self.driver.get(product.url)
        # The table is part of the page itself: once the title is there, the table is too.
        self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
        rows = self.driver.find_elements(By.CSS_SELECTOR, self.spec_rows_selector)
        if not rows:
            self.log.warning("No characteristics on the product page: %s", product.url)
        for row in rows:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) == 2:
                label = text_of(cells[0]).rstrip(":").strip()
                value = text_of(cells[1])
                if label and value:
                    product.features[label] = value
        return product