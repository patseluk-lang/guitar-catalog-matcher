"""Matching rules: names, colours, strings, level 3 candidates, wood conflicts."""
import pytest

from catalog_matcher.matcher import (
    Offer,
    build_groups,
    candidates,
    conflicts,
    matched_groups,
    model_parts,
    name_key,
    needs_human,
    string_count,
)


def offer(product_id, shop, name, price=1000, **features):
    return Offer(product_id, shop, name, f"https://{shop}/{product_id}", price, dict(features))


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("Акустична гітара CORT AD810 (Open Pore)", "Cort AD810 OP"),
        ("Акустична гітара YAMAHA F310 Natural", "Yamaha F310"),  # no colour means Natural
        ("Maxtone WGC4010 SB", "MAXTONE WGC4010 (Sunburst)"),  # bare SB means Sunburst
        ("Yamaha FG820 SB", "Акустична гітара YAMAHA FG820 (Sunset Blue)"),  # Yamaha: SB = Sunset Blue
        ("Cort AD810 (Black Satin)", "CORT AD810 BKS"),
        ("Parksons JB4111 Black", "PARKSONS JB-4111 BLK"),
    ],
)
def test_same_guitar_same_key(first, second):
    assert name_key(first) == name_key(second)


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("Cort AD810 OP", "Cort AD810M OP"),
        ("Cort AD810 OP", "Cort AD810-12 OP"),
        ("Yamaha FG820 SB", "Maxtone FG820 SB"),
        ("Maxtone WGC4010 SB", "Maxtone WGC4010 Sunset Blue"),  # outside Yamaha, SB is Sunburst
        ("Yamaha FG820 Natural", "Yamaha FG820 Black"),
    ],
)
def test_different_guitars_different_keys(first, second):
    assert name_key(first) != name_key(second)


@pytest.mark.parametrize(
    ("name", "strings"),
    [("Cort AD810-12 OP", 12), ("Cort AD810 OP", 6), ("Yamaha FG820-12 NT", 12), ("Yamaha F310", 6)],
)
def test_string_count(name, strings):
    assert string_count(name) == strings


@pytest.mark.parametrize(
    ("name", "parts"),
    [
        ("Cort AD810M OP", ("CORT AD810", "M", {"OP"})),
        ("Cort EARTH 60M (Open Pore)", ("CORT EARTH60", "M", {"OP"})),
        ("Yamaha JR2S TBS", ("YAMAHA JR2", "S", {"TBS"})),
        ("Maxtone WGC-360", ("MAXTONE WGC360", "", set())),
    ],
)
def test_model_parts(name, parts):
    assert model_parts(name) == (parts[0], parts[1], frozenset(parts[2]))


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        ("Cort AD810M OP", "Cort AD810 OP", True),  # index differs, colour the same
        ("Cort AD Mini M OP w /bag", "CORT AD MINI M (Open Pore)", True),  # extra words only
        ("Cort AD810M OP", "Cort AD810 BKS", False),  # another colour: another product
        ("Cort AD810 OP", "Cort AD810-12 OP", False),  # 6 and 12 strings
        ("Stagg SA25 A SPRUCE", "Stagg SA25 A MAHO", False),  # wood in the name
        ("Yamaha JR2 (Natural)", "Yamaha JR2S TBS", False),  # Natural vs a sunburst
        ("Maxtone WGC4010 SB", "Maxtone WGC4010 Sunset Blue", True),  # SB may mean Sunset Blue
    ],
)
def test_needs_human(first, second, expected):
    assert needs_human(offer(1, "a", first), offer(2, "b", second)) is expected


def test_groups_join_by_code_and_by_name():
    offers = [
        offer(1, "jam", "Yamaha FG820 (Sunset Blue)", Артикул="33545"),
        offer(2, "guitarhouse", "YAMAHA FG820 Blue", Артикул="33545"),  # same code, other name
        offer(3, "muzikant", "Yamaha FG820 SB"),  # no code, same name as offer 1
        offer(4, "muzikant", "Cort AD810 OP"),  # alone
    ]
    groups, members = build_groups(offers)
    matched = matched_groups(groups, members)

    assert len(matched) == 1
    evidence, items = matched[0]
    assert evidence == {"code", "name"}
    assert [item.product_id for item in items] == [2, 1, 3]  # sorted by shop


def test_candidates_need_a_human_and_skip_what_one_shop_sells_side_by_side():
    offers = [
        offer(1, "guitarhouse", "CORT AD MINI M (Open Pore)"),
        offer(2, "muzikant", "Cort AD Mini M OP w /bag"),
        # Guitar House sells both AD810 and AD810M: they are different guitars, not candidates
        offer(3, "guitarhouse", "Cort AD810 OP"),
        offer(4, "guitarhouse", "Cort AD810M OP"),
        offer(5, "jam", "Cort AD810M OP"),
        offer(6, "dommuzyki", "Cort AD810 OP"),
    ]
    _, members = build_groups(offers)
    pairs = candidates(members)

    assert [(a.product_id, b.product_id) for a, b in pairs] == [(1, 2)]


def test_conflicts_ignore_not_specified():
    offers = [
        offer(1, "jam", "Cort AD810 OP", Бридж="Мербау (Merbau)", **{"Верхня дека": "Ялина"}),
        offer(2, "guitarhouse", "Cort AD810 OP", Бридж="Палісандр", **{"Верхня дека": "Тонвуд"}),
        offer(3, "muzikant", "Cort AD810 OP", **{"Верхня дека": "Цілісна ялина"}),
    ]
    groups, members = build_groups(offers)
    found = conflicts(matched_groups(groups, members))

    assert len(found) == 1
    _, differing = found[0]
    assert differing == {"Бридж": {"jam": "мербау", "guitarhouse": "палісандр"}}
