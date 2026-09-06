"""De GWSW-klassenhierarchie en de kleine woordenboeken die de lader eruit afleidt.

Alle drie de uitkomsten hebben dezelfde vorm en dezelfde bron: een graaf met
klassenkennis erin -- de ontologie, of bij een handgeschreven fixture de dataset zelf --
en daaruit een woordenboek dat verder zonder graaf te lezen is. `subclasses` draagt per
klasse haar afsluiting, `kenmerk_property` per kenmerktype de property die de ontologie
voor zijn waarde voorschrijft, en `functie_per_klasse` per hulpstukklasse haar functie.

Wat ze delen is de terugval: **zonder klassenkennis blijft een afsluiting op de wortel
zelf steken**, en dan valt de lezing terug op geometrie. Die terugval staat een keer, in
`_afsluiting`. Stond hij er twee keer, dan zou een van beide bij een wijziging
achterblijven zonder dat het opvalt -- een afsluiting die stilzwijgend krimpt levert geen
fout op maar een lege selectie. `_bruikbare_afsluiting` is dezelfde vraag met een
antwoord dat je kunt zien: `None` waar de afsluiting singleton bleef.

Deze module leest de restricties niet zelf; dat doet `ontologie`. Hier staat wat je met
die uitkomsten doet: erven, afsluiten en op korte naam terugbrengen. Het *spellen* van
zo'n naam staat er sinds issue #29 niet meer bij: `_uri` en `_short` zijn twee `rsplit`-en
op een string en wonen in `namen`, naast de IRI's die ze uit elkaar halen. Deze module
gebruikt ze nog volop -- hij haalt ze alleen daar op, net als `inlezen` en `dataset`, die
er anders een rand naar de klassenlaag voor overhielden.
"""

from __future__ import annotations

from rdflib import RDFS, URIRef

from gwsw_orox_helpers.graaf import GraafIndex
from gwsw_orox_helpers.namen import GWSW, _short, _uri
from gwsw_orox_helpers.ontologie import functie_van_klasse, verwachte_property

# De twee wortels waarmee de lader knopen en strengen uit de graaf haalt. Blijft de
# afsluiting van een van beide op de wortel zelf steken, dan valt dat lezen terug op
# geometrie; `GwswDataset.klassenhierarchie_bekend` is precies die vraag.
WORTEL_KNOOPPUNT = "Knooppunt"
WORTEL_VERBINDING = "Verbinding"
WORTELS_VOOR_HERKENNING = (WORTEL_KNOOPPUNT, WORTEL_VERBINDING)

WORTEL_HULPSTUK = "Hulpstuk"
WORTEL_HULPSTUKORIENTATIE = "Hulpstukorientatie"

# De Putdeksel-klasse waarvan de lezing en de lader de afsluiting maken (issue #68). Een
# korte klassenaam, net als de `WORTEL_*` hierboven; hij stond op `inlezen` en `laden` nog
# als kale literal naast de plekken die hem gebruikten. Een hernoeming zou anders stil langs
# beide literalen glippen -- de put verliest dan haar dekselniveau en valt terug op maaiveld.
KLASSE_PUTDEKSEL = "Putdeksel"


def _afsluiting(
    subclasses: dict[str, frozenset[str]], wortel: str, basis: str = GWSW
) -> frozenset[str]:
    """De subklasse-afsluiting van een wortel; zonder klassenkennis de wortel zelf.

    De enige plek waar die terugval opgeschreven staat. Stond hij er twee keer, dan
    zou een van beide bij een wijziging achterblijven zonder dat het opvalt: een
    afsluiting die stilzwijgend krimpt levert geen fout op maar een lege selectie.

    Bewust geen `subclasses.get(_uri(wortel), frozenset({_uri(wortel)}))`: die default
    is een gewoon argument en wordt dus ook opgebouwd op de treffer, met een tweede
    `_uri`-aanroep erbij. `GwswDataset.closure` vraagt deze functie via `is_a` ruim een
    miljoen keer per run (issue #12), en dan telt een wegwerp-frozenset per
    aanroep mee. Het antwoord is aan beide kanten hetzelfde als voorheen.

    `basis` (issue #32) is de gedetecteerde GWSW-basis waarin de sleutel wordt opgebouwd;
    default is de gepinde 1.6-naamruimte, zodat de bestaande aanroep ongewijzigd 1.6 spelt.
    Op een 1.7-dataset geeft de aanroeper de 1.7-basis mee, zodat `_uri(wortel, basis)` de
    1.7-IRI opbouwt en die in de (dan 1.7-gesleutelde) `subclasses` terugvindt.
    """
    uri = _uri(wortel, basis)
    afsluiting = subclasses.get(uri)
    return frozenset({uri}) if afsluiting is None else afsluiting


def _bruikbare_afsluiting(
    subclasses: dict[str, frozenset[str]], wortel: str, basis: str = GWSW
) -> frozenset[str] | None:
    """De subklasse-afsluiting van een wortel, of None als de ontologie ontbreekt."""
    afsluiting = _afsluiting(subclasses, wortel, basis)
    return afsluiting if len(afsluiting) > 1 else None


def _subclass_closure(graph: GraafIndex) -> dict[str, frozenset[str]]:
    """Berekent per klasse de verzameling van zichzelf en al haar subklassen."""
    kinderen: dict[str, set[str]] = {}
    for kind, ouder in graph.subject_objects(RDFS.subClassOf):
        if isinstance(kind, URIRef) and isinstance(ouder, URIRef):
            kinderen.setdefault(str(ouder), set()).add(str(kind))

    afsluiting: dict[str, frozenset[str]] = {}
    # Een eigen naam voor de lus: `ouder` hierboven is een rdflib-term, hier een str.
    for klasse in kinderen:
        gezien = {klasse}
        stapel = [klasse]
        while stapel:
            huidig = stapel.pop()
            for afstammeling in kinderen.get(huidig, ()):
                if afstammeling not in gezien:
                    gezien.add(afstammeling)
                    stapel.append(afstammeling)
        afsluiting[klasse] = frozenset(gezien)
    return afsluiting


def _kenmerk_properties(
    graph: GraafIndex, subclasses: dict[str, frozenset[str]], basis: str = GWSW
) -> dict[str, str]:
    """Per kenmerktype de property die de ontologie voor zijn waarde voorschrijft.

    Loopt over de subklassen van `Kenmerk` en houdt alleen de types die een
    `hasValue`- of `hasReference`-restrictie dragen. Leest uit dezelfde graaf als
    `subclasses` (de ontologie, of bij een fixture de dataset zelf), zodat het met
    `--geen-ontologie` en inline-hierarchieen meebeweegt. Zonder klassenkennis blijft
    de afsluiting op `Kenmerk` zelf steken en levert dit een leeg woordenboek.

    `basis` (issue #32) is de basis van de restrictiebron: dezelfde als waarin `subclasses`
    gesleuteld staat, zodat `_afsluiting` de `Kenmerk`-afsluiting terugvindt en
    `verwachte_property` de restrictie-IRI's in de goede versie opbouwt.
    """
    gevonden: dict[str, str] = {}
    for uri in _afsluiting(subclasses, "Kenmerk", basis):
        property_ = verwachte_property(graph, URIRef(uri), basis)
        if property_ is not None:
            gevonden[_short(uri)] = property_
    return gevonden


def _klassefuncties(
    graph: GraafIndex, subclasses: dict[str, frozenset[str]], basis: str = GWSW
) -> dict[str, str]:
    """Per hulpstukklasse de functiewaarde uit de ontologie, overgeerfd naar subklassen.

    Loopt over de afsluiting van `Hulpstuk`; een klasse met een eigen restrictie wint
    van wat zij van een bovenklasse zou erven. Sleutel is de volledige URI, zodat een
    knoop er met zijn `types` direct in kan kijken.

    `basis` (issue #32) is de basis van de restrictiebron, net als bij
    `_kenmerk_properties`.
    """
    eigen: dict[str, str] = {}
    for uri in _afsluiting(subclasses, WORTEL_HULPSTUK, basis):
        functie = functie_van_klasse(graph, URIRef(uri), basis)
        if functie is not None:
            eigen[uri] = functie
    gevonden = dict(eigen)
    for uri, functie in sorted(eigen.items()):
        for sub in _afsluiting(subclasses, _short(uri), basis):
            gevonden.setdefault(sub, functie)
    return gevonden
