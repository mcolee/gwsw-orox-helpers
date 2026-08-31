"""Elke gegenereerde fixture op schijf is exact wat de generator maakt, per versie."""

import importlib.util
from pathlib import Path

import pytest

WORTEL = Path(__file__).resolve().parents[1]


def _generator():
    spec = importlib.util.spec_from_file_location(
        "maak_fixtures", WORTEL / "scripts" / "maak_fixtures.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


GENERATOR = _generator()

# Elke versie krijgt haar eigen fixtureset (1.6 in ttl/, 1.7 in ttl17/). De drift wordt
# per versie tegen de generator gehouden, zodat de 1.7-set net zo bewaakt is als de 1.6-set.
GEVALLEN = [(versie, naam) for versie in GENERATOR.VERSIES for naam in sorted(GENERATOR.FIXTURES)]


@pytest.mark.parametrize(("versie", "naam"), GEVALLEN)
def test_fixture_volgt_de_generator(versie: str, naam: str) -> None:
    defect, inhoud = GENERATOR.FIXTURES[naam]
    doel = GENERATOR.doel_voor(versie)
    assert (doel / naam).read_text(encoding="utf-8") == GENERATOR.render(defect, inhoud, versie)
