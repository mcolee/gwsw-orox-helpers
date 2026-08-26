"""Tests voor de herkomst van de maaiveldhoogte.

De BrutIS-export van De Wolden en Hoogeveen hangt een record-brede inwinningswijze aan het
Punt-aspect van een orientatie en herhaalt hem op het kenmerk zelf. Bij AHN2
blijft die herhaling uit: in de hele De Wolden en Hoogeveen-export komt AHN2 5104 keer voor op
het Punt van een maaiveldorientatie en geen enkele keer op de maaiveldhoogte.
Zonder terugval op het Punt zou de helft van de maaiveldhoogten als herkomstloos
gelden, terwijl juist die helft uit hetzelfde hoogtemodel komt als het AHN.
"""

from __future__ import annotations

from pathlib import Path

from gwsw_orox_helpers.dataset import load_dataset

TTL_DIR = Path(__file__).parent / "fixtures" / "ttl"
SCENARIO = TTL_DIR / "ext_scenario.ttl"


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
