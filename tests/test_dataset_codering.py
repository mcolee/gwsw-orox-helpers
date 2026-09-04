"""Tests voor het lezen van een OroX-export die geen geldige UTF-8 is."""

from __future__ import annotations

from pathlib import Path

import pytest

from gwsw_orox_helpers import codering
from gwsw_orox_helpers.dataset import load_dataset
from gwsw_orox_helpers.errors import DatasetError

TTL_DIR = Path(__file__).parent / "fixtures" / "ttl"
MINI = TTL_DIR / "mini_orox.ttl"
CP850 = TTL_DIR / "codering_cp850.ttl"


def test_utf8_bestand_meldt_geen_terugval() -> None:
    dataset = load_dataset(TTL_DIR / "schoon.ttl", ontology_paths=[])

    assert dataset.decode_fallback is None


def test_utf8_bom_leest_gelijk_aan_zonder_bom(tmp_path: Path) -> None:
    """Een UTF-8-BOM vooraan maakt een verder geldige export niet onleesbaar (issue #53).

    Sommige exporttools (Windows-editors) schrijven een BOM; die hoort geen `TurtleError`
    op te leveren. `utf-8-sig` in `codering.decodeer` accepteert UTF-8 mét en zonder BOM,
    dus leest de dataset met BOM dezelfde knopen en strengen als zonder, en er valt niets
    terug te melden.
    """
    bom = tmp_path / "mini_bom.ttl"
    bom.write_bytes(b"\xef\xbb\xbf" + MINI.read_bytes())

    zonder = load_dataset(MINI, ontology_paths=[])
    met = load_dataset(bom, ontology_paths=[])

    assert len(met.nodes) == len(zonder.nodes) == 2
    assert len(met.conduits) == len(zonder.conduits)
    assert zonder.decode_fallback is None
    assert met.decode_fallback is None


def test_decodeer_accepteert_utf8_met_en_zonder_bom() -> None:
    """De gedeelde decodeerregel: `utf-8-sig` is een superset van `utf-8` op BOM-loze invoer.

    Dit is het ene punt dat beide paden dekt -- `bestand._decode` (leesweg) en
    `schrijven._gedecodeerd` (schrijfweg) delen deze functie. De BOM verdwijnt uit de tekst
    en er is niets teruggevallen (`None`); zonder BOM verandert er niets.
    """
    pad = Path("mem.ttl")

    assert codering.decodeer(pad, b"\xef\xbb\xbf:a :b :c .", None) == (":a :b :c .", None)
    assert codering.decodeer(pad, b":a :b :c .", None) == (":a :b :c .", None)


def test_bom_loze_terugval_geeft_hetzelfde_verslag() -> None:
    """De terugvalcodering-tak blijft ongewijzigd op een BOM-loze latin-1-bron (issue #53).

    `utf-8-sig` raakt alleen een leidende BOM; een BOM-loze cp850-bron valt nog net zo terug
    als voorheen -- zelfde codering, zelfde afwijkende byte in het verslag.
    """
    rauw = CP850.read_bytes()

    tekst, gebruikt = codering.decodeer(CP850, rauw, "cp850")
    verslag = codering.terugvalverslag(CP850, rauw, "cp850")

    assert gebruikt == "cp850"
    assert "cavaljéweg" in tekst
    assert verslag.encoding == "cp850"
    assert verslag.byte_count == 1
    assert any("cavaljéweg" in sample for sample in verslag.samples)


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
