"""Build reports/report.html and reports/offers.csv from the database.

Run:  python -m catalog_matcher.report [path/to/catalog.db]
"""
import csv
import html
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from catalog_matcher.matcher import (
    DB_PATH,
    PREFIXES,
    Offer,
    build_groups,
    candidates,
    conflicts,
    load_offers,
    matched_groups,
    name_key,
)
from catalog_matcher.normalize import FIELDS, normalise

REPORTS_DIR = Path("reports")

LATEST = """
SELECT h.product_id, h.old_price, h.availability
FROM price_history h
WHERE h.id = (SELECT MAX(id) FROM price_history WHERE product_id = h.product_id)
"""

# Last two prices of every product; a row appears only when they differ.
PRICE_CHANGES = """
WITH ranked AS (
    SELECT product_id, price, collected_at,
           ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY id DESC) AS position
    FROM price_history
)
SELECT s.name, p.name, p.url, before.price, now.price, now.collected_at
FROM ranked now
JOIN ranked before ON before.product_id = now.product_id AND before.position = 2
JOIN products p ON p.id = now.product_id
JOIN shops s ON s.id = p.shop_id
WHERE now.position = 1 AND now.price IS NOT before.price
ORDER BY s.name, p.name
"""

SUMMARY = """
SELECT s.name,
       (SELECT COUNT(*) FROM products p WHERE p.shop_id = s.id),
       (SELECT MAX(r.finished_at) FROM scraping_runs r WHERE r.shops LIKE '%' || s.name || '%')
FROM shops s
ORDER BY s.name
"""

ERRORS = "SELECT created_at, shop, message FROM errors ORDER BY id DESC LIMIT 20"

STYLE = """
body { font-family: Segoe UI, Arial, sans-serif; margin: 24px; color: #222; }
h1 { margin-bottom: 4px; }
h2 { margin-top: 32px; border-bottom: 2px solid #ddd; padding-bottom: 4px; }
table { border-collapse: collapse; margin-top: 8px; }
th, td { border: 1px solid #ddd; padding: 4px 8px; text-align: left; vertical-align: top; }
th { background: #f3f3f3; }
td.num { text-align: right; white-space: nowrap; }
.cheapest { background: #e2f5e2; font-weight: bold; }
.down { color: #0a7a0a; font-weight: bold; }
.up { color: #b00020; }
.muted { color: #777; }
"""


def esc(value) -> str:
    return html.escape("" if value is None else str(value))


def link(offer: Offer) -> str:
    return f'<a href="{esc(offer.url)}">{esc(offer.name)}</a>'


def money(value) -> str:
    return "-" if value is None else f"{value:,}".replace(",", " ")


def short_name(name: str) -> str:
    """'Акустична гітара CORT AD880 (Natural Satin)' -> 'CORT AD880 (Natural Satin)'."""
    for prefix in PREFIXES:
        if name.upper().startswith(prefix):
            return name[len(prefix):].strip()
    return name


def display_name(items: list[Offer]) -> str:
    """One readable name for a group: the shortest one without the shop prefix."""
    return min((short_name(offer.name) for offer in items), key=len)


def group_keys(members: dict[int, list[Offer]]) -> dict[int, str]:
    """product_id -> one key per group (the same guitar gets the same key)."""
    keys = {}
    for items in members.values():
        key = min(name_key(offer.name) for offer in items)
        for offer in items:
            keys[offer.product_id] = key
    return keys


def write_csv(path: Path, offers: list[Offer], keys: dict[int, str], latest: dict) -> None:
    columns = ["shop", "group", "name", "url", "price", "old_price", "availability", *FIELDS]
    # utf-8-sig and ';' so that Excel with Ukrainian settings opens it correctly.
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file, delimiter=";")
        writer.writerow(columns)
        for offer in sorted(offers, key=lambda item: (keys[item.product_id], item.shop)):
            old_price, availability = latest.get(offer.product_id, (None, ""))
            wood = normalise(offer.features)
            writer.writerow([
                offer.shop, keys[offer.product_id], offer.name, offer.url,
                offer.price, old_price, availability, *(wood.get(part, "") for part in FIELDS),
            ])


def summary_section(connection) -> str:
    rows = "".join(
        f"<tr><td>{esc(shop)}</td><td class='num'>{count}</td><td>{esc(finished)}</td></tr>"
        for shop, count, finished in connection.execute(SUMMARY)
    )
    return (
        "<h2>Summary</h2><table><tr><th>Shop</th><th>Products</th><th>Last run finished</th></tr>"
        f"{rows}</table>"
    )


def groups_section(groups, shops: list[str]) -> str:
    head = "".join(f"<th>{esc(shop)}</th>" for shop in shops)
    rows = []
    for _, items in groups:
        by_shop = {offer.shop: offer for offer in items}
        prices = [offer.price for offer in items if offer.price is not None]
        lowest = min(prices) if len(set(prices)) > 1 else None
        cells = []
        for shop in shops:
            offer = by_shop.get(shop)
            if offer is None:
                cells.append("<td class='muted'>-</td>")
                continue
            mark = " cheapest" if offer.price == lowest else ""
            cells.append(f"<td class='num{mark}'><a href='{esc(offer.url)}'>{money(offer.price)}</a></td>")
        rows.append(f"<tr><td>{esc(display_name(items))}</td>{''.join(cells)}</tr>")
    return (
        f"<h2>Same guitar in different shops ({len(groups)})</h2>"
        "<p class='muted'>Green: the cheapest where prices differ. Prices in UAH.</p>"
        f"<table><tr><th>Guitar</th>{head}</tr>{''.join(rows)}</table>"
    )


def price_changes_section(connection) -> str:
    rows = []
    for shop, name, url, before, now, collected in connection.execute(PRICE_CHANGES):
        dropped = before is not None and now is not None and now < before
        css = "down" if dropped else "up"
        label = "price drop" if dropped else "price rise"
        rows.append(
            f"<tr><td>{esc(shop)}</td><td><a href='{esc(url)}'>{esc(name)}</a></td>"
            f"<td class='num'>{money(before)}</td><td class='num {css}'>{money(now)}</td>"
            f"<td class='{css}'>{label}</td><td>{esc(collected)}</td></tr>"
        )
    if not rows:
        return "<h2>Price changes</h2><p class='muted'>No price changes since the previous run.</p>"
    return (
        f"<h2>Price changes ({len(rows)})</h2><table><tr><th>Shop</th><th>Guitar</th>"
        f"<th>Before</th><th>Now</th><th></th><th>Collected</th></tr>{''.join(rows)}</table>"
    )


def candidates_section(pairs) -> str:
    rows = "".join(
        f"<tr><td>{esc(first.shop)}: {link(first)} ({money(first.price)})</td>"
        f"<td>{esc(second.shop)}: {link(second)} ({money(second.price)})</td></tr>"
        for first, second in pairs
    )
    return (
        f"<h2>Similar models - decide manually ({len(pairs)})</h2>"
        f"<table><tr><th>Offer</th><th>Offer</th></tr>{rows}</table>"
    )


def conflicts_section(found) -> str:
    rows = []
    for items, differing in found:
        for part, values in differing.items():
            shown = "; ".join(f"{esc(shop)}: {esc(value)}" for shop, value in sorted(values.items()))
            rows.append(f"<tr><td>{esc(display_name(items))}</td><td>{esc(part)}</td><td>{shown}</td></tr>")
    return (
        f"<h2>Same guitar, different wood by shop ({len(found)})</h2>"
        f"<table><tr><th>Guitar</th><th>Part</th><th>Shops say</th></tr>{''.join(rows)}</table>"
    )


def errors_section(connection) -> str:
    rows = "".join(
        f"<tr><td>{esc(created)}</td><td>{esc(shop)}</td><td>{esc(message)}</td></tr>"
        for created, shop, message in connection.execute(ERRORS)
    )
    if not rows:
        return "<h2>Errors</h2><p class='muted'>No errors.</p>"
    return f"<h2>Errors (last 20)</h2><table><tr><th>When</th><th>Shop</th><th>Message</th></tr>{rows}</table>"


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DB_PATH
    connection = sqlite3.connect(str(path))
    try:
        offers = load_offers(connection)
        latest = {row[0]: (row[1], row[2]) for row in connection.execute(LATEST)}
        groups, members = build_groups(offers)
        same_guitar = matched_groups(groups, members)
        shops = sorted({offer.shop for offer in offers})
        sections = [
            summary_section(connection),
            groups_section(same_guitar, shops),
            price_changes_section(connection),
            candidates_section(candidates(members)),
            conflicts_section(conflicts(same_guitar)),
            errors_section(connection),
        ]
    finally:
        connection.close()

    REPORTS_DIR.mkdir(exist_ok=True)
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    page = (
        "<!doctype html><html lang='uk'><head><meta charset='utf-8'>"
        f"<title>Guitar catalogue report</title><style>{STYLE}</style></head><body>"
        f"<h1>Guitar catalogue report</h1><p class='muted'>Generated {generated}</p>"
        f"{''.join(sections)}</body></html>"
    )
    html_path = REPORTS_DIR / "report.html"
    csv_path = REPORTS_DIR / "offers.csv"
    html_path.write_text(page, encoding="utf-8")
    write_csv(csv_path, offers, group_keys(members), latest)
    print(f"Report: {html_path.resolve()}")
    print(f"CSV:    {csv_path.resolve()} ({len(offers)} offers)")


if __name__ == "__main__":
    main()