"""Elke gegenereerde fixture op schijf is exact wat de generator maakt."""

import importlib.util
from pathlib import Path

import pytest

WORTEL = Path(__file__).resolve().parents[1]
TTL_DIR = Path(__file__).parent / "fixtures" / "ttl"


def _generator():
    spec = importlib.util.spec_from_file_location(
        "maak_fixtures", WORTEL / "scripts" / "maak_fixtures.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


GENERATOR = _generator()


@pytest.mark.parametrize("naam", sorted(GENERATOR.FIXTURES))
def test_fixture_volgt_de_generator(naam: str) -> None:
    defect, inhoud = GENERATOR.FIXTURES[naam]
    assert (TTL_DIR / naam).read_text(encoding="utf-8") == GENERATOR.render(defect, inhoud)
