"""Tests voor de herkomst van de maaiveldhoogte.

De BrutIS-export van De Wolden en Hoogeveen hangt een record-brede inwinningswijze aan het
Punt-aspect van een orientatie en herhaalt hem op het kenmerk zelf. Bij AHN2
blijft die herhaling uit: in de hele De Wolden en Hoogeveen-export komt AHN2 5104 keer voor op
het Punt van een maaiveldorientatie en geen enkele keer op de maaiveldhoogte.
Zonder terugval op het Punt zou de helft van de maaiveldhoogten als herkomstloos
gelden, terwijl juist die helft uit hetzelfde hoogtemodel komt als het AHN.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from gwsw_orox_helpers.dataset import Inwinning, load_dataset

TTL_DIR = Path(__file__).parent / "fixtures" / "ttl"
SCENARIO = TTL_DIR / "ext_scenario.ttl"
MET_DATUM = TTL_DIR / "dataset_inwinningsdatum.ttl"


def _node(dataset, label: str):
    """De knoop met dit label."""
    return next(node for node in dataset.nodes.values() if node.label == label)


def test_wijze_op_het_punt_telt_als_herkomst_van_de_maaiveldhoogte() -> None:
    dataset = load_dataset(SCENARIO, ontology_paths=[])

    node = _node(dataset, "B")

    assert node.maaiveld == 10.1
    # De maaiveldhoogte zelf draagt geen inwinning; het Punt van de orientatie wel.
    assert node.maaiveld_aspect.inwinning is None
    assert node.maaiveld_inwinning is not None
    assert node.maaiveld_inwinning.wijze == "AHN2"


def test_zonder_inwinning_blijft_de_herkomst_leeg() -> None:
    dataset = load_dataset(SCENARIO, ontology_paths=[])

    assert _node(dataset, "A").maaiveld_inwinning is None


def test_andere_wijze_wordt_ook_gelezen() -> None:
    dataset = load_dataset(SCENARIO, ontology_paths=[])

    assert _node(dataset, "C").maaiveld_inwinning.wijze == "Inmeting"


def test_de_maaiveldorientatie_wordt_geen_knooppunt() -> None:
    """Een maaiveldorientatie met puntgeometrie is geen knoop in het netwerk."""
    dataset = load_dataset(SCENARIO, ontology_paths=[])

    assert not any(uri.endswith("_maa") for uri in dataset.nodes)


# --- De datumhelft van de inwinning (issue #16) ----------------------------------------
#
# `Inwinning` heeft twee velden en tot nu toe droeg geen enkele fixture het tweede: de
# datum kwam nergens uit een TTL terug. `inlezen._read_inwinning` leest hem wel, en de
# omzetting loopt via `domein._as_date`.


def test_de_datum_van_inwinning_wordt_gelezen() -> None:
    """Het GWSW hangt WijzeVanInwinning en DatumInwinning onder dezelfde Inwinning.

    Beide horen bij het kenmerk terug te komen. Bleef de datumhelft ongelezen, dan
    stond overal `datum=None` -- een publiek veld dat er altijd leeg uitziet is niet te
    onderscheiden van een export die de datum niet levert, en geen enkele check zou
    erover klagen.
    """
    dataset = load_dataset(MET_DATUM, ontology_paths=[])

    put = _node(dataset, "A")

    assert put.dekselniveau == 9.85
    assert put.deksel_inwinning == Inwinning(wijze="Inmeting", datum=date(2019, 5, 17))
    # Dezelfde inwinning hangt aan het kenmerk zelf; `_herkomst` hoeft niet terug te
    # vallen op de puntgeometrie.
    assert put.deksel_aspect is not None
    assert put.deksel_aspect.inwinning == put.deksel_inwinning


def test_een_inwinning_met_alleen_een_datum_telt_ook() -> None:
    """`Inwinning.__bool__` is waar zodra er iets ingevuld is, ook zonder wijze.

    `_read_inwinning` geeft alleen een gevulde inwinning terug (`if gevonden`). Telde
    de datum daar niet mee, dan viel de herkomst van zo'n kenmerk stil weg en was "geen
    herkomst bekend" niet te onderscheiden van "wel ingewonnen, wijze niet vastgelegd".
    """
    dataset = load_dataset(MET_DATUM, ontology_paths=[])

    put = _node(dataset, "B")

    assert put.deksel_inwinning == Inwinning(wijze=None, datum=date(2020, 11, 2))
    assert bool(put.deksel_inwinning) is True
