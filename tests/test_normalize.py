"""Wood vocabulary: the same wood written differently by different shops."""
import pytest

from catalog_matcher.normalize import NOT_SPECIFIED, normalise, wood


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Ялина", "ялина"),
        ("Цілісна ялина (Solid Spruce)", "ялина"),
        ("масив ялини", "ялина"),
        ("ситхінська ялина (Sitka Spruce)", "ялина"),
        ("Меранті (Meranti)", "червоне дерево"),
        ("Сапеле", "червоне дерево"),
        ("Махагоні", "червоне дерево"),
        ("Swietenia (Червоне дерево)", "червоне дерево"),
        ("Полісандр", "палісандр"),
        ("Лаурель (Laurel)", "лавр"),
        ("ABS-пластик", "пластик"),
        ("HPL", "ламінат"),
        ("Інженерна деревина", "ламінат"),
        ("Тонвуд", NOT_SPECIFIED),
        ("Деревина музичних порід", NOT_SPECIFIED),
        ("Хвилястий клен (Flamed Maple)", "клен"),
    ],
)
def test_wood(raw, expected):
    assert wood(raw) == expected


def test_neck_with_fretboard_is_split():
    assert normalise({"Гриф": "Нато (Nato) з накладкою з горіха (Walnut)"}) == {
        "Гриф": "нато",
        "Накладка грифа": "горіх",
    }
    assert normalise({"Гриф": "Нато з палісандровою накладкою"}) == {
        "Гриф": "нато",
        "Накладка грифа": "палісандр",
    }


def test_shop_labels_become_common_fields():
    features = {
        "Матеріал верхньої деки": "ситхінська ялина (Sitka Spruce)",
        "Матеріал задньої деки та обичайок": "червоне дерево (Mahogany)",
        "Підкладка з грифом": "Палісандр",
        "Гарантія": "12 місяців",  # not a wood field: ignored
    }
    assert normalise(features) == {
        "Верхня дека": "ялина",
        "Нижня дека": "червоне дерево",
        "Обичайка": "червоне дерево",
        "Накладка грифа": "палісандр",
    }


def test_separate_fretboard_field_wins_over_split_neck():
    features = {"Гриф": "Нато з накладкою з горіха", "Накладка грифа": "Палісандр"}
    assert normalise(features)["Накладка грифа"] == "палісандр"
