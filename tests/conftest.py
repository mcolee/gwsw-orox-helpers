"""Gedeelde fixtures: een geladen voorbeelddataset op basis van een eigen fixture."""

import os
from pathlib import Path

import pytest

from gwsw_orox_helpers.dataset import GwswDataset, load_dataset

TTL_DIR = Path(__file__).parent / "fixtures" / "ttl"

# De relatieve ligging van de grote, niet-getrackte export onder de thuismap van de auteur.
# Op één plek zodat de `zwaar`-tests en de benchmarkscripts hem niet elk hard hoeven te
# spellen (issue #44).
_EXPORT_ONDER_HOME = Path("nlriochecker/data/gwsw_orox_ttl/dewoldenhoogeveen_orox.ttl")


def dewoldenhoogeveen_export() -> Path:
    """Het pad naar de 112 MB-export van De Wolden en Hoogeveen (niet in de repo).

    Standaard onder de thuismap; te overschrijven met de omgevingsvariabele
    `GWSW_OROX_FIXTUREPAD`, zodat het pad niet hard in de broncode staat. De `zwaar`-tests
    die deze export nodig hebben, slaan zichzelf net als voorheen over als hij niet bestaat.
    """
    override = os.environ.get("GWSW_OROX_FIXTUREPAD")
    return Path(override) if override else Path.home() / _EXPORT_ONDER_HOME


@pytest.fixture(scope="session")
def voorbeeld() -> GwswDataset:
    """Sessiebrede referentiedataset, geladen met de gebundelde ontologie."""
    return load_dataset(TTL_DIR / "dataset_voorbeeld.ttl")
