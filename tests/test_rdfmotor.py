"""Tests voor `rdfmotor`: de ene plek waar deze package pyoxigraph aanroept.

Twee dingen worden hier bewaakt. Ten eerste dat de adapter een **doorgeefluik** is:
dezelfde quads, dezelfde bytes en dezelfde uitzonderingen als een rechtstreekse
`pyoxigraph.parse` / `pyoxigraph.serialize`. Zou hij onderweg iets omzetten of een fout
opvangen, dan verandert het gedrag van `bestand._parse`, `schrijven.lees_orox` en
`schrijf_orox_quads` -- en die drie dragen contractvaste foutmeldingen.

Ten tweede de versiepoort. De cap in `pyproject.toml` (`pyoxigraph>=0.5,<0.6`) houdt een
verse install binnen de getoetste reeks; hij kan omzeild worden (`pip install --no-deps`,
een conda-omgeving, een handmatige upgrade), en dan hoort er een leesbare fout te komen
en geen rauwe `TypeError` diep in de quadstroom.
"""

from __future__ import annotations

import ast
import importlib
import tomllib
from collections.abc import Iterable, Iterator
from pathlib import Path

import pyoxigraph
import pytest

from gwsw_orox_helpers import rdfmotor
from gwsw_orox_helpers.errors import DatasetError

WORTEL = Path(__file__).resolve().parents[1]
TTL_DIR = Path(__file__).parent / "fixtures" / "ttl"
MINI = TTL_DIR / "mini_orox.ttl"


def _genormaliseerd(quads: Iterable[pyoxigraph.Quad]) -> list[str]:
    """De quads als tekst, met blanke knopen op volgorde van eerste verschijning.

    pyoxigraph mint bij elke lezing nieuwe labels voor blanke knopen, dus twee lezingen
    van dezelfde bron leveren letterlijk verschillende teksten op. De *n*-de nieuwe
    blanke knoop is in beide lezingen wel dezelfde knoop -- de stroomvolgorde ligt vast --
    dus hernummeren maakt de twee vergelijkbaar zonder de structuur weg te gooien.
    """
    namen: dict[str, str] = {}
    regels: list[str] = []
    for quad in quads:
        delen: list[str] = []
        for term in (quad.subject, quad.predicate, quad.object):
            if isinstance(term, pyoxigraph.BlankNode):
                delen.append(namen.setdefault(term.value, f"_:b{len(namen)}"))
            else:
                delen.append(str(term))
        regels.append(" ".join(delen))
    return regels


def test_ontleed_turtle_uit_bytes_geeft_dezelfde_quads() -> None:
    """De bytesweg: wat `bestand._parse` doet met de al gedecodeerde tekst."""
    rauw = MINI.read_bytes()
    verwacht = _genormaliseerd(pyoxigraph.parse(rauw, format=pyoxigraph.RdfFormat.TURTLE))

    assert _genormaliseerd(rdfmotor.ontleed_turtle(rauw)) == verwacht
    assert len(verwacht) == 55  # de fixture, zodat een lege vergelijking niet slaagt


def test_ontleed_turtle_uit_tekst_geeft_dezelfde_quads() -> None:
    """De tekstweg: wat `schrijven.lees_orox` doet met een terugvalcodering."""
    tekst = MINI.read_text(encoding="utf-8")
    verwacht = _genormaliseerd(pyoxigraph.parse(tekst, format=pyoxigraph.RdfFormat.TURTLE))

    assert _genormaliseerd(rdfmotor.ontleed_turtle(tekst)) == verwacht


def test_ontleed_turtle_bestand_geeft_dezelfde_quads_en_prefixen() -> None:
    """De padweg: de parser leest streamend van schijf en draagt de bronprefixen.

    `lees_orox` leunt op allebei -- de stroom én `parser.prefixes` na de eerste quad --
    dus de adapter moet het echte parserobject teruggeven en niet een kale iterator.
    """
    verwacht = _genormaliseerd(pyoxigraph.parse(path=MINI, format=pyoxigraph.RdfFormat.TURTLE))
    parser = rdfmotor.ontleed_turtle_bestand(MINI)
    gekregen = _genormaliseerd(parser)

    assert gekregen == verwacht
    assert parser.prefixes[""] == "http://sparql.gwsw.nl/repositories/Mini#"


def test_een_str_pad_leest_het_bestand_en_niet_de_padtekst() -> None:
    """`ontleed_turtle_bestand` geeft zijn argument altijd als `path=` door.

    Dit is waarom het een eigen functie is en geen `isinstance(bron, Path)`-tak in
    `ontleed_turtle`. `lees_orox` gaf vóór deze module altijd `path=bron` door en
    pyoxigraph accepteert daar ook een `str`; met een typeswitch zou zo'n pad in de
    inhoudstak vallen en zou de *padtekst* als Turtle ontleed worden -- 0 quads en een
    misleidende "geen geldige Turtle" in plaats van de 55 van het bestand.
    """
    assert len(_genormaliseerd(rdfmotor.ontleed_turtle_bestand(str(MINI)))) == 55  # type: ignore[arg-type]


def test_serialiseer_turtle_schrijft_dezelfde_bytes(tmp_path: Path) -> None:
    """Dezelfde quads en dezelfde prefixkop geven byte-gelijke uitvoer.

    Eén parse voor allebei: blanke-knooplabels zijn per lezing anders en zouden het
    verschil anders verklaren zonder dat er iets aan de schrijfkant veranderde.
    """
    quads = list(pyoxigraph.parse(path=MINI, format=pyoxigraph.RdfFormat.TURTLE))
    kop = {"gwsw": "http://data.gwsw.nl/1.6/totaal/", "": "http://sparql.gwsw.nl/x#"}

    rechtstreeks = tmp_path / "rechtstreeks.ttl"
    with open(rechtstreeks, "wb") as bestand:
        pyoxigraph.serialize(quads, bestand, pyoxigraph.RdfFormat.TURTLE, prefixes=kop)
    via_adapter = tmp_path / "adapter.ttl"
    with open(via_adapter, "wb") as bestand:
        rdfmotor.serialiseer_turtle(quads, bestand, prefixen=kop)

    assert via_adapter.read_bytes() == rechtstreeks.read_bytes()
    assert b"@prefix gwsw:" in via_adapter.read_bytes()


def test_serialiseer_turtle_geeft_een_fout_uit_de_stroom_ongemoeid_door(tmp_path: Path) -> None:
    """De adapter vangt niets af: een luie bron die afbreekt komt onveranderd boven.

    `schrijf_orox_quads` bouwt daarop -- een `DatasetError` uit `_gecontroleerd` moet de
    afnemer bereiken, en de tijdelijke-bestandsopruiming eromheen moet aan de beurt komen.
    """

    def stroom() -> Iterator[pyoxigraph.Quad]:
        yield from pyoxigraph.parse(path=MINI, format=pyoxigraph.RdfFormat.TURTLE)
        raise DatasetError("de bron breekt af")

    with (
        open(tmp_path / "half.ttl", "wb") as bestand,
        pytest.raises(DatasetError, match="breekt af"),
    ):
        rdfmotor.serialiseer_turtle(stroom(), bestand, prefixen={})


def test_een_syntaxfout_komt_als_pyoxigraph_fout_uit_de_adapter(tmp_path: Path) -> None:
    """De adapter vertaalt parsefouten niet; dat doen `inlezen` en `schrijven` zelf.

    Zou hij hier al een `DatasetError` maken, dan zou `bestand._parse` die in zijn
    `except Exception` opnieuw inpakken ("geen geldige Turtle (...)") en stond de
    boodschap er twee keer in.
    """
    stuk = tmp_path / "stuk.ttl"
    stuk.write_text("@prefix : <http://x#> .\n:a :b :c .\n:d :e\n", encoding="utf-8")

    with pytest.raises(SyntaxError):
        list(rdfmotor.ontleed_turtle_bestand(stuk))
    with pytest.raises(SyntaxError):
        list(rdfmotor.ontleed_turtle(stuk.read_bytes()))


def test_een_ontbrekend_bestand_komt_als_oserror_uit_de_adapter(tmp_path: Path) -> None:
    """`lees_orox` vangt `OSError` af om er "kan niet gelezen worden" van te maken."""
    with pytest.raises(OSError):
        rdfmotor.ontleed_turtle_bestand(tmp_path / "bestaat_niet.ttl")


def test_alleen_rdfmotor_roept_de_motor_aan() -> None:
    """De naad is er één: buiten `rdfmotor` staat geen `pyoxigraph.parse`/`serialize`.

    Zonder deze sweep is "één naad" een belofte in een docstring en belet niets een
    vijfde aanroep; dan is de een-naadswijziging waar issue #18 om vroeg na de volgende
    module weer een zoektocht. Aan de **AST** en niet aan een grep, net als
    `test_de_clipsubmodules_houden_de_importrichting`: een aanroep verderop in een regel,
    een `from pyoxigraph import parse` en een aanroep binnen een functie glippen alle drie
    langs een regelgericht patroon.

    De term-fabrieken vallen er met opzet buiten -- `pyoxigraph.NamedNode` en zijn
    zusters mogen overal staan (zie de moduledocstring van `rdfmotor`); alleen `parse` en
    `serialize` horen bij de naad.
    """
    pakket = Path(rdfmotor.__file__ or "").parent
    overtreders: list[str] = []
    for pad in sorted(pakket.rglob("*.py")):
        if pad.name == "rdfmotor.py" or "__pycache__" in pad.parts:
            continue
        for knoop in ast.walk(ast.parse(pad.read_text(encoding="utf-8"))):
            if (
                isinstance(knoop, ast.Attribute)
                and knoop.attr in {"parse", "serialize"}
                and isinstance(knoop.value, ast.Name)
                and knoop.value.id == "pyoxigraph"
            ):
                overtreders.append(f"{pad.name}:{knoop.lineno}: pyoxigraph.{knoop.attr}")
            elif isinstance(knoop, ast.ImportFrom) and knoop.module == "pyoxigraph":
                overtreders += [
                    f"{pad.name}:{knoop.lineno}: from pyoxigraph import {alias.name}"
                    for alias in knoop.names
                    if alias.name in {"parse", "serialize"}
                ]

    assert overtreders == [], (
        f"{overtreders} roept pyoxigraph rechtstreeks aan; de parse/serialize-naad hoort "
        "in `gwsw_orox_helpers.rdfmotor` te blijven (issue #18)."
    )


@pytest.mark.parametrize("versie", ["0.5.0", "0.5.9", "0.5.99", "0.5.0rc1", "0.5"])
def test_een_versie_binnen_de_reeks_gaat_door(versie: str) -> None:
    assert rdfmotor.controleer_versie(versie) is None


@pytest.mark.parametrize("versie", ["0.4.9", "0.0.1", "0.6.0", "0.7.0", "1.0.0"])
def test_een_versie_buiten_de_reeks_is_een_leesbare_dataseterror(versie: str) -> None:
    """De reeks en de gevonden versie staan allebei in de boodschap.

    Dit is de zachte landing achter de cap in `pyproject.toml`: wie hem omzeilt, krijgt
    hier te horen wat er staat, wat er verwacht wordt en waar hij dat aanpast.
    """
    with pytest.raises(DatasetError) as fout:
        rdfmotor.controleer_versie(versie)

    boodschap = str(fout.value)
    assert versie in boodschap
    assert rdfmotor.ONDERSTEUNDE_REEKS in boodschap
    assert "pyproject.toml" in boodschap


@pytest.mark.parametrize("versie", ["", "kapot", "nul.vijf", "0"])
def test_een_onleesbare_versie_is_ook_een_dataseterror(versie: str) -> None:
    """Doorgaan op een motor die zich niet laat identificeren is precies wat we niet doen."""
    with pytest.raises(DatasetError, match="geen major.minor uit te lezen"):
        rdfmotor.controleer_versie(versie)


def test_de_versiepoort_staat_aan_bij_het_importeren(monkeypatch: pytest.MonkeyPatch) -> None:
    """De check is niet alleen gedefinieerd maar ook aangesloten -- één keer, bij import.

    Bij import en niet per aanroep, om twee redenen. Het kost dan niets in de hete lus,
    en de fout valt vóór het eerste bestand: aan de aanroepkant zou hij in de
    `except Exception` van `bestand._parse` belanden en als "geen geldige Turtle"
    naar buiten komen -- precies de misleiding die dit issue wegneemt.
    """
    monkeypatch.setattr(pyoxigraph, "__version__", "0.6.0")
    try:
        with pytest.raises(DatasetError, match="0.6.0"):
            importlib.reload(rdfmotor)
    finally:
        monkeypatch.undo()
        importlib.reload(rdfmotor)

    assert rdfmotor.controleer_versie(pyoxigraph.__version__) is None


def test_de_reeks_is_dezelfde_als_de_cap_in_pyproject() -> None:
    """De poort en de cap horen hetzelfde te zeggen; anders bewaakt de een de ander niet.

    De cap voorkomt de installatie, de poort vangt een omzeilde cap. Drijven ze uit
    elkaar, dan meldt de poort een reeks die niemand meer installeert (of andersom).
    """
    pyproject = tomllib.loads((WORTEL / "pyproject.toml").read_text(encoding="utf-8"))
    afhankelijkheden = pyproject["project"]["dependencies"]
    pin = next(regel for regel in afhankelijkheden if regel.startswith("pyoxigraph"))

    assert pin == f"pyoxigraph{rdfmotor.ONDERSTEUNDE_REEKS}", (
        "de versiereeks in `rdfmotor` en de cap in pyproject.toml lopen uiteen; werk ze samen bij."
    )
