"""Versiedetectie en de versie-afgeleide termenset (issue #32, deel c).

De leeslaag en de cliplaag leiden hun predicaten sinds issue #32 af uit de gedetecteerde
GWSW-basis van de bron. Hier staan de bouwstenen daarvan: het uit elkaar halen van een
basis-IRI, de termenset per basis en de twee detectiewegen (de `gwsw:`-prefix en de scan
over de IRI's). De doortrekking in de lees- en cliplaag zelf staat in `test_dataset.py`,
`test_ontologie.py` en `test_clip.py`.
"""

from __future__ import annotations

from gwsw_orox_helpers import namen

BASIS_16 = "http://data.gwsw.nl/1.6/totaal/"
BASIS_17 = "http://data.gwsw.nl/1.7/totaal/"


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
