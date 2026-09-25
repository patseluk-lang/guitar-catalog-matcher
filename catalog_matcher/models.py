"""Common product format shared by all shop scrapers."""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Product:
    """One product card as collected from a shop, before any normalisation."""

    shop: str
    name: str
    url: str
    price: int | None
    old_price: int | None = None
    currency: str = "UAH"
    availability: str = ""
    features: dict[str, str] = field(default_factory=dict)
    collected_at: datetime = field(default_factory=datetime.now)