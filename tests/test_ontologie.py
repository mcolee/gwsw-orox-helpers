"""De facetlezer haalt de gedeclareerde waardebereiken uit de GWSW-ontologie.

Elk GWSW-kenmerk verwijst via een `owl:hasValue`-restrictie naar een datatype `Dt_X`,
en dat datatype draagt via `owl:equivalentClass` een `owl:withRestrictions`-lijst met
`xsd:minInclusive`/`maxInclusive`. Zonder deze schakel blijft elke drempel handwerk
(issue #35). De logica draait op een handgeschreven fixture; de echte ijkwaarden lezen
de 2,6 MB grote ontologie die met de package meereist.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from rdflib import Graph, URIRef

from gwsw_orox_helpers.bronnen import gebundelde_ontologie
from gwsw_orox_helpers.dataset import GWSW
from gwsw_orox_helpers.ontologie import (
    datatype_van_kenmerk,
    facetbereik,
    kenmerkbereik,
    verwachte_property,
)

FIXTURE = """
@prefix gwsw: <http://data.gwsw.nl/1.6/totaal/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

gwsw:LengteLeiding a owl:Class ;
    rdfs:subClassOf gwsw:Lengte ,
        [ a owl:Restriction ;
          owl:onProperty gwsw:hasValue ;
          owl:allValuesFrom gwsw:Dt_LengteLeiding ] .

gwsw:Dt_LengteLeiding a rdfs:Datatype ;
    owl:equivalentClass [
        a rdfs:Datatype ;
        owl:onDatatype xsd:decimal ;
        owl:withRestrictions (
            [ xsd:minInclusive "1"^^xsd:decimal ]
            [ xsd:maxInclusive "75"^^xsd:decimal ]
        )
    ] .

gwsw:Dt_HoogtePut a rdfs:Datatype ;
    owl:equivalentClass [
        a rdfs:Datatype ;
        owl:onDatatype xsd:integer ;
        owl:withRestrictions (
            [ xsd:minInclusive 500 ]
            [ xsd:maxInclusive 4000 ]
        )
    ] .

gwsw:Dt_AlleenOndergrens a rdfs:Datatype ;
    owl:equivalentClass [
        a rdfs:Datatype ;
        owl:onDatatype xsd:decimal ;
        owl:withRestrictions ( [ xsd:minInclusive "-20"^^xsd:decimal ] )
    ] .

gwsw:Dt_ZonderFacet a rdfs:Datatype .

gwsw:WIBONThema a owl:Class ;
    rdfs:subClassOf gwsw:Kenmerk ,
        [ a owl:Restriction ;
          owl:onProperty gwsw:hasReference ;
          owl:allValuesFrom gwsw:WIONThemaColl ] .

gwsw:Straatnaam a owl:Class ;
    rdfs:subClassOf gwsw:Kenmerk .
"""


@pytest.fixture
def graaf() -> Graph:
    """De handgeschreven fixture met precies de facetstructuur die de lezer volgt."""
    graph = Graph()
    graph.parse(data=FIXTURE, format="turtle")
    return graph


@pytest.fixture(scope="module")
def echte_graaf() -> Graph:
    """De totaal-ontologie, een keer geparst; los parsen kost per test drie seconden."""
    graph = Graph()
    graph.parse(gebundelde_ontologie(), format="turtle")
    return graph


def _dt(naam: str) -> URIRef:
    return URIRef(GWSW + naam)


def test_facetbereik_leest_een_decimaal_bereik(graaf: Graph) -> None:
    bereik = facetbereik(graaf, _dt("Dt_LengteLeiding"))
    assert bereik is not None
    assert bereik.datatype == "decimal"
    assert bereik.minimum == Decimal("1")
    assert bereik.maximum == Decimal("75")


def test_facetbereik_leest_een_geheeltallig_bereik(graaf: Graph) -> None:
    bereik = facetbereik(graaf, _dt("Dt_HoogtePut"))
    assert bereik is not None
    assert bereik.datatype == "integer"
    assert bereik.minimum == Decimal("500")
    assert bereik.maximum == Decimal("4000")


def test_facetbereik_met_alleen_ondergrens(graaf: Graph) -> None:
    """Een eenzijdig facet levert een bereik met de andere kant op `None`."""
    bereik = facetbereik(graaf, _dt("Dt_AlleenOndergrens"))
    assert bereik is not None
    assert bereik.minimum == Decimal("-20")
    assert bereik.maximum is None


def test_facetbereik_zonder_facetten_is_none(graaf: Graph) -> None:
    assert facetbereik(graaf, _dt("Dt_ZonderFacet")) is None


def test_facetbereik_onbekend_datatype_is_none(graaf: Graph) -> None:
    assert facetbereik(graaf, _dt("Dt_BestaatNiet")) is None


def test_datatype_van_kenmerk_volgt_hasvalue(graaf: Graph) -> None:
    assert datatype_van_kenmerk(graaf, _dt("LengteLeiding")) == _dt("Dt_LengteLeiding")


def test_datatype_van_kenmerk_zonder_restrictie_is_none(graaf: Graph) -> None:
    assert datatype_van_kenmerk(graaf, _dt("Dt_ZonderFacet")) is None


def test_kenmerkbereik_loopt_de_hele_keten(graaf: Graph) -> None:
    bereik = kenmerkbereik(graaf, _dt("LengteLeiding"))
    assert bereik is not None
    assert (bereik.minimum, bereik.maximum) == (Decimal("1"), Decimal("75"))


def test_verwachte_property_leest_hasreference(graaf: Graph) -> None:
    """Een kenmerk dat via een restrictie aan hasReference bindt, eist hasReference."""
    assert verwachte_property(graaf, _dt("WIBONThema")) == "hasReference"


def test_verwachte_property_leest_hasvalue(graaf: Graph) -> None:
    assert verwachte_property(graaf, _dt("LengteLeiding")) == "hasValue"


def test_verwachte_property_zonder_restrictie_is_none(graaf: Graph) -> None:
    """Straatnaam draagt geen property-restrictie; de check heeft er geen mening over."""
    assert verwachte_property(graaf, _dt("Straatnaam")) is None


def test_verwachte_property_uit_de_echte_ontologie(echte_graaf: Graph) -> None:
    """De drie herkenbare gevallen uit issue #37, rechtstreeks uit de totaal-ontologie."""
    assert verwachte_property(echte_graaf, _dt("WIBONThema")) == "hasReference"
    assert verwachte_property(echte_graaf, _dt("HoogtePut")) == "hasValue"
    assert verwachte_property(echte_graaf, _dt("Straatnaam")) is None


@pytest.mark.parametrize(
    ("datatype", "minimum", "maximum"),
    [
        ("Dt_LengteLeiding", Decimal("1"), Decimal("75")),
        ("Dt_BreedteLeiding", Decimal("63"), Decimal("4000")),
        ("Dt_HoogtePut", Decimal("500"), Decimal("4000")),
    ],
)
def test_bekende_bereiken_uit_de_echte_ontologie(
    echte_graaf: Graph, datatype: str, minimum: Decimal, maximum: Decimal
) -> None:
    """De drie ijkwaarden uit issue #35, rechtstreeks uit de totaal-ontologie."""
    bereik = facetbereik(echte_graaf, _dt(datatype))
    assert bereik is not None
    assert (bereik.minimum, bereik.maximum) == (minimum, maximum)


@pytest.mark.parametrize(
    ("klasse", "verwacht"),
    [
        ("Mof", "VerbindenVanTweeLeidingen"),
        ("T_stuk", "VerbindenVanDrieLeidingen"),
        ("Y_stuk", "VerbindenVanDrieLeidingen"),
        ("Kruisstuk", "VerbindenVanVierLeidingen"),
        ("Afsluitstuk", "AfsluitenVanLeidingen"),
        # Zijn definitie noemt drie leidingen, het model niet.
        ("Tubelure", None),
        # Draagt er twee -- LeidingaansluitingVerstevigen en VerstevigenAansluiting --
        # en levert dus de alfabetisch eerste.
        ("Zadel", "LeidingaansluitingVerstevigen"),
    ],
)
def test_functie_van_klasse_uit_de_echte_ontologie(
    echte_graaf: Graph, klasse: str, verwacht: str | None
) -> None:
    from gwsw_orox_helpers.ontologie import functie_van_klasse

    assert functie_van_klasse(echte_graaf, URIRef(GWSW + klasse)) == verwacht
