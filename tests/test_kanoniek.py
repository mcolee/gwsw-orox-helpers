"""Canonieke vraagtermen (issue #81): de index en de lezers delen dezelfde term-objecten.

Een dict-treffer met een gelijk-maar-niet-identiek sleutelobject valt door naar rdflib's
Python-`__eq__`; met dezelfde objecten aan beide kanten is het een identiteitstreffer.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from rdflib import RDF, RDFS, URIRef

from gwsw_orox_helpers import inlezen, namen
from gwsw_orox_helpers.bestand import _parse
from gwsw_orox_helpers.cache import laad_met_cache
from gwsw_orox_helpers.graaf import GraafIndex, _kanoniek

FIXTURES = Path(__file__).parent / "fixtures"
SCHOON = FIXTURES / "ttl" / "schoon.ttl"
MINI17 = FIXTURES / "ttl17" / "mini_orox.ttl"


def _termen(t: inlezen.Leestermen) -> list[URIRef]:
    uit: list[URIRef] = []
    for veld in dataclasses.fields(t):
        waarde = getattr(t, veld.name)
        uit.extend(waarde if isinstance(waarde, tuple) else (waarde,))
    return uit


def test_kanoniek_is_dezelfde_term_als_urirefs_eigen_constructor() -> None:
    for iri in (f"{namen.GWSW}hasAspect", f"{namen.RDF}type", "http://example.org/Put_1"):
        term = _kanoniek(iri)
        assert type(term) is URIRef
        assert term == URIRef(iri)
        assert hash(term) == hash(URIRef(iri))


def test_de_leestermen_en_rdf_type_zijn_kanoniek_voor_elke_basis() -> None:
    for basis in (namen.GWSW, namen.basis_voor_versie("1.7"), namen.basis_voor_versie("1.9")):
        for term in _termen(inlezen._leestermen(basis)):
            assert term is _kanoniek(str(term)), term
    assert inlezen._RDF_TYPE is _kanoniek(str(RDF.type))
    assert inlezen._RDFS_LABEL is _kanoniek(str(RDFS.label))


def test_een_niet_leesterm_wordt_niet_vastgehouden() -> None:
    iri = "http://example.org/Put_niet_kanoniek"
    assert _kanoniek(iri) is not _kanoniek(iri)


def _sleutels(graaf: GraafIndex) -> dict[str, object]:
    sleutels: dict[str, object] = {str(p): p for p in graaf._pos}
    for per_predicaat in graaf._spo.values():
        sleutels.update((str(p), p) for p in per_predicaat)
    for o in graaf._pos.get(inlezen._RDF_TYPE, {}):
        sleutels.setdefault(str(o), o)
    return sleutels


def _toets_identiteit(graaf: GraafIndex) -> None:
    sleutels = _sleutels(graaf)
    t = inlezen._leestermen(graaf.gwsw_basis)
    assert sleutels[str(inlezen._RDF_TYPE)] is inlezen._RDF_TYPE
    gevonden = [term for term in _termen(t) if str(term) in sleutels]
    assert t.has_aspect in gevonden
    for term in gevonden:
        assert sleutels[str(term)] is term, term


def test_de_index_draagt_de_kanonieke_objecten_na_de_parse() -> None:
    for pad in (SCHOON, MINI17):
        graaf, _ = _parse(pad, None)
        _toets_identiteit(graaf)


def test_de_index_draagt_de_kanonieke_objecten_na_een_cacherondgang(tmp_path: Path) -> None:
    laad_met_cache(SCHOON, [], cache_dir=tmp_path)
    warm, uitslag = laad_met_cache(SCHOON, [], cache_dir=tmp_path)
    assert uitslag.bron == "cache"
    len(warm.graph)
    _toets_identiteit(warm.graph._geladen())  # type: ignore[attr-defined]


def test_membership_met_een_verse_gelijke_term_blijft_waar() -> None:
    graaf, _ = _parse(SCHOON, None)
    subject, objecten = next(
        (s, per_p[inlezen._RDF_TYPE])
        for s, per_p in graaf._spo.items()
        if inlezen._RDF_TYPE in per_p and not isinstance(per_p[inlezen._RDF_TYPE], dict)
    )
    vers = URIRef(str(objecten))
    assert vers is not objecten
    assert (subject, URIRef(str(RDF.type)), vers) in graaf
    assert (subject, inlezen._RDF_TYPE, URIRef("http://example.org/Anders")) not in graaf


def test_membership_met_een_niet_term_is_onwaar_zonder_typefout() -> None:
    graaf, _ = _parse(SCHOON, None)
    subject = next(s for s, per_p in graaf._spo.items() if inlezen._RDF_TYPE in per_p)
    for vreemd in (None, 5, object()):
        assert (subject, inlezen._RDF_TYPE, vreemd) not in graaf
