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

from pathlib import Path

import pytest

from gwsw_orox_helpers import codering, rdfmotor
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
