"""Elke gebundelde index is exact wat de generator uit haar eigen ontologie maakt."""

import importlib.util
import json
import pickle
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

from gwsw_orox_helpers import laden as laden_module
from gwsw_orox_helpers.bestand import _parse
from gwsw_orox_helpers.bronnen import (
    GEBUNDELDE_VERSIES,
    gebundelde_graafindex_hash_pad_voor,
    gebundelde_graafindex_pad_voor,
    gebundelde_ontologie_voor,
    vocabulaire_index_pad_voor,
)
from gwsw_orox_helpers.laden import _gebundelde_graafindex, _graafindex_hash

WORTEL = Path(__file__).resolve().parents[1]
INDEXSCRIPT = WORTEL / "scripts" / "maak_gwsw_index.py"


def _generator() -> ModuleType:
    """Importeert `scripts/maak_gwsw_index.py` als module.

    De drifttest bouwt de index met precies dezelfde code als het script; een
    nagebouwde parser hier zou vroeg of laat iets anders opleveren dan wat er in het
    bestand staat, en dan meet de test zichzelf.
    """
    spec = importlib.util.spec_from_file_location("maak_gwsw_index", INDEXSCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["maak_gwsw_index"] = module
    spec.loader.exec_module(module)
    return module


def _bundels() -> list:
    """De bundels zoals de generator ze kent (16 en 17)."""
    return list(_generator().BUNDELS)


@pytest.mark.parametrize("versie", list(GEBUNDELDE_VERSIES))
def test_index_volgt_de_ontologie(versie: str) -> None:
    """Elke gebundelde index is bij tot en met de ontologie die ernaast ligt.

    Dit is de test die voorkomt dat een index stil veroudert zodra de auteur een nieuwe
    GWSW-versie neerzet -- per versie, want elke index volgt zijn eigen bundel. De hele
    bestandstekst wordt vergeleken en niet alleen de termen, zodat ook de meegedragen
    `owl:versionInfo`, de basis en de opmaak niet uit de pas kunnen lopen. Beide
    bestanden reizen met de package mee, dus deze test draait ook op CI.
    """
    generator = _generator()
    (bundel,) = [b for b in generator.BUNDELS if b.versie == versie]

    assert bundel.doel.read_text(encoding="utf-8") == generator.documenttekst(bundel.ontologie), (
        f"{bundel.doel.relative_to(WORTEL)} loopt achter op "
        f"{bundel.ontologie.relative_to(WORTEL)}.\n"
        "Draai: uv run python scripts/maak_gwsw_index.py"
    )


def test_de_generator_schrijft_de_gebundelde_bestanden() -> None:
    """Het script wijst per versie naar dezelfde bestanden als `bronnen`.

    Zonder deze test kan de generator ongemerkt een ander stel bestanden bijwerken dan
    de package uitlevert, en dan bewaakt de drifttest hierboven indexen die niemand
    leest.
    """
    bundels = {bundel.versie: bundel for bundel in _bundels()}

    assert set(bundels) == set(GEBUNDELDE_VERSIES)
    for versie, bundel in bundels.items():
        assert bundel.ontologie == gebundelde_ontologie_voor(versie)
        assert bundel.doel == vocabulaire_index_pad_voor(versie)


@pytest.mark.parametrize("versie", list(GEBUNDELDE_VERSIES))
def test_indexversie_staat_in_claude_md(versie: str) -> None:
    """Elke index en `CLAUDE.md` dragen dezelfde GWSW-versie -- per versie.

    De drifttest hierboven bewaakt maar één richting: `CLAUDE.md` bijwerken zonder het
    script te draaien valt om. De omgekeerde richting -- het script draaien terwijl
    `CLAUDE.md` de versie nog niet noemt -- merkt niemand, en dan is `CLAUDE.md` niet
    langer "de enige plek waar hij staat". Elke gebundelde index bindt daarom zijn
    eigen `versie=`-regel aan `CLAUDE.md`.

    Alleen het `versie=X.Y`-deel wordt vergeleken en niet de hele regel: de
    conversiedatum erachter hoort bij de ontologie en niet bij de projectafspraak. De
    versieregel komt uit de index, die hem letterlijk uit de `owl:versionInfo` van de
    gebundelde ontologie overneemt (`versie_uit_graaf`).
    """
    index = json.loads(vocabulaire_index_pad_voor(versie).read_text(encoding="utf-8"))
    gevonden = re.search(r"versie=[0-9]+(?:\.[0-9]+)*", index["gwsw_versie"])

    assert gevonden is not None, f"geen versie= in {index['gwsw_versie']!r}"
    assert gevonden.group() in (WORTEL / "CLAUDE.md").read_text(encoding="utf-8"), (
        f"{vocabulaire_index_pad_voor(versie).name} draagt {gevonden.group()}, maar CLAUDE.md "
        "noemt die versie niet. CLAUDE.md is de gezaghebbende plek; werk de regel over de "
        "gebundelde GWSW-versies bij."
    )


# --- De gebundelde GraafIndex-pickle (issue #70) --------------------------------------


@pytest.mark.parametrize("versie", list(GEBUNDELDE_VERSIES))
def test_graafindex_pickle_volgt_ttl_en_graaf(versie: str) -> None:
    """De gebundelde GraafIndex-pickle is bij tot en met TTL + `graaf.py` + rdflib (issue #70).

    De lader depickelt de bundel alleen bij een hash-treffer; deze test bindt het gecommitte
    sidecar aan de huidige TTL, `graaf.py` en de rdflib-versie -- de drie ingrediënten van
    `_graafindex_hash`. Loopt een ervan uit de pas zonder dat de pickle opnieuw gebouwd is,
    dan valt de lader stil terug op de parse; deze test maakt dat luid. Draai bij drift:
    uv run python scripts/maak_gwsw_index.py.
    """
    ttl = gebundelde_ontologie_voor(versie)
    pickle_pad = gebundelde_graafindex_pad_voor(versie)
    hash_pad = gebundelde_graafindex_hash_pad_voor(versie)

    assert pickle_pad.exists(), f"{pickle_pad.name} ontbreekt; draai scripts/maak_gwsw_index.py"
    assert hash_pad.exists(), f"{hash_pad.name} ontbreekt; draai scripts/maak_gwsw_index.py"
    assert hash_pad.read_text(encoding="ascii").strip() == _graafindex_hash(ttl), (
        f"{pickle_pad.name} loopt achter op de TTL, graaf.py of de rdflib-versie.\n"
        "Draai: uv run python scripts/maak_gwsw_index.py"
    )


@pytest.mark.parametrize("versie", list(GEBUNDELDE_VERSIES))
def test_de_gebundelde_pickle_leest_dezelfde_index_als_de_parse(versie: str) -> None:
    """De gedepickelde index draagt dezelfde triples en basis als de TTL-parse (issue #70)."""
    ttl = gebundelde_ontologie_voor(versie)

    uit_pickle = _gebundelde_graafindex(ttl)
    assert uit_pickle is not None, "de verse pickle hoort geladen te worden"

    geparst = _parse(ttl, None)[0]
    assert len(uit_pickle) == len(geparst)
    assert uit_pickle.gwsw_basis == geparst.gwsw_basis


def test_een_niet_gebundeld_pad_krijgt_geen_pickle(tmp_path: Path) -> None:
    """Een kopie van de bundel elders is geen gebundelde bundel: parse, geen pickle."""
    kopie = tmp_path / "kopie.ttl"
    kopie.write_bytes(gebundelde_ontologie_voor("1.6").read_bytes())

    assert _gebundelde_graafindex(kopie) is None


def test_hash_mismatch_valt_terug_op_de_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    """Een gewijzigde `graaf.py`/rdflib (hier nagebootst) haalt de pickle uit de poort."""
    monkeypatch.setattr(laden_module, "_graafindex_hash", lambda _pad: "niet-de-echte-hash")

    assert _gebundelde_graafindex(gebundelde_ontologie_voor("1.6")) is None


def test_ontbrekend_sidecar_valt_terug_op_de_parse(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Zonder leesbaar sidecar geen pickle -- de hash is dan niet te vergelijken."""
    monkeypatch.setattr(
        laden_module, "gebundelde_graafindex_hash_pad_voor", lambda _v: tmp_path / "weg.sha256"
    )

    assert _gebundelde_graafindex(gebundelde_ontologie_voor("1.6")) is None


def test_ontbrekende_pickle_valt_terug_op_de_parse(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Een verse hash maar geen pickle-bestand: geen `pickle.load`, gewoon parsen."""
    monkeypatch.setattr(
        laden_module, "gebundelde_graafindex_pad_voor", lambda _v: tmp_path / "weg.pickle"
    )

    assert _gebundelde_graafindex(gebundelde_ontologie_voor("1.6")) is None


def test_onbruikbare_pickle_valt_terug_op_de_parse(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Een beschadigde meegeleverde pickle is geen fout maar een gemiste versnelling.

    De hash klopt (het echte sidecar), de pickle bestaat maar is rommel; `pickle.load` gooit
    en `_gebundelde_graafindex` valt breed terug op None (en dus op de parse).
    """
    rommel = tmp_path / "rommel.pickle"
    rommel.write_bytes(b"\x80\x08 dit is geen geldige pickle")
    monkeypatch.setattr(laden_module, "gebundelde_graafindex_pad_voor", lambda _v: rommel)

    assert _gebundelde_graafindex(gebundelde_ontologie_voor("1.6")) is None


def test_pickle_van_het_verkeerde_type_valt_terug(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Een pickle die laadt maar geen `GraafIndex` oplevert telt ook als onbruikbaar."""
    verkeerd = tmp_path / "verkeerd.pickle"
    verkeerd.write_bytes(pickle.dumps({"geen": "graafindex"}))
    monkeypatch.setattr(laden_module, "gebundelde_graafindex_pad_voor", lambda _v: verkeerd)

    assert _gebundelde_graafindex(gebundelde_ontologie_voor("1.6")) is None
