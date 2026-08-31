"""De gebundelde ontologie en index zijn als resource bereikbaar en consistent."""

import json
from pathlib import Path

import pytest

from gwsw_orox_helpers.bronnen import (
    GEBUNDELDE_VERSIES,
    STANDAARD_VERSIE,
    gebundelde_ontologie,
    gebundelde_ontologie_voor,
    vocabulaire_index_pad,
    vocabulaire_index_pad_voor,
)
from gwsw_orox_helpers.cache import cachesleutel
from gwsw_orox_helpers.dataset import load_dataset

TTL_DIR = Path(__file__).parent / "fixtures" / "ttl"


def test_gebundelde_ontologie_bestaat_en_draagt_versie_1_6() -> None:
    pad = gebundelde_ontologie()
    assert pad.exists()
    kop = pad.read_text(encoding="utf-8")[:2000]
    assert "versie=1.6" in kop


def test_index_bestaat_en_is_gevuld() -> None:
    index = json.loads(vocabulaire_index_pad().read_text(encoding="utf-8"))
    assert len(index["termen"]) > 3_000


def test_standaard_is_de_16_bundel() -> None:
    """De handtekeningloze `bronnen`-helpers leveren nog altijd de 1.6-bestanden.

    De default verandert in dit deel niet: 1.6 is de leidende versie en 1.7 komt
    ernaast. Versiedetectie die 1.7 kiest komt in een later deel.
    """
    assert STANDAARD_VERSIE == "1.6"
    assert gebundelde_ontologie() == gebundelde_ontologie_voor("1.6")
    assert vocabulaire_index_pad() == vocabulaire_index_pad_voor("1.6")


def test_gebundelde_17_bundel_bestaat_en_draagt_versie_1_7() -> None:
    pad = gebundelde_ontologie_voor("1.7")
    assert pad.exists()
    kop = pad.read_text(encoding="utf-8")[:2000]
    assert "versie=1.7" in kop


def test_17_index_bestaat_en_draagt_versie_1_7() -> None:
    index = json.loads(vocabulaire_index_pad_voor("1.7").read_text(encoding="utf-8"))
    assert "versie=1.7" in index["gwsw_versie"]
    assert len(index["termen"]) > 3_000


def test_beide_gebundelde_versies_zijn_er() -> None:
    assert GEBUNDELDE_VERSIES == ("1.6", "1.7")
    for versie in GEBUNDELDE_VERSIES:
        assert gebundelde_ontologie_voor(versie).exists()
        assert vocabulaire_index_pad_voor(versie).exists()


def test_onbekende_versie_geeft_valueerror() -> None:
    with pytest.raises(ValueError, match="1.6"):
        gebundelde_ontologie_voor("9.9")
    with pytest.raises(ValueError, match="1.7"):
        vocabulaire_index_pad_voor("9.9")


def test_load_dataset_gebruikt_standaard_de_gebundelde_ontologie() -> None:
    dataset = load_dataset(TTL_DIR / "codering_cp850.ttl", fallback_encoding="cp850")
    assert dataset.klassenhierarchie_bekend


def test_lege_lijst_betekent_geen_ontologie() -> None:
    dataset = load_dataset(
        TTL_DIR / "codering_cp850.ttl", ontology_paths=[], fallback_encoding="cp850"
    )
    assert not dataset.klassenhierarchie_bekend


def test_de_cachesleutel_ziet_alle_gebundelde_versies() -> None:
    """De cache hasht de bestanden die de lezing werkelijk kan gebruiken.

    Zou de sleutel de gebundelde ontologie missen, dan gaf de cache na het vervangen
    van die ontologie de oude lezing terug -- en juist zonder opgave gebeurt dat stil.
    Sinds issue #32 kiest `load_dataset` bij `None` de gebundelde ontologie op de
    gedetecteerde dataset-versie, dus hasht de sleutel bij `None` **alle** gebundelde
    versies -- niet langer alleen de 1.6-bundel.
    """
    ttl = TTL_DIR / "codering_cp850.ttl"
    alle = [gebundelde_ontologie_voor(versie) for versie in GEBUNDELDE_VERSIES]

    assert cachesleutel(ttl) == cachesleutel(ttl, alle)
    assert cachesleutel(ttl) != cachesleutel(ttl, [gebundelde_ontologie()])
    assert cachesleutel(ttl) != cachesleutel(ttl, [])
