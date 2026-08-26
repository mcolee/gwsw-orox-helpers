"""Gedeelde fixtures: een geladen voorbeelddataset op basis van een eigen fixture."""

from pathlib import Path

import pytest

from gwsw_orox_helpers.dataset import GwswDataset, load_dataset

TTL_DIR = Path(__file__).parent / "fixtures" / "ttl"


@pytest.fixture(scope="session")
def voorbeeld() -> GwswDataset:
    """Sessiebrede referentiedataset, geladen met de gebundelde ontologie."""
    return load_dataset(TTL_DIR / "dataset_voorbeeld.ttl")
