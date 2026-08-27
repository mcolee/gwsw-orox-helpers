"""Leest de gedeclareerde waardebereiken (facetten) uit de GWSW-ontologie.

Elk GWSW-kenmerk verwijst via een `owl:hasValue`-restrictie naar een datatype `Dt_X`,
en dat datatype draagt via `owl:equivalentClass` een `owl:withRestrictions`-lijst met
`xsd:minInclusive`/`maxInclusive`. Deze module lost die keten op:

    Kenmerk -> allValuesFrom -> Dt_X -> equivalentClass -> withRestrictions -> min/max

Dit is de ontbrekende schakel uit issue #35: zonder haar blijft elke drempel handwerk
en kan een eigen check een waarde goedkeuren die de SHACL-nulmeting afkeurt. De module
*leest* alleen; hij vergelijkt niets met de projectdrempels en verandert niets aan een
run. Alleen de inclusieve grenzen worden gelezen -- de GWSW-facetten zijn dat allemaal.

Wat je met die uitkomsten *doet* -- ze erven naar subklassen, ze op korte naam terugbrengen
-- staat in `klassen`. Deze module kijkt daarom omlaag (naar `namen` en `graaf`) en nooit
omhoog naar de lader; dat is wat haar los houdt van `dataset`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from rdflib import OWL, RDFS, XSD, Graph, URIRef
from rdflib.collection import Collection

from gwsw_orox_helpers.graaf import GraafIndex
from gwsw_orox_helpers.namen import GWSW


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


def facetbereik(graph: Graph, datatype: URIRef) -> Facetbereik | None:
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
    for restrictie in Collection(graph, restricties):
        ondergrens = graph.value(restrictie, XSD.minInclusive)
        if ondergrens is not None:
            minimum = Decimal(str(ondergrens))
        bovengrens = graph.value(restrictie, XSD.maxInclusive)
        if bovengrens is not None:
            maximum = Decimal(str(bovengrens))

    onderliggend = graph.value(equivalent, OWL.onDatatype)
    naam = str(onderliggend).rsplit("#", 1)[-1] if onderliggend is not None else None
    return Facetbereik(datatype=naam, minimum=minimum, maximum=maximum)


def datatype_van_kenmerk(graph: Graph, kenmerk: URIRef) -> URIRef | None:
    """Vindt het `Dt_X`-datatype van een kenmerk via zijn `hasValue`-restrictie.

    De ontologie hangt onder een kenmerk een `owl:Restriction` op `gwsw:hasValue` met
    `owl:allValuesFrom gwsw:Dt_X`. Een kenmerk dat naar een kaal `xsd:integer` verwijst
    (dan is er geen `Dt_`-datatype met facetten) levert `None`.
    """
    has_value = URIRef(GWSW + "hasValue")
    for restrictie in graph.objects(kenmerk, RDFS.subClassOf):
        if graph.value(restrictie, OWL.onProperty) != has_value:
            continue
        doel = graph.value(restrictie, OWL.allValuesFrom)
        if isinstance(doel, URIRef) and doel.startswith(GWSW + "Dt_"):
            return doel
    return None


def kenmerkbereik(graph: Graph, kenmerk: URIRef) -> Facetbereik | None:
    """De hele keten: van een kenmerk naar het bereik van zijn datatype."""
    datatype = datatype_van_kenmerk(graph, kenmerk)
    if datatype is None:
        return None
    return facetbereik(graph, datatype)


def verwachte_property(graph: Graph | GraafIndex, kenmerk: URIRef) -> str | None:
    """De property die de ontologie voor de waarde van een kenmerk voorschrijft.

    De ontologie hangt onder een kenmerk een `owl:Restriction` die de waarde aan een
    property bindt: `owl:onProperty gwsw:hasReference` met `owl:allValuesFrom` een
    domeinlijstcollectie (zoals `WIONThemaColl`), of `owl:onProperty gwsw:hasValue`
    voor een vrije of getalswaarde. Dit levert `"hasReference"`, `"hasValue"`, of
    `None` als het kenmerk geen van beide restricties draagt (zoals `Straatnaam`).

    De verwijzende restrictie wint van de waarderestrictie: zij is het sterkste
    signaal, want zij bindt aan een concrete collectie. Dit is de schakel die
    ATTR-014 nodig heeft om te zien dat een export `hasValue` schrijft waar de
    ontologie `hasReference` eist; de SHACL-nulmeting mist die fout per constructie
    (issue #37).
    """
    has_value = URIRef(GWSW + "hasValue")
    has_reference = URIRef(GWSW + "hasReference")
    waarde: str | None = None
    for restrictie in graph.objects(kenmerk, RDFS.subClassOf):
        op = graph.value(restrictie, OWL.onProperty)
        if op == has_reference and graph.value(restrictie, OWL.allValuesFrom) is not None:
            return "hasReference"
        if op == has_value:
            waarde = "hasValue"
    return waarde


def functie_van_klasse(graph: Graph | GraafIndex, klasse: URIRef) -> str | None:
    """De functiewaarde die de ontologie aan een klasse bindt, als korte naam, of None.

    Het GWSW zegt wat een hulpstuk doet via een `owl:Restriction` op `gwsw:functie`
    met `owl:hasValue` (`T_stuk` → `VerbindenVanDrieLeidingen`, `Kruisstuk` →
    `VerbindenVanVierLeidingen`). TOP-022 en TOP-023 lezen daar het verwachte aantal
    leidingen uit (issue #60). Alleen de restricties direct op de klasse; het
    overerven naar subklassen doet `klassen._klassefuncties`.

    Tweeënveertig GWSW-klassen dragen meer dan een functiewaarde (`Zadel` bijvoorbeeld
    `LeidingaansluitingVerstevigen` en `VerstevigenAansluiting`). De volgorde waarin de
    graaf ze oplevert ligt niet vast, dus dit geeft de alfabetisch eerste terug: een
    willekeurige keuze zou dezelfde dataset tussen twee runs anders kunnen toetsen.
    """
    functie = URIRef(GWSW + "functie")
    waarden = set()
    for restrictie in graph.objects(klasse, RDFS.subClassOf):
        if graph.value(restrictie, OWL.onProperty) != functie:
            continue
        waarde = graph.value(restrictie, OWL.hasValue)
        if waarde is not None:
            waarden.add(str(waarde).removeprefix(GWSW))
    return min(waarden) if waarden else None
