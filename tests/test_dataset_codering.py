"""Tests voor het lezen van een OroX-export die geen geldige UTF-8 is."""

from __future__ import annotations

from pathlib import Path

import pytest

from gwsw_orox_helpers.dataset import load_dataset
from gwsw_orox_helpers.errors import DatasetError

TTL_DIR = Path(__file__).parent / "fixtures" / "ttl"


def test_utf8_bestand_meldt_geen_terugval() -> None:
    dataset = load_dataset(TTL_DIR / "schoon.ttl", ontology_paths=[])

    assert dataset.decode_fallback is None


def test_cp850_bestand_wordt_gelezen_en_vastgelegd() -> None:
    # Turtle hoort UTF-8 te zijn; de BrutIS-export van De Wolden en Hoogeveen is dat niet.
    # De package kent geen standaardcodering: de afnemer geeft er zelf een op.
    dataset = load_dataset(
        TTL_DIR / "codering_cp850.ttl", ontology_paths=[], fallback_encoding="cp850"
    )
    fallback = dataset.decode_fallback

    assert fallback is not None
    assert fallback.encoding == "cp850"
    assert fallback.byte_count == 1
    assert any("cavaljéweg" in sample for sample in fallback.samples)
    # De rest van de dataset is gewoon bruikbaar.
    assert len(dataset.conduits) == 1


def test_eigen_terugvalcodering(tmp_path: Path) -> None:
    # Met cp1252 levert dezelfde byte een ander teken op; de keuze is expliciet.
    dataset = load_dataset(
        TTL_DIR / "codering_cp850.ttl", ontology_paths=[], fallback_encoding="cp1252"
    )

    assert dataset.decode_fallback.encoding == "cp1252"
    assert not any("cavaljéweg" in sample for sample in dataset.decode_fallback.samples)


def test_onleesbare_codering_geeft_dataseterror(tmp_path: Path) -> None:
    stuk = tmp_path / "stuk.ttl"
    stuk.write_bytes(b"@prefix : <http://x#> .\n:a :b \x82 .\n")

    with pytest.raises(DatasetError, match="geen geldige UTF-8"):
        load_dataset(stuk, fallback_encoding="onbekende-codering")
