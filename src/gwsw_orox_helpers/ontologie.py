"""Leest de gedeclareerde waardebereiken (facetten) uit de GWSW-ontologie.

Elk GWSW-kenmerk verwijst via een `owl:hasValue`-restrictie naar een datatype `Dt_X`,
en dat datatype draagt via `owl:equivalentClass` een `owl:withRestrictions`-lijst met
`xsd:minInclusive`/`maxInclusive`. Deze module lost die keten op:

    Kenmerk -> allValuesFrom -> Dt_X -> equivalentClass -> withRestrictions -> min/max

Dit is de ontbrekende schakel uit issue #35: zonder haar blijft elke drempel handwerk
en kan een eigen check een waarde goedkeuren die een SHACL-validatie afkeurt. De module
*leest* alleen; hij vergelijkt niets met de projectdrempels en verandert niets aan een
run. Alleen de inclusieve grenzen worden gelezen -- de GWSW-facetten zijn dat allemaal.

Wat je met die uitkomsten *doet* -- ze erven naar subklassen, ze op korte naam terugbrengen
-- staat in `klassen`. Deze module kijkt daarom omlaag (naar `namen` en `graaf`) en nooit
omhoog naar de lader; dat is wat haar los houdt van `dataset`.

**Elke lezer hier neemt `graaf.GraafLezer`**, en dat is geen gemak maar de kern van issue
#19: `load_dataset` leest de ontologie in een `GraafIndex` (zijn `restrictiebron`) en gaf
die aan `verwachte_property` en `functie_van_klasse`, terwijl `facetbereik`,
`datatype_van_kenmerk` en `kenmerkbereik` via `rdflib.collection.Collection` een echte
`Graph` eisten. Die drie draaiden daardoor alleen in tests -- de belofte van issue #35 was
op de echte leesweg niet aan te roepen en liep er op een `AttributeError` stuk.
`_lijstleden` wandelt de `rdf:first`/`rdf:rest`-ketting nu zelf, met niets anders dan de
`value` die allebei de vormen aanbieden.

Tot issue #21 stond die vrijheid er als union `Graph | GraafIndex`: een opsomming van de
twee vormen die het toevallig kunnen. `GraafLezer` (in `graaf`) zegt in plaats daarvan wat
deze module werkelijk vraagt -- `objects` en `value`, meer niet -- en `rdflib.Graph` en
`GraafIndex` vervullen dat allebei structureel. Voor de aanroeper verandert er niets: elke
`Graph` en elke `GraafIndex` die vroeger paste, past nog. Wat er wél verandert is de kant
van deze module: een lezer hier die een derde bewerking gaat gebruiken, wordt door mypy
tegengehouden tot het protocol verbreed is, in plaats van stil een van de twee vormen
onaanroepbaar te maken. Dat is precies de scheur die issue #19 moest repareren, nu
bewaakt in plaats van beschreven. Het bewijs dat allebei de vormen passen staat in
`tests/typecheck/graaflezer.py` en gaat door de poort mee (`[tool.mypy]` in
`pyproject.toml`).

**Wat hiermee nog niet af is**, en bewust niet: `load_dataset` bouwt zijn
ontologie-`GraafIndex` als lokale `restrictiebron` en bewaart hem niet op `GwswDataset`.
Een afnemer die deze lezers op een geladen dataset wil loslaten, moet de ontologie dus nog
altijd zelf inlezen. Dat dichten betekent een veld bij `GwswDataset`, en dat is een
bevroren contract (`CLAUDE.md`, Harde regels; `tests/test_publieke_api.py` pint de
handtekening): een auteursbeslissing, geen agentbeslissing.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal

from rdflib import OWL, RDF, RDFS, XSD, URIRef
from rdflib.term import Node as RdfNode

from gwsw_orox_helpers.graaf import GraafLezer
from gwsw_orox_helpers.namen import GWSW, termen_voor


@dataclass(frozen=True)
class Facetbereik:
    """Het gedeclareerde bereik van een GWSW-datatype.

    `datatype` is de korte naam van `owl:onDatatype` (`decimal`, `integer`). De grenzen
    zijn `Decimal` voor een exacte vergelijking met de projectdrempels, of `None` als de
    ontologie die kant niet vastlegt.
    """

    datatype: str | None
    minimum: Decimal | None
    maximum: Decimal | None


def _lijstleden(graph: GraafLezer, kop: RdfNode) -> Iterator[RdfNode]:
    """De leden van een RDF-lijst (`rdf:first`/`rdf:rest`), vanaf `kop`.

    De tegenhanger van `rdflib.collection.Collection` die het op de leesweg ook doet:
    `Collection` itereert via `Graph.items` en werkt dus alleen op een rdflib-`Graph`,
    terwijl `load_dataset` een `GraafIndex` als restrictiebron levert (issue #19). Deze
    wandeling gebruikt niets anders dan `value`, dat allebei de graafvormen aanbieden.

    **Intern, met een underscore**, ook al is het een algemeen bruikbaar RDF-primitief:
    `facetbereik` is de enige aanroeper, en deze module belooft naar buiten wat een
    `owl:Restriction` over een klasse of kenmerk zegt -- niet hoe je een RDF-lijst
    wandelt. In `graaf` hoort hij evenmin: die index kent met opzet geen enkele
    RDF-woordenschat (zie zijn moduledocstring), en dat hoeft ook niet -- dat een lijst
    met alleen `value` te wandelen is, is juist de reden dat `GraafIndex` geen
    collectie-bewerking hoeft aan te bieden. Meldt zich een tweede aanroeper, dan is de
    underscore weghalen een additieve stap.

    Het gedrag is dat van `Graph.items` -- de iterator achter `Collection`, en de
    ontlening is letterlijk: de lus, de `gezien`-verzameling die met de kop begint en de
    tekst van de fout komen daarvandaan (rdflib 7.6.0, BSD-3-Clause). Opzettelijk tot in
    de randgevallen; `tests/test_ontologie.py` houdt de twee lid voor lid en foutmelding
    voor foutmelding naast elkaar:

    - een **afgebroken lijst** (een schakel zonder `rdf:rest`) eindigt stil met wat er
      wél stond, net als een lijst die netjes op `rdf:nil` uitkomt. De ontologie is de
      bron van waarheid en niet de invoer van een gebruiker; een half geschreven lijst
      is een fout in het ontologiebestand, niet in de dataset die getoetst wordt, en de
      lezer die erop leunt merkt hem aan het ontbrekende facet;
    - een schakel **zonder `rdf:first`** slaat een lid over in plaats van `None` op te
      leveren;
    - een **cyclus** in `rdf:rest` is de enige harde fout: daar zou een stille afbreking
      een willekeurig afgekapt bereik opleveren, en dat is precies de stille verkeerde
      uitkomst die het manifest verbiedt. `Collection` gooide er een `ValueError` met
      deze tekst; die blijft, zodat wie hem ving hem blijft vangen.
    """
    gezien: set[RdfNode | None] = {kop}
    schakel: RdfNode | None = kop
    while schakel:
        lid = graph.value(schakel, RDF.first)
        if lid is not None:
            yield lid
        schakel = graph.value(schakel, RDF.rest)
        if schakel in gezien:
            raise ValueError("List contains a recursive rdf:rest reference")
        gezien.add(schakel)


def facetbereik(graph: GraafLezer, datatype: URIRef) -> Facetbereik | None:
    """Lost het bereik van een `Dt_X`-datatype op, of `None` als het er geen draagt.

    `None` betekent: geen `owl:equivalentClass` met een `owl:withRestrictions`-lijst.
    Een lijst met alleen een ondergrens levert een `Facetbereik` met `maximum` op `None`.
    """
    equivalent = graph.value(datatype, OWL.equivalentClass)
    if equivalent is None:
        return None
    restricties = graph.value(equivalent, OWL.withRestrictions)
    if restricties is None:
        return None

    minimum: Decimal | None = None
    maximum: Decimal | None = None
    for restrictie in _lijstleden(graph, restricties):
        ondergrens = graph.value(restrictie, XSD.minInclusive)
        if ondergrens is not None:
            minimum = Decimal(str(ondergrens))
        bovengrens = graph.value(restrictie, XSD.maxInclusive)
        if bovengrens is not None:
            maximum = Decimal(str(bovengrens))

    onderliggend = graph.value(equivalent, OWL.onDatatype)
    naam = str(onderliggend).rsplit("#", 1)[-1] if onderliggend is not None else None
    return Facetbereik(datatype=naam, minimum=minimum, maximum=maximum)


def datatype_van_kenmerk(graph: GraafLezer, kenmerk: URIRef, basis: str = GWSW) -> URIRef | None:
    """Vindt het `Dt_X`-datatype van een kenmerk via zijn `hasValue`-restrictie.

    De ontologie hangt onder een kenmerk een `owl:Restriction` op `gwsw:hasValue` met
    `owl:allValuesFrom gwsw:Dt_X`. Een kenmerk dat naar een kaal `xsd:integer` verwijst
    (dan is er geen `Dt_`-datatype met facetten) levert `None`.

    `basis` (issue #32) is de GWSW-basis van de graaf: default 1.6, zodat de bestaande
    aanroep ongewijzigd blijft; op een 1.7-ontologie geeft de aanroeper de 1.7-basis mee,
    zodat `hasValue` en `Dt_` in de goede versie gespeld worden.
    """
    termen = termen_voor(basis)
    has_value = URIRef(termen.has_value)
    for restrictie in graph.objects(kenmerk, RDFS.subClassOf):
        if graph.value(restrictie, OWL.onProperty) != has_value:
            continue
        doel = graph.value(restrictie, OWL.allValuesFrom)
        if isinstance(doel, URIRef) and doel.startswith(termen.dt_voorvoegsel):
            return doel
    return None


def kenmerkbereik(graph: GraafLezer, kenmerk: URIRef, basis: str = GWSW) -> Facetbereik | None:
    """De hele keten: van een kenmerk naar het bereik van zijn datatype."""
    datatype = datatype_van_kenmerk(graph, kenmerk, basis)
    if datatype is None:
        return None
    return facetbereik(graph, datatype)


def verwachte_property(graph: GraafLezer, kenmerk: URIRef, basis: str = GWSW) -> str | None:
    """De property die de ontologie voor de waarde van een kenmerk voorschrijft.

    De ontologie hangt onder een kenmerk een `owl:Restriction` die de waarde aan een
    property bindt: `owl:onProperty gwsw:hasReference` met `owl:allValuesFrom` een
    domeinlijstcollectie (zoals `WIONThemaColl`), of `owl:onProperty gwsw:hasValue`
    voor een vrije of getalswaarde. Dit levert `"hasReference"`, `"hasValue"`, of
    `None` als het kenmerk geen van beide restricties draagt (zoals `Straatnaam`).

    De verwijzende restrictie wint van de waarderestrictie: zij is het sterkste
    signaal, want zij bindt aan een concrete collectie. Dit is de schakel die een
    attribuutcheck nodig heeft om te zien dat een export `hasValue` schrijft waar de
    ontologie `hasReference` eist; een SHACL-validatie mist die fout per constructie
    (issue #37).

    `basis` (issue #32) is de GWSW-basis van de graaf; default 1.6.
    """
    termen = termen_voor(basis)
    has_value = URIRef(termen.has_value)
    has_reference = URIRef(termen.has_reference)
    waarde: str | None = None
    for restrictie in graph.objects(kenmerk, RDFS.subClassOf):
        op = graph.value(restrictie, OWL.onProperty)
        if op == has_reference and graph.value(restrictie, OWL.allValuesFrom) is not None:
            return "hasReference"
        if op == has_value:
            waarde = "hasValue"
    return waarde


def functie_van_klasse(graph: GraafLezer, klasse: URIRef, basis: str = GWSW) -> str | None:
    """De functiewaarde die de ontologie aan een klasse bindt, als korte naam, of None.

    Het GWSW zegt wat een hulpstuk doet via een `owl:Restriction` op `gwsw:functie`
    met `owl:hasValue` (`T_stuk` → `VerbindenVanDrieLeidingen`, `Kruisstuk` →
    `VerbindenVanVierLeidingen`). Een topologiecheck leest daar het verwachte aantal
    leidingen van een hulpstuk uit (issue #60). Alleen de restricties direct op de klasse; het
    overerven naar subklassen doet `klassen._klassefuncties`.

    Tweeënveertig GWSW-klassen dragen meer dan een functiewaarde (`Zadel` bijvoorbeeld
    `LeidingaansluitingVerstevigen` en `VerstevigenAansluiting`). De volgorde waarin de
    graaf ze oplevert ligt niet vast, dus dit geeft de alfabetisch eerste terug: een
    willekeurige keuze zou dezelfde dataset tussen twee runs anders kunnen toetsen.

    `basis` (issue #32) is de GWSW-basis van de graaf; default 1.6.
    """
    functie = URIRef(termen_voor(basis).functie)
    waarden = set()
    for restrictie in graph.objects(klasse, RDFS.subClassOf):
        if graph.value(restrictie, OWL.onProperty) != functie:
            continue
        waarde = graph.value(restrictie, OWL.hasValue)
        if waarde is not None:
            waarden.add(str(waarde).removeprefix(basis))
    return min(waarden) if waarden else None
