"""Guitar House (guitarhouse.com.ua): classic pagination, shop code in the card."""
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