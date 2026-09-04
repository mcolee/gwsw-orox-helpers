"""De faalfamilies onder `DatasetError`, elk op een representatieve plek gepind.

Issue #31: één `DatasetError` dekte 29 raise-plekken met wezenlijk andere oorzaken -- een
bestand dat niet open gaat, bytes die geen UTF-8 zijn, Turtle die niet parseert, een
dataset zonder objecten, een grenslaag die geen knipinvoer is, een clip die niet rond
komt, en een pyoxigraph buiten de getoetste reeks. Een afnemer die er alleen
`DatasetError` van zag, kon "de bron is kapot" niet van "de clipdelen zijn incompleet"
onderscheiden. Sinds #31 staan er zeven subklassen onder en pinnen de tests hieronder er
per familie één plek van.

Ze staan hier bij elkaar en niet verspreid over de zeven testbestanden, zodat de indeling
in één schermvol te lezen is. De andere kant wordt juist elders bewaakt: de bestaande
`pytest.raises(DatasetError)` in `test_dataset.py`, `test_schrijven.py`, `test_clip.py`,
`test_rdfmotor.py`, `test_dataset_codering.py` en `test_generieke_parameters.py` bleven
ongewijzigd, en die blijven alleen groen zolang elke familie een `DatasetError` *is* --
precies de belofte waarop nlriochecker met zijn brede `except` leunt.

Welke raise-plek in welke familie hoort, staat in de docstrings van
`gwsw_orox_helpers.errors`; `tests/test_publieke_api.py` pint de hiërarchie zelf.
"""

import ast
from pathlib import Path

import pytest

from gwsw_orox_helpers import codering, errors, rdfmotor
from gwsw_orox_helpers.clip import clip_orox, merge_orox
from gwsw_orox_helpers.dataset import load_dataset
from gwsw_orox_helpers.errors import (
    BestandError,
    CoderingError,
    GrenslaagError,
    InhoudError,
    KnipError,
    MotorError,
    TurtleError,
)
from gwsw_orox_helpers.schrijven import schrijf_orox_quads

TTL_DIR = Path(__file__).parent / "fixtures" / "ttl"
MINI = TTL_DIR / "mini_orox.ttl"

# Welke module welke familie hoeveel keer gooit. Dit is de tabel achter de "Vier plekken:
# ..."-regels in de docstrings van `gwsw_orox_helpers.errors` en achter de aantallen in de
# CHANGELOG-regel van #31, en zonder bewaker is dat precies het soort belofte dat wegslijt:
# een raise-plek erbij verandert de code en laat de docstring staan. Uitgeschreven en niet
# uit de code afgeleid, want een lijst die zichzelf afleidt bewaakt niets.
RAISE_PLEKKEN = {
    "BestandError": {"bestand": 1, "cache": 1, "clip.grenzen": 1, "schrijven": 3},
    "CoderingError": {"codering": 2, "schrijven": 1},
    "GrenslaagError": {"clip.grenzen": 6},
    "InhoudError": {"dataset": 2},
    "KnipError": {"clip.knip": 2, "clip.merge": 5, "clip.orkest": 1, "clip.plan": 1},
    "MotorError": {"rdfmotor": 2},
    "TurtleError": {"bestand": 1, "schrijven": 2},
    # Leeg, en dat is de helft van de belofte die het makkelijkst wegslijt: sinds #31 wordt
    # de basisklasse binnen de package nergens meer rechtstreeks gegooid. Wie een nieuwe
    # raise-plek erbij zet zonder familie, komt hierlangs.
    "DatasetError": {},
}


def test_een_bestand_dat_niet_open_gaat_is_een_bestanderror(tmp_path: Path) -> None:
    """`BestandError`: het besturingssysteem geeft het bestand niet, lezend of schrijvend."""
    with pytest.raises(BestandError, match="kan niet gelezen worden"):
        load_dataset(tmp_path / "bestaat_niet.ttl", ontology_paths=[])


def test_bytes_die_geen_utf8_zijn_zijn_een_coderingerror(tmp_path: Path) -> None:
    """`CoderingError`: de bytes worden geen tekst, en er is geen terugval die dat oplost."""
    with pytest.raises(CoderingError, match="geen geldige UTF-8"):
        codering.decodeer(tmp_path / "bron.ttl", b"\xff", None)


def test_ongeldige_turtle_is_een_turtleerror(tmp_path: Path) -> None:
    """`TurtleError`: de tekst is er wel, maar hij voldoet niet aan de Turtle-grammatica."""
    stuk = tmp_path / "stuk.ttl"
    stuk.write_text("dit is <geen geldige turtle", encoding="utf-8")

    with pytest.raises(TurtleError, match="geen geldige Turtle"):
        load_dataset(stuk, ontology_paths=[])


def test_een_ongeldige_prefixsleutel_is_ook_een_turtleerror(tmp_path: Path) -> None:
    """Dezelfde familie aan de schrijfkant: een prefix die geen PN_PREFIX is.

    De tweede pin op `TurtleError`, want deze plek is de enige waar de familie niet over
    een gelezen bron gaat maar over de kop die geschreven zou worden -- en juist daar zou
    "een OSError-familie" een voor de hand liggende vergissing zijn.
    """
    with pytest.raises(TurtleError, match="geen geldige Turtle-prefix"):
        schrijf_orox_quads([], tmp_path / "uit.ttl", prefixen={"kapot prefix": "http://x#"})


def test_een_dataset_zonder_objecten_is_een_inhouderror(tmp_path: Path) -> None:
    """`InhoudError`: gelezen, geparseerd, en toch niet wat er gevraagd wordt."""
    leeg = tmp_path / "leeg.ttl"
    leeg.write_text("@prefix ex: <http://example.org/> .\nex:a ex:b ex:c .\n", encoding="utf-8")

    with pytest.raises(InhoudError, match="geen knooppunten of strengen"):
        load_dataset(leeg, ontology_paths=[])


def test_een_grenslaag_zonder_vlakken_is_een_grenslaagerror(tmp_path: Path) -> None:
    """`GrenslaagError`: het GeoJSON-bestand is er, maar het is geen knipinvoer."""
    pad = tmp_path / "grens.geojson"
    pad.write_text('{"type": "FeatureCollection", "features": []}', encoding="utf-8")

    with pytest.raises(GrenslaagError, match="geen features"):
        clip_orox(MINI, pad, tmp_path / "uit", sleutel="naam")


def test_een_merge_zonder_delen_is_een_kniperror(tmp_path: Path) -> None:
    """`KnipError`: knippen of herenigen komt niet rond."""
    with pytest.raises(KnipError, match="geen delen opgegeven"):
        merge_orox([], tmp_path / "nooit.ttl")


def test_een_pyoxigraph_buiten_de_reeks_is_een_motorerror() -> None:
    """`MotorError`: niet de invoer deugt niet maar de installatie eronder."""
    with pytest.raises(MotorError, match="valt buiten de reeks"):
        rdfmotor.controleer_versie("0.6.0")


def test_de_raise_plekken_staan_waar_de_docstrings_ze_beloven() -> None:
    """De indeling zelf, mechanisch: elke `raise` in de package, geteld per familie.

    De acht tests hierboven pinnen per familie één plek; die blijven groen terwijl de
    andere 23 plekken ongemerkt van familie wisselen. Deze test loopt de AST van elke
    module af en legt de volledige verdeling naast `RAISE_PLEKKEN`. Valt hij om, dan hoort
    in dezelfde stap de docstring van de betrokken klasse in `gwsw_orox_helpers.errors`
    mee -- die noemt de aantallen en de modules met naam.
    """
    pakket = Path(errors.__file__ or "").parent
    geteld: dict[str, dict[str, int]] = {naam: {} for naam in RAISE_PLEKKEN}
    for pad in sorted(pakket.rglob("*.py")):
        if "__pycache__" in pad.parts:
            continue
        module = ".".join(pad.relative_to(pakket).with_suffix("").parts)
        boom = ast.parse(pad.read_text(encoding="utf-8"))
        for knoop in ast.walk(boom):
            if not isinstance(knoop, ast.Raise) or not isinstance(knoop.exc, ast.Call):
                continue
            soort = knoop.exc.func
            if isinstance(soort, ast.Name) and soort.id in geteld:
                geteld[soort.id][module] = geteld[soort.id].get(module, 0) + 1

    assert geteld == RAISE_PLEKKEN
    # 29 sinds #31, plus de `cache._bestandshash`-plek van #48 (30) en de
    # `schrijven._gecontroleerd`-plek van #49 (31). De moduledocstrings houden de 29 aan als
    # de historische telling van #31 (de oorzaak van de opsplitsing), niet als het lopende
    # totaal -- dat staat hier.
    assert sum(sum(per_module.values()) for per_module in geteld.values()) == 31
