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

from gwsw_orox_helpers.graaf import GraafIndex, _literal_string_snel, _uriref_snel

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


# --------------------------------------------------------------------------------------
# Het snelpad voor de twee dominante termvormen
# --------------------------------------------------------------------------------------

# Wat de snelpaden op de proef stelt: de lege tekst, witruimte (ook een regeleinde, dat
# `Literal.n3()` naar de drievoudig aangehaalde vorm duwt), unicode, cijfertekst, een IRI
# met een fragment, en een IRI met een spatie -- die laatste zou `URIRef.__new__`'s
# `_is_valid_uri` afkeuren en met een `logger.warning` beantwoorden. Juist die moet
# hetzelfde object opleveren als de trage weg, want het snelpad slaat die controle over.
SNELPAD_WAARDEN = [
    "",
    " ",
    "\t\n ",
    "42",
    "0,5",
    "één stráát mét ünïcode ☂",
    "http://example.org/gewoon",
    f"{NS}Put#fragment",
    "http://example.org/met een spatie",
    "urn:x-gwsw:leeg",
]


def _n3(term) -> object:
    """`term.n3()`, of de fout die hij gooit; rdflib weigert een IRI met een spatie.

    Beide wegen horen daar hetzelfde te doen, dus de fout is hier net zo goed een
    uitkomst om te vergelijken als de tekst.
    """
    try:
        return term.n3()
    except Exception as fout:
        # Breed vangen is hier het punt: welke fout rdflib kiest hoort ook gelijk te zijn,
        # dus de soort en de tekst zijn de uitkomst en niet iets om weg te filteren.
        return type(fout), str(fout)


@pytest.mark.parametrize("waarde", SNELPAD_WAARDEN)
def test_uriref_snel_is_niet_te_onderscheiden_van_de_trage_weg(waarde: str) -> None:
    """`_uriref_snel(v)` levert exact wat `URIRef(v)` levert, tot en met het type.

    Dit is de bewaker voor een rdflib-upgrade: het snelpad omzeilt `URIRef.__new__` en
    steunt erop dat die in de zonder-`base`-tak niets anders doet dan valideren en
    `str.__new__` aanroepen. Verandert dat, dan hoort deze test rood te worden.
    """
    snel = _uriref_snel(waarde)
    traag = URIRef(waarde)

    assert type(snel) is type(traag) is URIRef
    assert snel == traag and traag == snel
    assert hash(snel) == hash(traag)
    assert str(snel) == str(traag)
    assert _n3(snel) == _n3(traag)
    assert snel.toPython() == traag.toPython()
    # Een `URIRef` draagt geen `.datatype`, `.language` of `.value`; dat het snelpad daar
    # niet stiekem wel iets neerzet hoort net zo goed vast te liggen.
    for naam in ("datatype", "language", "value"):
        assert hasattr(snel, naam) == hasattr(traag, naam) is False, naam


@pytest.mark.parametrize("waarde", SNELPAD_WAARDEN)
def test_literal_string_snel_is_niet_te_onderscheiden_van_de_trage_weg(waarde: str) -> None:
    """`_literal_string_snel(v)` levert exact wat `Literal(v)` levert.

    Dit is de bewaker voor een rdflib-upgrade die de interne veldnamen (`_language`,
    `_datatype`, `_value`, `_ill_typed`) hernoemt of hun betekenis verandert: het snelpad
    zet die vier rechtstreeks in plaats van de constructor te laten rekenen. Vandaar dat
    hier niet alleen `==` maar ook `hash()`, `.n3()` en alle vier de afgeleide
    eigenschappen vergeleken worden -- `==` alleen zou een verkeerde `_value` niet zien.
    """
    snel = _literal_string_snel(waarde)
    traag = Literal(waarde)

    assert type(snel) is type(traag) is Literal
    assert snel == traag and traag == snel
    assert hash(snel) == hash(traag)
    assert str(snel) == str(traag)
    assert _n3(snel) == _n3(traag)
    assert snel.datatype == traag.datatype and traag.datatype is None
    assert snel.language == traag.language and traag.language is None
    assert snel.value == traag.value
    assert snel.ill_typed == traag.ill_typed
    assert snel.toPython() == traag.toPython()


# Het aantal unieke IRI's in de gebundelde GWSW 1.6-ontologie -- subject, predicaat en
# object samen. Net als `AANTAL_TRIPELS_GWSW16` in `tests/test_dataset.py` is dit een
# getal dat bij een ontologie-upgrade meeschuift; het meldt zich vanzelf, want deze test
# wordt er rood van.
AANTAL_IRIS_GWSW16 = 3_367


def test_uriref_snel_geeft_dezelfde_term_voor_elke_iri_in_de_gebundelde_ontologie() -> None:
    """Het snelpad en `URIRef()` zijn gelijk op de hele voorraad IRI's die we uitleveren.

    De tien waarden hierboven zijn met de hand gekozen randgevallen; dit is de andere
    kant van hetzelfde bewijs -- elke IRI die de gebundelde ontologie werkelijk draagt,
    en dus precies de tekstvorm waar `dataset.graph_types_of` en `inlezen._deksel_kenmerk`
    hun term uit bouwen (issue #23). Dat die twee daarvoor van `URIRef()` naar
    `_uriref_snel` zijn overgestapt, rust op de gelijkheid die hier geteld wordt: gelijk
    type, gelijke `==`, gelijke `hash()` en gelijke tekst, want de index zoekt op hash en
    gelijkheid op.

    Rechtstreeks langs de motor en niet via `GraafIndex`: de index biedt geen bewerking
    aan om al haar termen op te sommen, en dat blijft zo -- het leescontract in de
    moduledocstring van `graaf` is precies de handvol bewerkingen die de checks stellen.
    """
    from gwsw_orox_helpers import rdfmotor
    from gwsw_orox_helpers.bronnen import gebundelde_ontologie

    iris = {
        term.value
        for quad in rdfmotor.ontleed_turtle_bestand(gebundelde_ontologie())
        for term in (quad.subject, quad.predicate, quad.object)
        if isinstance(term, pyoxigraph.NamedNode)
    }

    assert len(iris) == AANTAL_IRIS_GWSW16
    afwijkend = [
        iri
        for iri in iris
        if type(_uriref_snel(iri)) is not URIRef
        or _uriref_snel(iri) != URIRef(iri)
        or hash(_uriref_snel(iri)) != hash(URIRef(iri))
        or str(_uriref_snel(iri)) != str(URIRef(iri))
    ]
    assert afwijkend == []


def _slots(klasse: type) -> tuple[str, ...]:
    """Alle `__slots__` van een klasse en haar bovenklassen, zonder duplicaten."""
    gevonden: dict[str, None] = {}
    for basis in klasse.__mro__:
        for naam in getattr(basis, "__slots__", ()):
            gevonden[naam] = None
    return tuple(gevonden)


def test_literal_snelpad_zet_elk_intern_veld_dat_rdflib_zelf_zet() -> None:
    """Een rdflib-upgrade die een vijfde intern veld toevoegt, hoort hier op te vallen.

    De attribuutvergelijkingen hierboven kennen alleen de velden van vandaag. Een nieuw
    veld dat de constructor wel zet en het snelpad niet, zou daar doorheen glippen en pas
    veel later als een `AttributeError` bovenkomen -- een `Literal` draagt geen `__dict__`,
    dus een ongezet slot is geen `None` maar een fout. Deze test loopt daarom over de
    slots zelf en niet over een lijst die hier met de hand wordt bijgehouden.
    """
    velden = _slots(Literal)
    assert velden, "een `Literal` hoort zijn interne velden in `__slots__` te dragen"

    snel = _literal_string_snel("een waarde")
    traag = Literal("een waarde")

    for veld in velden:
        assert getattr(snel, veld) == getattr(traag, veld), veld


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
