"""De package kent geen afnemersspecifieke defaults: vulwaardenlijst en encoding zijn parameters."""

import inspect
from pathlib import Path

import pytest

from gwsw_orox_helpers.cache import cachesleutel, laad_met_cache
from gwsw_orox_helpers.dataset import load_dataset, markeer_vulwaarden
from gwsw_orox_helpers.errors import DatasetError

TTL_DIR = Path(__file__).parent / "fixtures" / "ttl"


def test_markeer_vulwaarden_eist_de_kenmerkenlijst() -> None:
    parameters = inspect.signature(markeer_vulwaarden).parameters
    assert parameters["kenmerken"].default is inspect.Parameter.empty


def test_geen_encoding_fallback_zonder_opgave() -> None:
    with pytest.raises(DatasetError):
        load_dataset(TTL_DIR / "codering_cp850.ttl")


def test_encoding_fallback_op_verzoek() -> None:
    dataset = load_dataset(
        TTL_DIR / "codering_cp850.ttl", ontology_paths=[], fallback_encoding="cp850"
    )
    assert dataset.nodes


def test_cachesleutel_draagt_de_encodingkeuze() -> None:
    for functie in (cachesleutel, laad_met_cache):
        parameter = inspect.signature(functie).parameters["fallback_encoding"]
        assert parameter.default is None
