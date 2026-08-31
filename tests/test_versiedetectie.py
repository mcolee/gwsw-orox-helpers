"""Versiedetectie en de versie-afgeleide termenset (issue #32, deel c).

De leeslaag en de cliplaag leiden hun predicaten sinds issue #32 af uit de gedetecteerde
GWSW-basis van de bron. Hier staan de bouwstenen daarvan: het uit elkaar halen van een
basis-IRI, de termenset per basis en de twee detectiewegen (de `gwsw:`-prefix en de scan
over de IRI's). De doortrekking in de lees- en cliplaag zelf staat in `test_dataset.py`,
`test_ontologie.py` en `test_clip.py`.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from gwsw_orox_helpers import namen
from gwsw_orox_helpers.bestand import _parse

BASIS_16 = "http://data.gwsw.nl/1.6/totaal/"
BASIS_17 = "http://data.gwsw.nl/1.7/totaal/"

TTL16 = Path(__file__).parent / "fixtures" / "ttl" / "dataset_voorbeeld.ttl"
TTL17 = Path(__file__).parent / "fixtures" / "ttl17" / "dataset_voorbeeld.ttl"


def test_de_gepinde_constanten_blijven_16() -> None:
    """De module-constanten zijn het bevroren contract en veranderen niet."""
    assert namen.GWSW == BASIS_16
    assert namen.HAS_ASPECT == f"{BASIS_16}hasAspect"
    assert namen.HAS_VALUE == f"{BASIS_16}hasValue"


def test_termen_16_is_gelijk_aan_de_constanten() -> None:
    """De default-termenset spelt precies de gepinde 1.6-properties."""
    assert namen.TERMEN_16.basis == namen.GWSW
    assert namen.TERMEN_16.has_aspect == namen.HAS_ASPECT
    assert namen.TERMEN_16.has_part == namen.HAS_PART
    assert namen.TERMEN_16.is_aspect_of == namen.IS_ASPECT_OF
    assert namen.TERMEN_16.is_part_of == namen.IS_PART_OF
    assert namen.TERMEN_16.has_connection == namen.HAS_CONNECTION
    assert namen.TERMEN_16.has_value == namen.HAS_VALUE
    assert namen.TERMEN_16.has_reference == namen.HAS_REFERENCE


def test_termen_voor_17_spelt_de_17_basis() -> None:
    termen = namen.termen_voor(BASIS_17)
    assert termen.has_aspect == f"{BASIS_17}hasAspect"
    assert termen.has_value == f"{BASIS_17}hasValue"
    assert termen.has_reference == f"{BASIS_17}hasReference"


def test_basis_voor_versie_en_terug() -> None:
    assert namen.basis_voor_versie("1.7") == BASIS_17
    assert namen.versie_van_basis(BASIS_17) == "1.7"
    assert namen.versie_van_basis(BASIS_16) == "1.6"
    assert namen.versie_van_basis("http://example.org/") is None


def test_uri_volgt_de_basis() -> None:
    assert namen._uri("Knooppunt") == f"{BASIS_16}Knooppunt"
    assert namen._uri("Knooppunt", BASIS_17) == f"{BASIS_17}Knooppunt"
    # Een IRI die al volledig is, blijft ongemoeid, ongeacht de basis.
    assert namen._uri("http://x/Y", BASIS_17) == "http://x/Y"


def test_basis_uit_prefixen_leest_de_gwsw_prefix() -> None:
    assert namen.basis_uit_prefixen({"gwsw": BASIS_17, "rdf": "x"}) == BASIS_17
    assert namen.basis_uit_prefixen({"gwsw": BASIS_16}) == BASIS_16


def test_basis_uit_prefixen_zonder_gwsw_of_buiten_patroon_is_none() -> None:
    assert namen.basis_uit_prefixen({"rdf": "x"}) is None
    assert namen.basis_uit_prefixen({"gwsw": "http://data.gwsw.nl/1.7/bas/"}) is None
    assert namen.basis_uit_prefixen({}) is None


def test_basis_uit_iri_herkent_predicaat_en_klasse() -> None:
    assert namen.basis_uit_iri(f"{BASIS_17}hasAspect") == BASIS_17
    assert namen.basis_uit_iri(f"{BASIS_16}Knooppunt") == BASIS_16
    assert namen.basis_uit_iri("http://www.w3.org/2000/01/rdf-schema#label") is None


def test_parse_leest_de_basis_uit_de_gwsw_prefix() -> None:
    """Een gebundelde fixture draagt zijn versie in de `gwsw:`-prefix; `_parse` leest die."""
    index16, _ = _parse(TTL16, None)
    index17, _ = _parse(TTL17, None)
    assert index16.gwsw_basis == BASIS_16
    assert index17.gwsw_basis == BASIS_17


def test_parse_valt_terug_op_de_iri_scan_zonder_gwsw_prefix(tmp_path: Path) -> None:
    """Een export zonder `gwsw:`-prefixdeclaratie is geldig Turtle; de IRI's dragen de versie."""
    bron = tmp_path / "zonder_prefix.ttl"
    bron.write_text(
        f"<http://x/S> <{BASIS_17}hasAspect> <http://x/O> .\n",
        encoding="utf-8",
    )
    index, _ = _parse(bron, None)
    assert index.gwsw_basis == BASIS_17


def test_parse_zonder_herkenbare_versie_valt_terug_op_16_met_waarschuwing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Geen `gwsw:`-prefix en geen GWSW-IRI: terugval op 1.6, maar nooit stil."""
    bron = tmp_path / "geen_gwsw.ttl"
    bron.write_text("<http://x/S> <http://x/p> <http://x/O> .\n", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="gwsw_orox_helpers.bestand"):
        index, _ = _parse(bron, None)
    assert index.gwsw_basis == BASIS_16
    assert "geen herkenbare GWSW-versie" in caplog.text


# --------------------------------------------------------------------------------------
# De doortrekking in de leeslaag (`load_dataset` op de 1.7-fixture uit deel b)
# --------------------------------------------------------------------------------------


def _types_modulo_basis(dataset, basis):  # type: ignore[no-untyped-def]
    return {
        uri: (
            frozenset(t.removeprefix(basis) for t in node.types),
            frozenset(t.removeprefix(basis) for t in node.orientation_types),
        )
        for uri, node in dataset.nodes.items()
    }


def test_17_dataset_leest_dezelfde_knopen_en_strengen_modulo_basis() -> None:
    """De 1.7-voorbeeldfixture levert dezelfde domeinobjecten als de 1.6-tegenhanger."""
    from gwsw_orox_helpers.dataset import load_dataset

    d16 = load_dataset(TTL16)
    d17 = load_dataset(TTL17)

    assert d16._basis == BASIS_16
    assert d17._basis == BASIS_17
    assert set(d16.nodes) == set(d17.nodes)
    assert set(d16.conduits) == set(d17.conduits)
    # De typen zijn gelijk op de basis-IRI na.
    assert _types_modulo_basis(d16, BASIS_16) == _types_modulo_basis(d17, BASIS_17)
    # De ontologische herkenning werkt op 1.7 net zo goed.
    assert d17.klassenhierarchie_bekend
    assert d17.of_class("Leiding") == d16.of_class("Leiding")
    assert any(d17.is_a(uri, "Put") for uri in d17.nodes)


def test_17_dataset_zonder_opgave_kiest_de_17_bundel() -> None:
    """Zonder opgegeven ontologie kiest de lader de gebundelde 1.7-ontologie."""
    from gwsw_orox_helpers.dataset import load_dataset

    d17 = load_dataset(TTL17)
    assert [pad.name for pad in d17.ontologies] == ["gwsw_ontologie_totaal_17.ttl"]


def test_17_dataset_met_expliciete_16_ontologie_meldt_geen_valse_hierarchie(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Een versiemismatch mag `klassenhierarchie_bekend` niet stil op True houden.

    De impact-analyse van issue #32 waarschuwt hiervoor: de 1.6-ontologie levert een
    niet-triviale afsluiting, maar op een 1.7-dataset matcht die geen enkele orientatie.
    De vlag hoort dan eerlijk `False` te zijn (terugval op geometrie), niet True.
    """
    from gwsw_orox_helpers.bronnen import gebundelde_ontologie_voor
    from gwsw_orox_helpers.dataset import load_dataset

    dataset = load_dataset(TTL17, ontology_paths=[gebundelde_ontologie_voor("1.6")])
    assert dataset._basis == BASIS_17
    assert dataset.klassenhierarchie_bekend is False
    # Het gezondheidssignaal laat zien dat de herkenning op geometrie leunt.
    assert dataset.structural_diff.get("knooppunten_wel_geometrie_geen_rol")


def test_kenmerk_property_17_is_een_superset_van_16() -> None:
    """De ontologische kenmerkkennis groeit met 1.7 en verliest geen 1.6-kenmerk."""
    from gwsw_orox_helpers.dataset import load_dataset

    k16 = load_dataset(TTL16).kenmerk_property
    k17 = load_dataset(TTL17).kenmerk_property
    assert k16.items() <= k17.items()


def test_onbekende_versie_valt_terug_op_de_16_bundel_met_waarschuwing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Een gedetecteerde basis zonder gebundelde ontologie (bv. 1.8) valt terug op 1.6."""
    from gwsw_orox_helpers.bronnen import gebundelde_ontologie
    from gwsw_orox_helpers.dataset import _gebundelde_paden_voor_basis

    with caplog.at_level(logging.WARNING, logger="gwsw_orox_helpers.dataset"):
        paden = _gebundelde_paden_voor_basis("http://data.gwsw.nl/1.8/totaal/")
    assert paden == [gebundelde_ontologie()]
    assert "geen ontologie voor gebundeld" in caplog.text
    # De gebundelde versies zelf leveren hun eigen bundel, zonder waarschuwing.
    assert _gebundelde_paden_voor_basis(BASIS_17)[0].name == "gwsw_ontologie_totaal_17.ttl"
