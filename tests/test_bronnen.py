"""De gebundelde ontologie en index zijn als resource bereikbaar en consistent."""

import json
from pathlib import Path

from gwsw_orox_helpers.bronnen import gebundelde_ontologie, vocabulaire_index_pad
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


def test_load_dataset_gebruikt_standaard_de_gebundelde_ontologie() -> None:
    dataset = load_dataset(TTL_DIR / "codering_cp850.ttl", fallback_encoding="cp850")
    assert dataset.klassenhierarchie_bekend


def test_lege_lijst_betekent_geen_ontologie() -> None:
    dataset = load_dataset(
        TTL_DIR / "codering_cp850.ttl", ontology_paths=[], fallback_encoding="cp850"
    )
    assert not dataset.klassenhierarchie_bekend


def test_de_cachesleutel_ziet_dezelfde_standaard() -> None:
    """De cache hasht de bestanden die de lezing werkelijk gebruikt.

    Zou de sleutel de gebundelde ontologie missen, dan gaf de cache na het vervangen
    van die ontologie de oude lezing terug -- en juist zonder opgave gebeurt dat stil.
    """
    ttl = TTL_DIR / "codering_cp850.ttl"

    assert cachesleutel(ttl) == cachesleutel(ttl, [gebundelde_ontologie()])
    assert cachesleutel(ttl) != cachesleutel(ttl, [])
