# guitar-catalog-matcher

Collects acoustic guitars from four Ukrainian music shops with **Selenium**, stores them in
**SQLite** with price history, and finds **the same guitar across shops** even when every shop
writes its name differently. On top of that it shows where shops describe the same guitar
with **different wood**, and builds an HTML report and a CSV file.

```
Акустична гітара YAMAHA FG820 (Sunset Blue)   Гітарний дім   22 011
Yamaha FG820 (Sunset Blue)                    JAM            22 011
Акустична гітара Yamaha FG820 SB              MuzikAnt       22 011
                  -> one guitar: YAMAHAFG820SUNSETBLUE
```

## Why

Shops fill their catalogues by hand. The same model appears as `CORT AD810 (Open Pore)`,
`Cort AD810 OP` and `CORT AD810 OP`; colours are spelled out in one shop and abbreviated in
another; "solid spruce", "цілісна ялина" and plain "ялина" mean the same top. Comparing prices
or specifications across shops first needs a reliable answer to "is this the same guitar?".

The matching rules come from practice in instrument retail and are written down in the code
together with real examples from the data.

## Shops

| Shop | Catalogue | How the next portion loads | Product page |
|---|---|---|---|
| MuzikAnt (muzikant.ua) | `?page=N` | click on "next", wait for URL + old card to go stale | characteristics list, maker's article |
| JAM (jam.ua) | one page | "Show more" button, custom wait for more cards | characteristics table, shop code |
| Гітарний дім (guitarhouse.com.ua) | `/filter/page=N/` | click on "next" | table, or a list in the description |
| Dommuzyki (dommuzyki.ua) | `?p=N` | click on "next" | characteristics table |

A fifth shop, MuzLine, was dropped: its "show more" request is disallowed in `robots.txt`
and the pages sit behind a Cloudflare challenge. The project does not bypass bot protection.

## Matching

| Level | Rule | Result |
|---|---|---|
| 1 | Same shop code (JAM "Код товару" = Гітарний дім "Артикул") | same guitar |
| 2 | Same normalised name: brand + model + colour code | same guitar |
| 3 | Same brand and base model, different index or extra words | shown to a human |

Name normalisation (level 2):

- shop prefixes removed: `Акустична гітара`, `Гітара акустична`, …
- colours to one code: `Open Pore` → `OP`, `Black Satin` → `BKS`, `Ruby Red` → `RR`, …
- no colour in the name means **Natural**: `YAMAHA F310 Natural` = `Yamaha F310`
- a bare `SB` means **Sunburst**, except Yamaha, where `SB` is the maker's code for
  **Sunset Blue** (`FG820 SB` = `FG820 (Sunset Blue)`)
- `-12` after the model means **12 strings**: `AD810-12` is never matched with `AD810`
- wood in the name makes a different product: `SA25 A SPRUCE` ≠ `SA25 A MAHO`
- a shop never lists the same guitar twice, so two offers of one shop are never joined

Groups are built with union-find, so a guitar joined by code in two shops and by name in a
third ends up in one group.

Level 3 skips pairs that one shop sells side by side (Гітарний дім has both `AD810` and
`AD810M`, so they are different guitars) and pairs with different colours.

## Wood vocabulary

Characteristics are compared after normalisation (`catalog_matcher/normalize.py`); raw values
stay in the database untouched.

- `Цілісна ялина (Solid Spruce)`, `масив ялини`, `ситхінська ялина` → `ялина`
- `Меранті`, `Сапеле`, `Окуме`, `Махагоні`, `Swietenia` → `червоне дерево`
- `HPL`, `Ламінована деревина`, `Інженерна деревина` → `ламінат`
- `Тонвуд`, `Деревина музичних порід` → not specified (not a conflict)
- `Нато з накладкою з горіха` → neck `нато` + fretboard `горіх`
- shop labels to common fields: `Матеріал верхньої деки` → `Верхня дека`,
  `Підкладка з грифом` → `Накладка грифа`, …

## Results

One run with three catalogue pages per shop (September 2026):

| | |
|---|---|
| Products collected | 303 (MuzikAnt 108, Dommuzyki 90, Гітарний дім 60, JAM 45) |
| Characteristics stored | 3 561 |
| Same guitar in 2+ shops | 66 groups, 15 of them in all four shops |
| Groups with different prices | 14 |
| Similar models for a human | 3 |
| Same guitar, different wood by shop | 36 groups |

What the data shows:

- **Prices mostly match to the hryvnia**, but not everywhere: 10 SX models cost about 5% more
  in Dommuzyki than in MuzikAnt (`SX SD104`: 4 082 vs 3 878).
- **The whole Cort AD810 / AF510 line has two versions of the truth**: MuzikAnt and
  Dommuzyki write a rosewood fretboard, JAM writes merbau.
- **Colour fields are filled by default values**: MuzikAnt shows `FG820 SB` with colour
  "Санберст", while the photo, the price and the maker's code say Sunset Blue.

## Selenium techniques

- explicit waits only: `presence_of_all_elements_located`, `element_to_be_clickable`,
  `url_contains`, `staleness_of`, and a custom condition `cards_more_than(selector, count)`
  for the "Show more" button
- `textContent` instead of `.text` to read hidden elements, `scrollIntoView` before clicks
- a common `BaseScraper`: a shop only defines selectors, `parse_card`, `next_page` and
  optionally `enrich` for product pages; the fourth shop was added without touching the others
- one broken card or one failing shop does not stop the run
- screenshots on errors (`screenshots/`), errors copied into the `errors` table
- polite 3-second pauses between pages; product pages already in the database are not
  opened again (`--refresh-details` forces it)

## Project structure

```
main.py                       CLI: collect into SQLite
Dockerfile, docker-compose.yml  headless run in a container
catalog_matcher/
    models.py                 Product dataclass
    database.py               SQLite schema and storage
    scrapers/                 base.py + one file per shop
    normalize.py              wood vocabulary
    matcher.py                levels 1-3 and wood conflicts
    report.py                 reports/report.html and reports/offers.csv
tests/                        unit tests + Selenium tests on local HTML pages
```

Database tables: `shops`, `products` (one row per URL), `price_history` (a row per product
per run), `features`, `scraping_runs`, `errors`.

Logs: `logs/application.log` (everything), `logs/scraper.log` (scrapers), `logs/errors.log`.

## Usage

Requirements: Python 3.11+, Google Chrome (Selenium Manager downloads the matching driver).

```
git clone https://github.com/patseluk-lang/guitar-catalog-matcher.git
cd guitar-catalog-matcher
python -m venv .venv
.venv\Scripts\activate            # Windows; on Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

```
python main.py                                  # all shops, first catalogue page
python main.py --shops jam dommuzyki --pages 3  # selected shops, three pages each
python main.py --refresh-details                # read product pages again

python -m catalog_matcher.matcher               # groups, candidates, wood conflicts
python -m catalog_matcher.normalize             # every raw wood value and its common form
python -m catalog_matcher.report                # reports/report.html and reports/offers.csv
```

`offers.csv` uses `;` and UTF-8 with BOM, so Excel opens it with Cyrillic intact.

### With Docker

The image contains Python, headless Chromium and its driver, so nothing else has to be
installed. The database, logs, reports and screenshots stay in the project folder on the host.

```
docker compose build
docker compose run --rm app main.py --pages 3            # collect
docker compose run --rm app -m catalog_matcher.matcher   # match
docker compose run --rm app -m catalog_matcher.report    # reports/report.html, reports/offers.csv
docker compose run --rm app -m pytest                    # all tests inside the container
```

`docker compose run --rm app <arguments>` runs `python <arguments>` in the container.

## Tests

```
python -m pytest                    # everything: 72 tests
python -m pytest -m "not selenium"  # fast unit tests only
python -m pytest -m selenium        # Selenium tests in headless Chrome
```

Selenium tests open small local HTML pages (`tests/pages/`) with the same markup as the
shops, so they need no internet: catalogue pages, "next" and "Show more", a broken card,
a duplicate product, a product without price, product pages with a table, a description list
or nothing at all, and a catalogue that fails to load (error logged, screenshot saved).

## Limitations

- acoustic guitars only; classical guitars are the next category
- no bot-protection bypass, by design
- the colour and wood dictionaries cover what the four shops use today; a new shop may bring
  new spellings, which `python -m catalog_matcher.normalize` makes easy to spot
