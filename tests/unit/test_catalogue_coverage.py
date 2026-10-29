"""Every active catalogue case ID is referenced by a test marker, and no unknown ID is used."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOGUE = ROOT / "docs" / "Firm_Payments_Test_Scenarios.md"
TESTS = ROOT / "tests"
ID = re.compile(r"\b([A-Z]{3}\d{3})\b")


def catalogue_ids() -> set[str]:
    return set(re.findall(r"^### ([A-Z]{3}\d{3}) ", CATALOGUE.read_text(encoding="utf-8"), re.MULTILINE))


def marked_ids() -> set[str]:
    ids: set[str] = set()
    for path in TESTS.rglob("*.py"):
        for args in re.findall(r"mark\.case\(([^)]*)\)", path.read_text(encoding="utf-8"), re.DOTALL):
            ids.update(ID.findall(args))
    return ids


def test_catalogue_has_151_cases():
    assert len(catalogue_ids()) == 151


def test_every_case_is_marked():
    assert sorted(catalogue_ids() - marked_ids()) == []


def test_no_unknown_case_ids():
    assert sorted(marked_ids() - catalogue_ids()) == []
