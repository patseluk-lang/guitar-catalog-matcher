"""Bring characteristics from different shops to one vocabulary.

Raw values stay in the database untouched; this runs at comparison time.
Rules (agreed with a guitar seller):
- "цілісна ялина", "масив ялини", "Solid Spruce" and plain "ялина" are the same wood;
- меранті, сапеле, окуме, махагоні are sold as червоне дерево;
- "деревина музичних порід", "тонвуд", "деревина твердих порід" say nothing: not specified;
- ламінат, HPL, ламінована деревина: ламінат.
"""
import re
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path("data") / "catalog.db"

FIELDS = ("Верхня дека", "Нижня дека", "Обичайка", "Гриф", "Накладка грифа", "Бридж")
NOT_SPECIFIED = "не вказано"

# Shop label -> one or more common fields.
LABELS = {
    "Верхня дека": ("Верхня дека",),
    "Матеріал верхньої деки": ("Верхня дека",),
    "Нижня дека": ("Нижня дека",),
    "Матеріал задньої деки та обичайок": ("Нижня дека", "Обичайка"),
    "Обичайка": ("Обичайка",),
    "Гриф": ("Гриф",),
    "Матеріал грифа": ("Гриф",),
    "Накладка грифа": ("Накладка грифа",),
    "Матеріал накладки грифа та струнотримача": ("Накладка грифа", "Бридж"),
    "Бридж": ("Бридж",),
}

# Words that do not change the wood.
NOISE = re.compile(r"\b(цілісн\w*|цільн\w*|масив\w*|solid|хвиляст\w*|ситхінськ\w*)\b")

WOODS = {
    "махагоні": "червоне дерево",
    "махогані": "червоне дерево",
    "меранті": "червоне дерево",
    "сапеле": "червоне дерево",
    "окуме": "червоне дерево",
    "swietenia": "червоне дерево",
    "полісандр": "палісандр",
    "палісандрова": "палісандр",
    "палісандровою": "палісандр",
    "деревина музичних порід": NOT_SPECIFIED,
    "тонвуд": NOT_SPECIFIED,
    "деревина твердих порід": NOT_SPECIFIED,
    "hpl": "ламінат",
    "ламінована деревина музичних порід": "ламінат",
    "ламінована деревина": "ламінат",
    "mahogany finish utf": "ламінат",
    "бранковуд": "коричневе дерево",
}

# JAM: "Нато (Nato) з накладкою з горіха (Walnut)", "Нато з палісандровою накладкою".
NECK_WITH_BOARD = (
    re.compile(r"^(?P<neck>.+?)\s+(?:з|із)\s+накладк\w*\s+(?:з|із)\s+(?P<board>.+)$"),
    re.compile(r"^(?P<neck>.+?)\s+(?:з|із)\s+(?P<board>\S+)\s+накладк\w*$"),
)

# Genitive forms after "з накладкою з ...".
GENITIVE = {"горіха": "горіх", "мербау": "мербау", "лаурелю": "лаурель", "палісандра": "палісандр"}


def wood(value: str) -> str:
    """'Цілісна ялина (Solid Spruce)' -> 'ялина'; 'Меранті (Meranti)' -> 'червоне дерево'."""
    text = value.lower()
    text = re.sub(r"\([^)]*\)", " ", text)  # English names and notes in brackets
    text = NOISE.sub(" ", text)
    text = " ".join(text.split())
    text = GENITIVE.get(text, text)
    return WOODS.get(text, text) or NOT_SPECIFIED


def normalise(features: dict[str, str]) -> dict[str, str]:
    """Shop characteristics -> {common field: common value}, only FIELDS."""
    result: dict[str, str] = {}
    for label, value in features.items():
        for field in LABELS.get(label, ()):
            if field == "Гриф":
                for pattern in NECK_WITH_BOARD:
                    match = pattern.match(re.sub(r"\([^)]*\)", " ", value).strip())
                    if match:
                        result["Гриф"] = wood(match["neck"])
                        result.setdefault("Накладка грифа", wood(match["board"]))
                        break
                else:
                    result["Гриф"] = wood(value)
            else:
                result[field] = wood(value)
    return result


def main() -> None:
    """Show every raw value next to its normalised form, to check the rules by eye."""
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DB_PATH
    connection = sqlite3.connect(str(path))
    try:
        rows = connection.execute("SELECT product_id, label, value FROM features").fetchall()
    finally:
        connection.close()

    products: dict[int, dict[str, str]] = {}
    for product_id, label, value in rows:
        products.setdefault(product_id, {})[label] = value

    seen: dict[str, dict[str, set[str]]] = {field: {} for field in FIELDS}
    for features in products.values():
        normal = normalise(features)
        for label, value in features.items():
            fields = LABELS.get(label, ())
            if "Гриф" in fields and "накладк" in value.lower():
                fields = ("Гриф", "Накладка грифа")
            for field in fields:
                if field in normal:
                    seen[field].setdefault(normal[field], set()).add(value)

    for field in FIELDS:
        print(f"\n== {field}")
        for normal, raw in sorted(seen[field].items()):
            print(f"    {normal:<20} <- {'; '.join(sorted(raw))}")


if __name__ == "__main__":
    main()