"""De gebundelde index is exact wat de generator uit de gebundelde ontologie maakt."""

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType

from gwsw_orox_helpers.bronnen import gebundelde_ontologie, vocabulaire_index_pad

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


def test_index_volgt_de_ontologie() -> None:
    """De gebundelde index is bij tot en met de ontologie die ernaast ligt.

    Dit is de test die voorkomt dat de index stil veroudert zodra de auteur GWSW 1.7
    neerzet. De hele bestandstekst wordt vergeleken en niet alleen de termen, zodat
    ook de meegedragen `owl:versionInfo` en de opmaak niet uit de pas kunnen lopen.
    Beide bestanden reizen met de package mee, dus deze test draait ook op CI.
    """
    generator = _generator()

    assert generator.DOEL.read_text(encoding="utf-8") == generator.documenttekst(
        generator.ONTOLOGIE
    ), (
        f"{generator.DOEL.relative_to(WORTEL)} loopt achter op "
        f"{generator.ONTOLOGIE.relative_to(WORTEL)}.\n"
        "Draai: uv run python scripts/maak_gwsw_index.py"
    )


def test_de_generator_schrijft_de_gebundelde_bestanden() -> None:
    """Het script wijst naar dezelfde bestanden als `bronnen`.

    Zonder deze test kan de generator ongemerkt een ander paar bestanden bijwerken dan
    de package uitlevert, en dan bewaakt de drifttest hierboven een index die niemand
    leest.
    """
    generator = _generator()

    assert generator.ONTOLOGIE == gebundelde_ontologie()
    assert generator.DOEL == vocabulaire_index_pad()


def test_indexversie_staat_in_claude_md() -> None:
    """De index en `CLAUDE.md` dragen dezelfde GWSW-versie.

    De drifttest hierboven bewaakt maar één richting: `CLAUDE.md` bijwerken zonder het
    script te draaien valt om. De omgekeerde richting -- het script draaien op 1.7
    terwijl `CLAUDE.md` nog 1.6 zegt -- merkt niemand, en dan is `CLAUDE.md` niet langer
    "de enige plek waar hij staat".

    Alleen het `versie=X.Y`-deel wordt vergeleken en niet de hele regel: de
    conversiedatum erachter hoort bij de ontologie en niet bij de projectafspraak. De
    versieregel komt uit de index, die hem letterlijk uit de `owl:versionInfo` van de
    gebundelde ontologie overneemt (`versie_uit_graaf`).
    """
    versieregel = json.loads(vocabulaire_index_pad().read_text(encoding="utf-8"))["gwsw_versie"]
    gevonden = re.search(r"versie=[0-9]+(?:\.[0-9]+)*", versieregel)

    assert gevonden is not None, f"geen versie= in {versieregel!r}"
    assert gevonden.group() in (WORTEL / "CLAUDE.md").read_text(encoding="utf-8"), (
        f"{vocabulaire_index_pad().name} draagt {gevonden.group()}, maar CLAUDE.md noemt die "
        "versie niet. CLAUDE.md is de gezaghebbende plek; werk de regel over de leidende "
        "GWSW-versie bij."
    )
