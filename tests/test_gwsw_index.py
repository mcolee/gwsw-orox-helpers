"""Elke gebundelde index is exact wat de generator uit haar eigen ontologie maakt."""

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

from gwsw_orox_helpers.bronnen import (
    GEBUNDELDE_VERSIES,
    gebundelde_ontologie_voor,
    vocabulaire_index_pad_voor,
)

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
