import json
from collections import Counter
from pathlib import Path


GOLDEN_DATASET_PATH = Path("eval/golden_dataset.json")

REQUIRED_ITEM_FIELDS = {
    "id",
    "question",
    "expected_answer",
    "expected_keywords",
    "category",
    "difficulty",
    "source",
}

ALLOWED_DIFFICULTIES = {"easy", "medium", "hard"}


def load_golden_dataset() -> dict:
    return json.loads(
        GOLDEN_DATASET_PATH.read_text(encoding="utf-8")
    )


def test_golden_dataset_file_exists() -> None:
    assert GOLDEN_DATASET_PATH.exists()


def test_golden_dataset_has_version_and_items() -> None:
    dataset = load_golden_dataset()

    assert dataset["version"] == 1
    assert isinstance(dataset["items"], list)
    assert len(dataset["items"]) >= 20


def test_golden_dataset_item_ids_are_unique() -> None:
    dataset = load_golden_dataset()

    ids = [item["id"] for item in dataset["items"]]

    assert len(ids) == len(set(ids))


def test_golden_dataset_items_have_required_fields() -> None:
    dataset = load_golden_dataset()

    for item in dataset["items"]:
        missing_fields = REQUIRED_ITEM_FIELDS - set(item)

        assert missing_fields == set(), (
            f"Item {item.get('id', '<no id>')} "
            f"has missing fields: {missing_fields}"
        )


def test_golden_dataset_has_enough_categories_and_hard_cases() -> None:
    dataset = load_golden_dataset()

    categories = {
        item["category"]
        for item in dataset["items"]
    }
    hard_items = [
        item
        for item in dataset["items"]
        if item["difficulty"] == "hard"
    ]

    assert len(categories) >= 3
    assert len(hard_items) >= 3


def test_golden_dataset_expected_keywords_are_non_empty_lists() -> None:
    dataset = load_golden_dataset()

    for item in dataset["items"]:
        assert isinstance(item["expected_keywords"], list), item["id"]
        assert len(item["expected_keywords"]) > 0, item["id"]

        for keyword in item["expected_keywords"]:
            assert isinstance(keyword, str), item["id"]
            assert keyword.strip(), item["id"]


def test_golden_dataset_difficulty_values_are_valid() -> None:
    dataset = load_golden_dataset()

    for item in dataset["items"]:
        assert item["difficulty"] in ALLOWED_DIFFICULTIES, item["id"]


def test_golden_dataset_has_no_duplicate_categories_by_accident() -> None:
    """
    Этот тест не запрещает повторяющиеся категории.

    Он просто помогает увидеть распределение категорий,
    если тест упадёт в будущем из-за пустого dataset.
    """
    dataset = load_golden_dataset()

    categories = Counter(
        item["category"]
        for item in dataset["items"]
    )

    assert sum(categories.values()) == len(dataset["items"])