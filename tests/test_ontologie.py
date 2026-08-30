"""De facetlezer haalt de gedeclareerde waardebereiken uit de GWSW-ontologie.

Elk GWSW-kenmerk verwijst via een `owl:hasValue`-restrictie naar een datatype `Dt_X`,
en dat datatype draagt via `owl:equivalentClass` een `owl:withRestrictions`-lijst met
`xsd:minInclusive`/`maxInclusive`. Zonder deze schakel blijft elke drempel handwerk
(issue #35). De logica draait op een handgeschreven fixture; de echte ijkwaarden lezen
de 2,6 MB grote ontologie die met de package meereist.
"""

from __future__ import annotations

import ast
import inspect
from decimal import Decimal

import pytest
from rdflib import OWL, RDF, RDFS, Graph, URIRef
from rdflib.collection import Collection

from gwsw_orox_helpers import ontologie
from gwsw_orox_helpers.bronnen import gebundelde_ontologie
from gwsw_orox_helpers.dataset import GWSW
from gwsw_orox_helpers.graaf import GraafIndex, GraafLezer
from gwsw_orox_helpers.inlezen import _parse
from gwsw_orox_helpers.klassen import _afsluiting, _subclass_closure
from gwsw_orox_helpers.ontologie import (
    Facetbereik,
    _lijstleden,
    datatype_van_kenmerk,
    facetbereik,
    functie_van_klasse,
    kenmerkbereik,
    verwachte_property,
)
from gwsw_orox_helpers.rdfmotor import ontleed_turtle

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

gwsw:Dt_ZonderRestricties a rdfs:Datatype ;
    owl:equivalentClass [
        a rdfs:Datatype ;
        owl:onDatatype xsd:decimal
    ] .

gwsw:WIBONThema a owl:Class ;
    rdfs:subClassOf gwsw:Kenmerk ,
        [ a owl:Restriction ;
          owl:onProperty gwsw:hasReference ;
          owl:allValuesFrom gwsw:WIONThemaColl ] .

gwsw:Straatnaam a owl:Class ;
    rdfs:subClassOf gwsw:Kenmerk .
"""


def _in_vorm(ttl: str, vorm: str) -> Graph | GraafIndex:
    """Dezelfde Turtle als rdflib-`Graph` of als `GraafIndex`.

    De twee graafvormen die de lezers van `ontologie` kennen: de `Graph` waarop de
    facetlezing tot issue #19 alleen liep, en de `GraafIndex` die `load_dataset` als
    restrictiebron levert. Elke fixture hieronder draait beide, zodat een verschil
    tussen de twee wegen meteen opvalt.
    """
    if vorm == "graph":
        graph = Graph()
        graph.parse(data=ttl, format="turtle")
        return graph
    index = GraafIndex()
    index.vul_uit(ontleed_turtle(ttl.encode("utf-8")))
    return index


@pytest.fixture(params=["graph", "index"])
def graaf(request: pytest.FixtureRequest) -> Graph | GraafIndex:
    """De handgeschreven fixture met precies de facetstructuur die de lezer volgt."""
    return _in_vorm(FIXTURE, request.param)


@pytest.fixture(scope="module")
def echte_graaf() -> Graph:
    """De totaal-ontologie, een keer geparst; los parsen kost per test drie seconden."""
    graph = Graph()
    graph.parse(gebundelde_ontologie(), format="turtle")
    return graph


def _dt(naam: str) -> URIRef:
    return URIRef(GWSW + naam)


def test_facetbereik_leest_een_decimaal_bereik(graaf: Graph | GraafIndex) -> None:
    bereik = facetbereik(graaf, _dt("Dt_LengteLeiding"))
    assert bereik is not None
    assert bereik.datatype == "decimal"
    assert bereik.minimum == Decimal("1")
    assert bereik.maximum == Decimal("75")


def test_facetbereik_leest_een_geheeltallig_bereik(graaf: Graph | GraafIndex) -> None:
    bereik = facetbereik(graaf, _dt("Dt_HoogtePut"))
    assert bereik is not None
    assert bereik.datatype == "integer"
    assert bereik.minimum == Decimal("500")
    assert bereik.maximum == Decimal("4000")


def test_facetbereik_met_alleen_ondergrens(graaf: Graph | GraafIndex) -> None:
    """Een eenzijdig facet levert een bereik met de andere kant op `None`."""
    bereik = facetbereik(graaf, _dt("Dt_AlleenOndergrens"))
    assert bereik is not None
    assert bereik.minimum == Decimal("-20")
    assert bereik.maximum is None


def test_facetbereik_zonder_facetten_is_none(graaf: Graph | GraafIndex) -> None:
    assert facetbereik(graaf, _dt("Dt_ZonderFacet")) is None


def test_facetbereik_met_equivalent_zonder_restricties_is_none(graaf: Graph | GraafIndex) -> None:
    """Een `owl:equivalentClass` zonder `owl:withRestrictions` legt geen bereik vast."""
    assert facetbereik(graaf, _dt("Dt_ZonderRestricties")) is None


def test_facetbereik_onbekend_datatype_is_none(graaf: Graph | GraafIndex) -> None:
    assert facetbereik(graaf, _dt("Dt_BestaatNiet")) is None


def test_datatype_van_kenmerk_volgt_hasvalue(graaf: Graph | GraafIndex) -> None:
    assert datatype_van_kenmerk(graaf, _dt("LengteLeiding")) == _dt("Dt_LengteLeiding")


def test_datatype_van_kenmerk_zonder_restrictie_is_none(graaf: Graph | GraafIndex) -> None:
    assert datatype_van_kenmerk(graaf, _dt("Dt_ZonderFacet")) is None


def test_kenmerkbereik_loopt_de_hele_keten(graaf: Graph | GraafIndex) -> None:
    bereik = kenmerkbereik(graaf, _dt("LengteLeiding"))
    assert bereik is not None
    assert (bereik.minimum, bereik.maximum) == (Decimal("1"), Decimal("75"))


def test_verwachte_property_leest_hasreference(graaf: Graph | GraafIndex) -> None:
    """Een kenmerk dat via een restrictie aan hasReference bindt, eist hasReference."""
    assert verwachte_property(graaf, _dt("WIBONThema")) == "hasReference"


def test_verwachte_property_leest_hasvalue(graaf: Graph | GraafIndex) -> None:
    assert verwachte_property(graaf, _dt("LengteLeiding")) == "hasValue"


def test_verwachte_property_zonder_restrictie_is_none(graaf: Graph | GraafIndex) -> None:
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
    assert functie_van_klasse(echte_graaf, URIRef(GWSW + klasse)) == verwacht


# --- Dezelfde lezing op de GraafIndex van de echte leesweg (issue #19) -----------------


@pytest.fixture(scope="module")
def echte_index() -> GraafIndex:
    """De totaal-ontologie als `GraafIndex`, langs precies de weg van `load_dataset`.

    `inlezen._parse` is de functie die de lader zelf voor elk ontologiebestand aanroept;
    wat hij oplevert is de `restrictiebron` waarop `load_dataset` de klassenafleiding
    doet. Deze fixture is dus geen nabootsing van de leesweg maar die weg zelf -- en
    daarmee het bewijs dat issue #19 vraagt.
    """
    graaf, _ = _parse(gebundelde_ontologie(), None)
    return graaf


# De aantallen van GWSW 1.6 (zie de Harde regels in `CLAUDE.md`). Ze zijn hier geen
# doel op zich maar de dekkingsmaat van issue #19: vóór de eigen collectiewandeling
# liep de facetlezing op een `GraafIndex` op een `AttributeError` stuk en was de
# dekking van de leesweg dus nul.
AANTAL_DATATYPES = 39
AANTAL_FACETBEREIKEN = 38
AANTAL_KENMERKKLASSEN = 709
AANTAL_KENMERKBEREIKEN = 40
AANTAL_KLASSEN = 2087


def test_de_facetlezing_van_de_hele_ontologie_is_op_beide_graafvormen_gelijk(
    echte_graaf: Graph, echte_index: GraafIndex
) -> None:
    """Elk datatype dat de ontologie kent, gelezen langs allebei de wegen."""
    datatypes = sorted(
        term for term in echte_graaf.subjects(RDF.type, RDFS.Datatype) if isinstance(term, URIRef)
    )
    assert len(datatypes) == AANTAL_DATATYPES
    via_graph = {datatype: facetbereik(echte_graaf, datatype) for datatype in datatypes}
    via_index = {datatype: facetbereik(echte_index, datatype) for datatype in datatypes}
    assert via_graph == via_index
    gevonden = [bereik for bereik in via_index.values() if bereik is not None]
    assert len(gevonden) == AANTAL_FACETBEREIKEN


def test_de_kenmerklezing_van_de_hele_ontologie_is_op_beide_graafvormen_gelijk(
    echte_graaf: Graph, echte_index: GraafIndex
) -> None:
    """Elk kenmerk uit de `Kenmerk`-afsluiting, met datatype en bereik, langs beide wegen."""
    kenmerken = sorted(
        URIRef(uri) for uri in _afsluiting(_subclass_closure(echte_index), "Kenmerk")
    )
    assert len(kenmerken) == AANTAL_KENMERKKLASSEN
    assert {kenmerk: datatype_van_kenmerk(echte_graaf, kenmerk) for kenmerk in kenmerken} == {
        kenmerk: datatype_van_kenmerk(echte_index, kenmerk) for kenmerk in kenmerken
    }
    via_graph = {kenmerk: kenmerkbereik(echte_graaf, kenmerk) for kenmerk in kenmerken}
    via_index = {kenmerk: kenmerkbereik(echte_index, kenmerk) for kenmerk in kenmerken}
    assert via_graph == via_index
    gevonden = [bereik for bereik in via_index.values() if bereik is not None]
    assert len(gevonden) == AANTAL_KENMERKBEREIKEN


def test_de_restrictielezers_zijn_op_beide_graafvormen_gelijk_over_alle_klassen(
    echte_graaf: Graph, echte_index: GraafIndex
) -> None:
    """De twee lezers die al `Graph | GraafIndex` namen, over de hele ontologie.

    `verwachte_property` en `functie_van_klasse` liepen ook vóór issue #19 al op allebei
    de vormen, maar dat stond alleen op de vijf klassen van de handgeschreven fixture
    vast. Hier gaan ze over elke `owl:Class` die de ontologie kent -- de klassen waar
    `klassen._kenmerk_properties` en `_klassefuncties` hun woordenboeken uit vullen -- en
    is de gelijkwaardigheid van de twee wegen dus niet meer een steekproef. `value()` geeft
    "het eerste object", en de volgorde van rdflib's store is een andere dan de
    insertievolgorde van `GraafIndex`; deze test is de bewaker die het zou merken als
    de ontologie ooit een klasse met twee concurrerende restricties krijgt.
    """
    klassen = sorted(
        term for term in echte_graaf.subjects(RDF.type, OWL.Class) if isinstance(term, URIRef)
    )
    assert len(klassen) == AANTAL_KLASSEN
    assert {klasse: verwachte_property(echte_graaf, klasse) for klasse in klassen} == {
        klasse: verwachte_property(echte_index, klasse) for klasse in klassen
    }
    assert {klasse: functie_van_klasse(echte_graaf, klasse) for klasse in klassen} == {
        klasse: functie_van_klasse(echte_index, klasse) for klasse in klassen
    }


# --- De collectiewandeling zelf, tegen `rdflib.collection.Collection` gehouden --------

LIJSTEN = """
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix ex: <http://example.org/> .

# Een nette lijst van twee leden.
ex:goed rdf:first ex:a ; rdf:rest ex:goed_staart .
ex:goed_staart rdf:first ex:b ; rdf:rest rdf:nil .

# Een lijst waarvan de staart geen rdf:rest draagt.
ex:afgebroken rdf:first ex:a ; rdf:rest ex:losse_staart .
ex:losse_staart rdf:first ex:b .

# Een schakel zonder rdf:first: een gat in de lijst, geen einde.
ex:met_gat rdf:rest ex:na_het_gat .
ex:na_het_gat rdf:first ex:c ; rdf:rest rdf:nil .

# Een lijst met een lijst als lid; die wordt niet afgevlakt.
ex:genest rdf:first ex:binnenste ; rdf:rest rdf:nil .
ex:binnenste rdf:first ex:x ; rdf:rest rdf:nil .

# Twee cyclussen: een van twee schakels en een die naar zichzelf wijst.
ex:cyclus rdf:first ex:a ; rdf:rest ex:cyclus_terug .
ex:cyclus_terug rdf:first ex:b ; rdf:rest ex:cyclus .
ex:zelflus rdf:first ex:a ; rdf:rest ex:zelflus .
"""

EX = "http://example.org/"


@pytest.fixture(params=["graph", "index"])
def lijsten(request: pytest.FixtureRequest) -> Graph | GraafIndex:
    """`LIJSTEN` als rdflib-`Graph` en als `GraafIndex`; elke test draait op allebei."""
    return _in_vorm(LIJSTEN, request.param)


@pytest.mark.parametrize(
    ("kop", "verwacht"),
    [
        (URIRef(EX + "goed"), [EX + "a", EX + "b"]),
        # Een schakel zonder rdf:rest sluit de lijst af met wat er wél stond.
        (URIRef(EX + "afgebroken"), [EX + "a", EX + "b"]),
        # Een schakel zonder rdf:first slaat een lid over en loopt door.
        (URIRef(EX + "met_gat"), [EX + "c"]),
        # Een geneste lijst levert de kop van de binnenlijst op, niet haar leden.
        (URIRef(EX + "genest"), [EX + "binnenste"]),
        # rdf:nil is de lege lijst.
        (RDF.nil, []),
        # Een kop die nergens in de graaf staat, levert niets op.
        (URIRef(EX + "bestaat_niet"), []),
    ],
)
def test_lijstleden_wandelt_de_rdf_lijst(
    lijsten: Graph | GraafIndex, kop: URIRef, verwacht: list[str]
) -> None:
    """De randgevallen van een RDF-lijst, gelijk op allebei de graafvormen."""
    assert [str(lid) for lid in _lijstleden(lijsten, kop)] == verwacht


@pytest.mark.parametrize("kop", ["goed", "afgebroken", "met_gat", "genest"])
def test_lijstleden_geeft_hetzelfde_als_rdflibs_collection(kop: str) -> None:
    """De ijking: dezelfde leden als `rdflib.collection.Collection`, die dit eerst deed."""
    graph = Graph()
    graph.parse(data=LIJSTEN, format="turtle")
    uri = URIRef(EX + kop)
    assert list(_lijstleden(graph, uri)) == list(Collection(graph, uri))


@pytest.mark.parametrize("kop", ["cyclus", "zelflus"])
def test_lijstleden_weigert_een_cyclische_lijst(lijsten: Graph | GraafIndex, kop: str) -> None:
    """Geen oneindige lus maar dezelfde `ValueError` die `Collection` gaf."""
    with pytest.raises(ValueError, match="recursive rdf:rest reference"):
        list(_lijstleden(lijsten, URIRef(EX + kop)))


@pytest.mark.parametrize("kop", ["cyclus", "zelflus"])
def test_de_cyclusfout_is_dezelfde_als_die_van_rdflibs_collection(kop: str) -> None:
    """Woordelijk dezelfde melding, zodat wie haar ving haar blijft vangen."""
    graph = Graph()
    graph.parse(data=LIJSTEN, format="turtle")
    uri = URIRef(EX + kop)
    with pytest.raises(ValueError) as eigen:
        list(_lijstleden(graph, uri))
    with pytest.raises(ValueError) as rdflib_fout:
        list(Collection(graph, uri))
    assert str(eigen.value) == str(rdflib_fout.value)


def test_lijstleden_laat_de_graaf_ongemoeid(lijsten: Graph | GraafIndex) -> None:
    """De wandeling leest en schrijft niet; een lezing mag de ontologie niet verbouwen."""
    voor = len(lijsten)
    for kop in ("goed", "afgebroken", "met_gat", "genest"):
        list(_lijstleden(lijsten, URIRef(EX + kop)))
    assert len(lijsten) == voor


# --- Het protocol is precies zo breed als de lezers hem gebruiken (issue #21) ---------

# De leden die `GraafLezer` belooft. Met de hand uit `vars()` en niet uit
# `__protocol_attrs__`: dat attribuut is een implementatiedetail van `typing` (het
# officiele `typing.get_protocol_members` bestaat pas vanaf 3.13, en deze package draait
# vanaf 3.12). De twee tests hieronder lezen allebei deze verzameling, zodat er maar een
# plek is die weet hoe je de leden van het protocol opvraagt.
PROTOCOLLEDEN = frozenset(naam for naam in vars(GraafLezer) if not naam.startswith("_"))


def test_het_protocol_is_precies_zo_breed_als_ontologie_het_gebruikt() -> None:
    """`GraafLezer` noemt exact de bewerkingen die `ontologie` op zijn graaf aanroept.

    De ene kant bewaakt mypy al: een lezer die een derde bewerking gaat gebruiken, krijgt
    een `attr-defined` op het protocol. De andere kant ziet mypy niet -- een protocol mag
    breder zijn dan zijn aanroepers zonder dat er iets rood wordt -- en juist die kant is
    hier het punt. Elk lid erbij is een eis aan wie het protocol wil vervullen: `Graph`
    haakt af op het eerste lid dat rdflib niet kent (`heeft_subject`), en dat is precies
    de scheur die issue #19 repareerde. Deze test leest daarom de boom van `ontologie.py`
    af: elke naam die daar van een `GraafLezer`-parameter wordt opgevraagd, en niets
    anders, staat in het protocol. Opgevraagd en niet aangeroepen -- de sweep filtert
    bewust niet op `ast.Call`: ook een `graph.items` die alleen doorgegeven wordt, is een
    lid dat de vervuller moet dragen, en juist zo'n gebruik brak issue #19.

    De sweep zoekt die parameters op hun **annotatie** en niet op de naam `graph`: een
    lezer die er straks `bron` van maakt, of een zesde lezer die een eigen naam kiest,
    zou anders ongemerkt langs deze bewaker glippen en het protocol stil te smal of te
    breed laten worden. `from __future__ import annotations` maakt de annotatie een
    string bij het draaien, maar de boom draagt haar nog als `ast.Name`.
    """
    boom = ast.parse(inspect.getsource(ontologie))
    parameters = {
        arg.arg
        for knoop in ast.walk(boom)
        if isinstance(knoop, ast.FunctionDef)
        for arg in knoop.args.args
        if isinstance(arg.annotation, ast.Name) and arg.annotation.id == GraafLezer.__name__
    }
    gebruikt = {
        knoop.attr
        for knoop in ast.walk(boom)
        if isinstance(knoop, ast.Attribute)
        and isinstance(knoop.value, ast.Name)
        and knoop.value.id in parameters
    }
    assert parameters, "geen enkele parameter in `ontologie` is op `GraafLezer` geannoteerd"
    assert gebruikt == PROTOCOLLEDEN


@pytest.mark.parametrize("vorm", ["graph", "index"])
def test_allebei_de_graafvormen_dragen_de_leden_van_het_protocol(vorm: str) -> None:
    """De runtimekant van hetzelfde: `Graph` en `GraafIndex` hebben die leden echt.

    Structurele vervulling is een typebegrip en het bewijs ervan staat in
    `tests/typecheck/graaflezer.py`, dat de poort meeneemt. Dit is de goedkope
    tegenhanger: de namen bestaan en zijn aanroepbaar op allebei de vormen, ook als
    iemand ooit met een `if TYPE_CHECKING` de mypy-kant zou omzeilen.
    """
    bron = _in_vorm(FIXTURE, vorm)
    for naam in PROTOCOLLEDEN:
        assert callable(getattr(bron, naam)), naam


def test_de_ijkwaarden_uit_issue_35_komen_ook_uit_de_graafindex(echte_index: GraafIndex) -> None:
    """De belofte van issue #35, nu op de graafvorm die de lader werkelijk draagt."""
    assert kenmerkbereik(echte_index, _dt("LengteLeiding")) == Facetbereik(
        datatype="decimal", minimum=Decimal("1"), maximum=Decimal("75")
    )
    assert facetbereik(echte_index, _dt("Dt_HoogtePut")) == Facetbereik(
        datatype="integer", minimum=Decimal("500"), maximum=Decimal("4000")
    )
