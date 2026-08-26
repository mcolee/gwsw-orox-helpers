"""Tests voor `graaf.GraafIndex`: hetzelfde antwoord als rdflib, inclusief volgorde.

De index vervangt de rdflib-store als drager van `GwswDataset.graph`. De harde eis is
dat elke geinventariseerde leesbewerking (zie de moduledocstring van `graaf.py`) op
dezelfde triples exact het rdflib-antwoord geeft -- ook de iteratievolgorde, want de
uitvoer van de checks hangt eraan. Elke test bouwt daarom een rdflib-`Graph` en een
`GraafIndex` uit dezelfde triple-lijst en vergelijkt de twee letterlijk.
"""

from __future__ import annotations

import pyoxigraph
import pytest
from rdflib import RDF, RDFS, BNode, Graph, Literal, URIRef

from gwsw_orox_helpers.graaf import GraafIndex

NS = "http://data.gwsw.nl/1.6/totaal/"
P_TYPE = RDF.type
P_PART = URIRef(f"{NS}hasPart")
P_LABEL = RDFS.label

S1 = URIRef("http://voorbeeld#s1")
S2 = URIRef("http://voorbeeld#s2")
S3 = BNode("b3")
O1 = URIRef(f"{NS}Put")
O2 = URIRef(f"{NS}Leiding")


def _triples() -> list[tuple]:
    """Een lijst met de gevallen die de volgorde op de proef stellen.

    Bewust met een duplicaat, een BNode-subject, meerdere objecten per (s, p),
    meerdere subjecten per (p, o) en een interleaving die de pos-groepering van
    `subject_objects` zichtbaar maakt (s1-o1, s2-o2, s3-o1: rdflib groepeert per
    object, niet in triple-volgorde).
    """
    return [
        (S1, P_TYPE, O1),
        (S1, P_PART, S2),
        (S2, P_TYPE, O2),
        (S1, P_TYPE, O2),
        (S3, P_TYPE, O1),
        (S1, P_TYPE, O1),  # duplicaat: mag nergens dubbel verschijnen
        (S1, P_PART, S3),
        (S2, P_LABEL, Literal("put twee")),
        (S3, P_LABEL, Literal("två", lang="sv")),
        (S1, P_LABEL, Literal("2.5", datatype=URIRef("http://www.w3.org/2001/XMLSchema#decimal"))),
    ]


def _naar_pyoxigraph(term) -> pyoxigraph.NamedNode | pyoxigraph.BlankNode | pyoxigraph.Literal:
    """De pyoxigraph-tegenhanger van een rdflib-term, voor de vul_uit-route."""
    if isinstance(term, URIRef):
        return pyoxigraph.NamedNode(str(term))
    if isinstance(term, BNode):
        return pyoxigraph.BlankNode(str(term))
    if term.language is not None:
        return pyoxigraph.Literal(str(term), language=term.language)
    if term.datatype is not None:
        return pyoxigraph.Literal(str(term), datatype=pyoxigraph.NamedNode(str(term.datatype)))
    return pyoxigraph.Literal(str(term))


@pytest.fixture(params=["voeg_toe", "vul_uit"])
def paar(request: pytest.FixtureRequest) -> tuple[Graph, GraafIndex]:
    """Dezelfde triples in een rdflib-graaf en in de eigen index.

    Geparametriseerd over beide vulroutes: `voeg_toe` (de leesbare referentie) en
    `vul_uit` (de inline-productieroute uit de pyoxigraph-stream). Zo draait elke
    volgorde-, dedupe- en membershipvergelijking hieronder tweemaal en kunnen de
    twee implementaties niet uit elkaar groeien.
    """
    graf = Graph()
    for s, p, o in _triples():
        graf.add((s, p, o))
    index = GraafIndex()
    if request.param == "voeg_toe":
        for s, p, o in _triples():
            index.voeg_toe(s, p, o)
    else:
        index.vul_uit(
            pyoxigraph.Quad(_naar_pyoxigraph(s), _naar_pyoxigraph(p), _naar_pyoxigraph(o))
            for s, p, o in _triples()
        )
    return graf, index


def _alle_sp(triples) -> list[tuple]:
    return list(dict.fromkeys((s, p) for s, p, _ in triples))


def _alle_po(triples) -> list[tuple]:
    return list(dict.fromkeys((p, o) for _, p, o in triples))


def test_objects_geeft_het_rdflib_antwoord_in_dezelfde_volgorde(paar) -> None:
    graf, index = paar
    for s, p in _alle_sp(_triples()):
        assert list(index.objects(s, p)) == list(graf.objects(s, p)), (s, p)
    assert list(index.objects(URIRef("http://onbekend"), P_TYPE)) == []
    assert list(index.objects(S1, URIRef(f"{NS}nooit"))) == []


def test_subjects_geeft_het_rdflib_antwoord_in_dezelfde_volgorde(paar) -> None:
    graf, index = paar
    for p, o in _alle_po(_triples()):
        assert list(index.subjects(p, o)) == list(graf.subjects(p, o)), (p, o)
    assert list(index.subjects(P_TYPE, URIRef("http://onbekend"))) == []


def test_value_geeft_het_eerste_object_of_none(paar) -> None:
    graf, index = paar
    for s, p in _alle_sp(_triples()):
        assert index.value(s, p) == graf.value(s, p), (s, p)
    assert index.value(URIRef("http://onbekend"), P_TYPE) is None


def test_subject_objects_volgt_de_pos_groepering_van_rdflib(paar) -> None:
    """rdflib loopt bij (None, p, None) de pos-index af: eerst per object, dan per
    subject. Dat is niet de triple-volgorde; de index moet die groepering spiegelen."""
    graf, index = paar
    for p in (P_TYPE, P_PART, P_LABEL, URIRef(f"{NS}nooit")):
        assert list(index.subject_objects(p)) == list(graf.subject_objects(p)), p


def test_membership_op_volledig_gebonden_triples(paar) -> None:
    graf, index = paar
    for triple in _triples():
        assert (triple in index) == (triple in graf)
    afwezig = (S2, P_PART, S1)
    assert (afwezig in index) == (afwezig in graf) is False


def test_len_telt_triples_zonder_duplicaten(paar) -> None:
    graf, index = paar
    assert len(index) == len(graf)


def test_heeft_subject_kent_alleen_subjecten(paar) -> None:
    _, index = paar
    assert index.heeft_subject(S1)
    assert index.heeft_subject(S3)  # ook een BNode
    assert not index.heeft_subject(O1)  # komt alleen als object voor


def test_vul_uit_bouwt_dezelfde_index_als_losse_rdflib_termen() -> None:
    """De pyoxigraph-stream levert dezelfde termen en volgorde als de handmatige route."""
    ttl = f"""
    @prefix gwsw: <{NS}> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    <http://voorbeeld#s1> a gwsw:Put ; gwsw:hasPart <http://voorbeeld#s2> .
    <http://voorbeeld#s2> a gwsw:Leiding ; rdfs:label "put twee" .
    """
    quads = pyoxigraph.parse(ttl.encode("utf-8"), format=pyoxigraph.RdfFormat.TURTLE)
    index = GraafIndex()
    index.vul_uit(quads)

    assert list(index.objects(S1, P_TYPE)) == [O1]
    assert list(index.objects(S1, P_PART)) == [S2]
    assert index.value(S2, P_LABEL) == Literal("put twee")
    assert len(index) == 4


def test_vul_uit_deelt_gelijke_termen_als_een_object() -> None:
    """Interning: dezelfde URI in meerdere triples wordt een keer als term bewaard."""
    ttl = f"""
    <http://voorbeeld#s1> <{P_TYPE}> <{O1}> .
    <http://voorbeeld#s2> <{P_TYPE}> <{O1}> .
    """
    quads = pyoxigraph.parse(ttl.encode("utf-8"), format=pyoxigraph.RdfFormat.TURTLE)
    index = GraafIndex()
    index.vul_uit(quads)

    eerste = next(iter(index.objects(S1, P_TYPE)))
    tweede = next(iter(index.objects(S2, P_TYPE)))
    assert eerste is tweede
