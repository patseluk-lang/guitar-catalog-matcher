"""Shared fixtures: headless Chrome and paths to the local test pages."""
import os
from pathlib import Path

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.service import Service

PAGES = Path(__file__).parent / "pages"


def page_url(shop: str, name: str) -> str:
    """file:///.../tests/pages/<shop>/<name> - a local page, no internet needed."""
    return (PAGES / shop / name).resolve().as_uri()


@pytest.fixture(scope="session")
def driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")  # small /dev/shm inside Docker
    # Optional overrides for machines where Chrome is not installed in the usual place (e.g. CI).
    if os.environ.get("CHROME_BINARY"):
        options.binary_location = os.environ["CHROME_BINARY"]
    service = Service(os.environ["CHROMEDRIVER"]) if os.environ.get("CHROMEDRIVER") else None
    browser = webdriver.Chrome(options=options, service=service)
    yield browser
    browser.quit()
