"""Van een gevulde graaf naar knopen en strengen: de domeinlezers van deze package.

Alles wat de graaf *bevraagt* om het domeinmodel te vullen staat hier: de twee
schrijfrichtingen van hasPart en hasAspect, de kenmerklezers en de twee grote lezers
`_read_nodes` en `_read_conduits`. `dataset` zet er de dataset omheen en biedt de
uitkomst aan; `domein` draagt de objecten die hier gevuld worden.

**Het bestand zelf staat er niet meer in.** Het parsen, de codering en het procesbrede
GC-neveneffect wonen sinds issue #26 in `bestand` (`_parse`, `_decode`, `_quiet_rdflib`,
`_gc_uit`). De twee clusters deelden alleen de `GraafIndex`: wat hier staat krijgt die
index gevuld aangeleverd en kent geen paden, geen bytes en geen coderingen. In de
lagentabel staat `bestand` ónder deze module -- hij leunt alleen op de bladeren -- maar
er loopt geen rand tússen de twee: deze module importeert hem niet en her-exporteert hem
niet, `dataset` haalt `_parse` en `_gc_uit` er rechtstreeks op.
`test_de_bestandssnit_ligt_vast` houdt dat zo.

De IRI's staan hier als `URIRef`, gemaakt uit de tekst in `namen`. Ze komen via `dataset`
naar buiten -- dat is het oppervlak dat nlriochecker kent -- en horen daarom bij de laag
die ze leest, niet bij de tekstmodule die ze spelt.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from datetime import date

from rdflib import RDF, RDFS, URIRef
from rdflib.term import Node as RdfNode

from gwsw_orox_helpers import namen
from gwsw_orox_helpers.domein import Aspect, Conduit, Inwinning, Koppelingsherstel, Node, _as_date
from gwsw_orox_helpers.geometry import (
    GeometryError,
    is_multipart_literal,
    parse_gml_met_z,
)
from gwsw_orox_helpers.graaf import GraafIndex, _uriref_snel
from gwsw_orox_helpers.klassen import _afsluiting

# Naast `from gwsw_orox_helpers import namen` hierboven, en met opzet: `_short` staat in de
# hete lus (per aspect en per object, op een gemeentebrede export honderdduizenden keren)
# en een `namen._short(...)` zou daar een attribuutopzoeking per aanroep bij zetten. Het
# is dezelfde functie; alleen de naam is hier lokaal.
from gwsw_orox_helpers.namen import _short

# `RDF.type` en `RDFS.label` zijn geen attributen maar een `__getattr__` op rdflib's
# `DefinedNamespace`, en die kost bijna een microseconde per keer. De lezers hieronder
# stellen die vraag per aspect en per object -- op de De Wolden en Hoogeveen-export bijna
# negenhonderdduizend keer, samen ruim acht tiende seconde. Een keer opvragen en daarna
# de naam gebruiken kost er zestien nanoseconde van; het is dezelfde term.
#
# `dataset` leent `_RDF_TYPE` hiervandaan (issue #23) in plaats van er een tweede naast te
# zetten: de `URIRef`-vorm van een GWSW-IRI woont in deze module (`docs/architectuur.md`).
_RDF_TYPE = RDF.type
_RDFS_LABEL = RDFS.label

HAS_ASPECT = URIRef(namen.HAS_ASPECT)
HAS_PART = URIRef(namen.HAS_PART)
# Het GWSW declareert `isPartOf owl:inverseOf hasPart` en `isAspectOf owl:inverseOf
# hasAspect`. Een conforme export mag dus de inverse schrijven; wie alleen de
# voorwaartse richting leest, krijgt van zo'n export een leeg domeinmodel zonder een
# enkele melding. Lees daarom beide, net als bij hasConnection.
IS_PART_OF = URIRef(namen.IS_PART_OF)
IS_ASPECT_OF = URIRef(namen.IS_ASPECT_OF)
HAS_CONNECTION = URIRef(namen.HAS_CONNECTION)
HAS_VALUE = URIRef(namen.HAS_VALUE)
HAS_REFERENCE = URIRef(namen.HAS_REFERENCE)

KLASSE_INWINNING = URIRef(f"{namen.GWSW}Inwinning")
KLASSE_WIJZE_VAN_INWINNING = URIRef(f"{namen.GWSW}WijzeVanInwinning")
KLASSE_DATUM_INWINNING = URIRef(f"{namen.GWSW}DatumInwinning")
KLASSE_MAAIVELDORIENTATIE = URIRef(f"{namen.GWSW}Maaiveldorientatie")
KLASSE_MAAIVELDHOOGTE = URIRef(f"{namen.GWSW}Maaiveldhoogte")
KLASSE_PUTDEKSELNIVEAU = URIRef(f"{namen.GWSW}Putdekselniveau")

KLASSE_PUNT = URIRef(f"{namen.GWSW}Punt")
KLASSE_LIJN = URIRef(f"{namen.GWSW}Lijn")
# Het GWSW kent drie soorten verbindingen, elk met een eigen begin- en eindvertex.
# Alle zes zijn subklassen van gwsw:Vertex.
KLASSEN_BEGINPUNT = tuple(
    URIRef(f"{namen.GWSW}{naam}")
    for naam in ("BeginpuntLeiding", "BeginpuntOnderdeel", "BeginpuntAfvoerrelatie")
)
KLASSEN_EINDPUNT = tuple(
    URIRef(f"{namen.GWSW}{naam}")
    for naam in ("EindpuntLeiding", "EindpuntOnderdeel", "EindpuntAfvoerrelatie")
)
KLASSE_BEGINPUNT = KLASSEN_BEGINPUNT[0]
KLASSE_EINDPUNT = KLASSEN_EINDPUNT[0]
KLASSE_BOB_BEGIN = URIRef(f"{namen.GWSW}BobBeginpuntLeiding")
KLASSE_BOB_EIND = URIRef(f"{namen.GWSW}BobEindpuntLeiding")

# De staart die de BrutIS-export achter de naam van een hulpstuk plakt in het
# hasConnection-doel van een leidingeinde, waar de orientatie zelf anders heet.
FANTOOM_STAART = "_put"


# --------------------------------------------------------------------------------------
# De twee schrijfrichtingen van hasPart, hasAspect en hasConnection
# --------------------------------------------------------------------------------------


def _beide_richtingen(
    voorwaarts: Iterable[RdfNode], invers: Iterable[RdfNode]
) -> Iterator[RdfNode]:
    """De termen uit beide schrijfrichtingen, elk hoogstens een keer.

    Een export mag `hasPart` schrijven, `isPartOf`, of allebei; in het laatste geval
    zou een dubbel kenmerk of een dubbel onderdeel ontstaan. De voorwaartse richting
    gaat voorop, zodat de volgorde niet verandert voor de exports die alleen die
    richting schrijven.
    """
    gezien: set[RdfNode] = set()
    for term in voorwaarts:
        gezien.add(term)
        yield term
    for term in invers:
        if term not in gezien:
            yield term


def parts_of(graph: GraafIndex, subject: RdfNode) -> Iterator[RdfNode]:
    """De onderdelen van een object, in beide schrijfrichtingen van hasPart."""
    return _beide_richtingen(graph.objects(subject, HAS_PART), graph.subjects(IS_PART_OF, subject))


def part_holders_of(graph: GraafIndex, subject: RdfNode) -> Iterator[RdfNode]:
    """De objecten die dit object als onderdeel bevatten, in beide schrijfrichtingen."""
    return _beide_richtingen(graph.subjects(HAS_PART, subject), graph.objects(subject, IS_PART_OF))


def aspects_of(graph: GraafIndex, subject: RdfNode) -> Iterator[RdfNode]:
    """De aspecten van een object, in beide schrijfrichtingen van hasAspect."""
    return _beide_richtingen(
        graph.objects(subject, HAS_ASPECT), graph.subjects(IS_ASPECT_OF, subject)
    )


def aspect_holders_of(graph: GraafIndex, subject: RdfNode) -> Iterator[RdfNode]:
    """De objecten die dit object als aspect dragen, in beide schrijfrichtingen."""
    return _beide_richtingen(
        graph.subjects(HAS_ASPECT, subject), graph.objects(subject, IS_ASPECT_OF)
    )


def _connections(graph: GraafIndex, subject: RdfNode):
    """De hasConnection-buren van een object, in beide schrijfrichtingen."""
    yield from graph.objects(subject, HAS_CONNECTION)
    yield from graph.subjects(HAS_CONNECTION, subject)


# --------------------------------------------------------------------------------------
# De kenmerken aan een object
# --------------------------------------------------------------------------------------


def _read_aspects(graph: GraafIndex, subject: RdfNode) -> tuple[Aspect, ...]:
    """Leest de kenmerken die via hasAspect aan een object hangen.

    Aspecten zonder waarde en zonder verwijzing zijn geen kenmerken maar
    orientaties en geometrieen; die horen hier niet thuis en vallen af.
    """
    gevonden: list[Aspect] = []
    for aspect in aspects_of(graph, subject):
        waarde = graph.value(aspect, HAS_VALUE)
        referentie = graph.value(aspect, HAS_REFERENCE)
        if waarde is None and referentie is None:
            continue
        inwinning = _read_inwinning(graph, aspect)
        for soort in graph.objects(aspect, _RDF_TYPE):
            gevonden.append(
                Aspect(
                    kind=_short(str(soort)),
                    value=str(waarde) if waarde is not None else None,
                    reference=_short(str(referentie)) if referentie is not None else None,
                    inwinning=inwinning,
                )
            )
    return tuple(gevonden)


def _read_inwinning(graph: GraafIndex, subject: RdfNode) -> Inwinning | None:
    """Leest de inwinningsmetagegevens die aan een kenmerk hangen."""
    for aspect in aspects_of(graph, subject):
        if (aspect, _RDF_TYPE, KLASSE_INWINNING) not in graph:
            continue
        wijze: str | None = None
        datum: date | None = None
        for deel in aspects_of(graph, aspect):
            if (deel, _RDF_TYPE, KLASSE_WIJZE_VAN_INWINNING) in graph:
                referentie = graph.value(deel, HAS_REFERENCE)
                wijze = _short(str(referentie)) if referentie is not None else None
            elif (deel, _RDF_TYPE, KLASSE_DATUM_INWINNING) in graph:
                waarde = graph.value(deel, HAS_VALUE)
                datum = _as_date(str(waarde)) if waarde is not None else None
        gevonden = Inwinning(wijze=wijze, datum=datum)
        if gevonden:
            return gevonden
    return None


def _aspect_van_klasse(graph: GraafIndex, subject: RdfNode, klasse: URIRef) -> Aspect | None:
    """Het kenmerk van deze klasse dat direct aan het object hangt."""
    for aspect in aspects_of(graph, subject):
        if (aspect, _RDF_TYPE, klasse) not in graph:
            continue
        waarde = graph.value(aspect, HAS_VALUE)
        if waarde is None:
            continue
        return Aspect(
            kind=_short(str(klasse)),
            value=str(waarde),
            inwinning=_read_inwinning(graph, aspect),
        )
    return None


def _maaiveld_kenmerk(
    graph: GraafIndex, orientation: RdfNode
) -> tuple[Aspect | None, Inwinning | None]:
    """De maaiveldhoogte bij een knooppunt, met de herkomst ervan.

    Het GWSW hangt het maaiveld niet aan de put zelf maar aan een aparte
    maaiveldorientatie, die via hasConnection aan de putorientatie hangt.
    """
    for buur in _connections(graph, orientation):
        if (buur, _RDF_TYPE, KLASSE_MAAIVELDORIENTATIE) not in graph:
            continue
        aspect = _aspect_van_klasse(graph, buur, KLASSE_MAAIVELDHOOGTE)
        if aspect is not None:
            return aspect, _herkomst(graph, buur, aspect)
    return None, None


def _herkomst(graph: GraafIndex, orientation: RdfNode, aspect: Aspect) -> Inwinning | None:
    """De inwinning van een kenmerk, met terugval op die van de puntgeometrie.

    De BrutIS-export van De Wolden en Hoogeveen hangt een record-brede inwinningswijze aan het
    Punt-aspect van de orientatie en herhaalt hem op het kenmerk zelf. Bij AHN2
    blijft die herhaling uit: dan staat de wijze uitsluitend op het Punt. Zonder
    deze terugval zou juist de uit het AHN afgeleide helft van de maaiveldhoogten
    als herkomstloos gelden.
    """
    if aspect.inwinning is not None:
        return aspect.inwinning
    punt = _aspect_van_klasse(graph, orientation, KLASSE_PUNT)
    return punt.inwinning if punt is not None else None


def _deksel_kenmerk(
    graph: GraafIndex, subject: RdfNode, deksel_klassen: frozenset[URIRef]
) -> tuple[Aspect | None, Inwinning | None]:
    """Het putdekselniveau van een put, met de herkomst ervan.

    Het niveau hangt aan de dekselorientatie van een Putdeksel-onderdeel; sommige
    exports hangen het rechtstreeks aan de put. Beide wegen worden gevolgd. De
    herkomst volgt dezelfde terugval als bij de maaiveldhoogte: staat er geen
    inwinning op het kenmerk zelf, dan telt die van de puntgeometrie ernaast.

    `deksel_klassen` is de subklasse-afsluiting van Putdeksel, niet een enkele
    klasse: het GWSW kent `Putdeksel_LichtVerkeer` en `Putdeksel_ZwaarVerkeer` als
    subklassen, en een exacte typevergelijking zou zo'n put stilzwijgend haar
    dekselniveau afnemen -- waarna `Node.bovenkant` op het maaiveld terugvalt zonder
    dat iemand het merkt.

    Hij komt binnen als **termen** en niet als tekst (issue #23). Die drie klassen zijn
    voor de hele lezing dezelfde en de membershiptest hieronder gebeurt per put én per
    onderdeel daarvan; ze hier uit tekst opbouwen betekende dus dezelfde handvol
    `URIRef`-constructies tienduizenden keren over. `_read_nodes` zet ze een keer om,
    buiten de knopenlus, met `graaf._uriref_snel` -- dezelfde term als `URIRef()`, dus
    dezelfde membership.

    **Wat hier niet gedekt is.** De afsluiting stopt bij `Putdeksel`. Het GWSW hangt
    onder `Deksel` ook `Straatpot`, `Drainputdeksel` en `Peilbuisdeksel` -- zusters
    van `Putdeksel`, geen subklassen -- en onder `Afdekking` daarnaast `Rooster`,
    `Luik` en `Afdekplaat`. Een put met een `Straatpot` die netjes een
    `Dekselorientatie` met een `Putdekselniveau` draagt, verliest dat niveau hier dus
    nog steeds, met dezelfde stille terugval op het maaiveld. Verbreden naar `Deksel`
    of `Afdekking` is een domeinkeuze -- telt het niveau onder een rooster als
    putdekselniveau? -- en die ligt bij de auteur, niet hier. Zie het rapport bij
    issue #36.
    """
    direct = _aspect_van_klasse(graph, subject, KLASSE_PUTDEKSELNIVEAU)
    if direct is not None:
        return direct, _herkomst(graph, subject, direct)

    for deel in parts_of(graph, subject):
        if not any((deel, _RDF_TYPE, klasse) in graph for klasse in deksel_klassen):
            continue
        for orientatie in aspects_of(graph, deel):
            aspect = _aspect_van_klasse(graph, orientatie, KLASSE_PUTDEKSELNIVEAU)
            if aspect is not None:
                return aspect, _herkomst(graph, orientatie, aspect)
        aspect = _aspect_van_klasse(graph, deel, KLASSE_PUTDEKSELNIVEAU)
        if aspect is not None:
            return aspect, _herkomst(graph, deel, aspect)
    return None, None


def _bob(graph: GraafIndex, endpoint: RdfNode | None, klasse: URIRef) -> Aspect | None:
    """Het BOB-kenmerk dat aan een strengeindpunt hangt, met zijn inwinning."""
    if endpoint is None:
        return None
    return _aspect_van_klasse(graph, endpoint, klasse)


# --------------------------------------------------------------------------------------
# De knopen en de strengen
# --------------------------------------------------------------------------------------


def _label(graph: GraafIndex, subject: RdfNode) -> str:
    """Het rdfs:label van een object, of een lege tekst."""
    waarde = graph.value(subject, _RDFS_LABEL)
    return str(waarde) if waarde is not None else ""


def _types(graph: GraafIndex, subject: RdfNode) -> frozenset[str]:
    """Alle rdf:type-waarden van een object."""
    return frozenset(str(waarde) for waarde in graph.objects(subject, _RDF_TYPE))


def _geometry(graph: GraafIndex, orientation: RdfNode, klasse: URIRef, errors: dict[str, str]):
    """Zoekt de geometrie van een orientatie en geeft die met haar z-waarden terug.

    Via `parse_gml_met_z` en niet via `parse_gml` plus `parse_gml_z`: die twee zouden
    dezelfde literaal twee tot vijf keer regexen en naar floats omzetten, en dit is het
    pad dat dat voor elke geometrie in de export doet. De uitkomst en elke foutmelding
    zijn per contract dezelfde (`test_parse_gml_met_z_is_gelijkwaardig_aan_de_twee_losse_lezers`);
    een onleesbare literaal belandt dus nog altijd in `errors` en levert `None, []` op.
    """
    for aspect in aspects_of(graph, orientation):
        if (aspect, _RDF_TYPE, klasse) not in graph:
            continue
        literal = graph.value(aspect, HAS_VALUE)
        if literal is None:
            continue
        try:
            return parse_gml_met_z(str(literal))
        except GeometryError as error:
            errors[str(orientation)] = str(error)
            return None, []
    return None, []


def _read_nodes(
    graph: GraafIndex,
    errors: dict[str, str],
    knooppunt_klassen: frozenset[str] | None = None,
    deksel_klassen: frozenset[str] | None = None,
) -> dict[str, Node]:
    """Leest de knooppunten van het netwerk.

    Het GWSW definieert een knoop als een object met een orientatie van het type
    Knooppunt. Is de ontologie beschikbaar, dan wordt die definitie gevolgd; anders
    valt de lader terug op de structurele herkenning (een orientatie met een
    puntgeometrie), zodat een dataset ook zonder ontologie leesbaar blijft.
    """
    nodes: dict[str, Node] = {}
    deksel_klassen = deksel_klassen or _afsluiting({}, "Putdeksel")
    # Een keer, buiten de lus: `_deksel_kenmerk` toetst deze handvol klassen per put en
    # per onderdeel daarvan, en bouwde ze tot issue #23 elke keer opnieuw uit tekst op.
    deksel_termen = frozenset(_uriref_snel(klasse) for klasse in deksel_klassen)

    if knooppunt_klassen:
        bron = _orientations_of_class(graph, knooppunt_klassen)
    else:
        bron = _orientations_with(graph, KLASSE_PUNT)

    for orientation in bron:
        point, z_waarden = _geometry(graph, orientation, KLASSE_PUNT, errors)
        maaiveld, maaiveld_inwinning = _maaiveld_kenmerk(graph, orientation)
        multipart = _is_multipart(graph, orientation, KLASSE_PUNT)
        for subject in aspect_holders_of(graph, orientation):
            uri = str(subject)
            if uri in nodes:
                continue
            deksel, deksel_inwinning = _deksel_kenmerk(graph, subject, deksel_termen)
            nodes[uri] = Node(
                uri=uri,
                label=_label(graph, subject),
                types=_types(graph, subject),
                orientation=str(orientation),
                orientation_types=_types(graph, orientation),
                point=point,
                z=z_waarden[0] if z_waarden else None,
                parents=_parents(graph, subject),
                aspects=_read_aspects(graph, subject),
                maaiveld_aspect=maaiveld,
                maaiveld_inwinning=maaiveld_inwinning,
                deksel_aspect=deksel,
                deksel_inwinning=deksel_inwinning,
                multipart=multipart,
            )

    return nodes


def _parents(graph: GraafIndex, subject: RdfNode) -> tuple[str, ...]:
    """De objecten die dit object via hasPart bevatten, oplopend gesorteerd.

    Alle houders en niet de eerste: het GWSW staat er meer dan een toe (een `Put`
    hangt onder een Afwateringsgebied *en* een Straat, een `Overstortdrempel` onder
    een Overstortput of een Overstortconstructie), en welke houder rdflib het eerst
    oplevert hangt af van de schrijfvolgorde van de export. Een enkele houder
    onthouden zou de wandeling van `klim_naar_knoop` op de verkeerde tak kunnen
    zetten en daar laten doodlopen. De sortering maakt die wandeling reproduceerbaar.
    """
    return tuple(
        sorted(
            {
                str(houder)
                for houder in part_holders_of(graph, subject)
                if isinstance(houder, URIRef) and houder != subject
            }
        )
    )


def _orientations_of_class(graph: GraafIndex, klassen: frozenset[str]):
    """De orientaties waarvan het type in deze verzameling klassen valt."""
    gezien = set()
    for klasse in klassen:
        for orientation in graph.subjects(_RDF_TYPE, URIRef(klasse)):
            if orientation not in gezien:
                gezien.add(orientation)
                yield orientation


def _orientations_with(graph: GraafIndex, klasse: URIRef):
    """De orientaties die via hasAspect een geometrie van dit type dragen."""
    gezien = set()
    for aspect in graph.subjects(_RDF_TYPE, klasse):
        for orientation in aspect_holders_of(graph, aspect):
            if orientation not in gezien:
                gezien.add(orientation)
                yield orientation


def _read_conduits(
    graph: GraafIndex,
    nodes: dict[str, Node],
    errors: dict[str, str],
    verbinding_klassen: frozenset[str] | None = None,
    hulpstuk_klassen: frozenset[str] = frozenset(),
) -> tuple[dict[str, Conduit], Koppelingsherstel]:
    """Leest de verbindingen: leidingen en andere kanten van het netwerk.

    Net als bij de knopen geldt de ontologische definitie (een orientatie van het
    type Verbinding) zodra de ontologie beschikbaar is, met terugval op de
    structurele herkenning via begin- en eindvertices.

    Geeft naast de verbindingen het herstel van de fantoomkoppeling terug (issue #60).
    """
    orientation_to_node = {
        node.orientation: uri for uri, node in nodes.items() if node.orientation is not None
    }
    hulpstukken = frozenset(
        uri for uri, node in nodes.items() if node.orientation_types & hulpstuk_klassen
    )
    hersteld: list[str] = []
    conduits: dict[str, Conduit] = {}

    bron = (
        _orientations_of_class(graph, verbinding_klassen)
        if verbinding_klassen
        else _leiding_orientations(graph)
    )
    for orientation in bron:
        line, z_waarden = _geometry(graph, orientation, KLASSE_LIJN, errors)
        multipart = _is_multipart(graph, orientation, KLASSE_LIJN)
        begin = _endpoint(graph, orientation, KLASSEN_BEGINPUNT)
        eind = _endpoint(graph, orientation, KLASSEN_EINDPUNT)

        for subject in aspect_holders_of(graph, orientation):
            uri = str(subject)
            if uri in conduits:
                continue
            # Draagt één orientatie twee leidingen, dan telt hetzelfde herstelde eind
            # twee keer in `koppelingen`; `hulpstukken` klopt wel, want dat gaat via een
            # set. Het referentievoorbeeld heeft nul van zulke orientaties.
            conduits[uri] = Conduit(
                uri=uri,
                label=_label(graph, subject),
                types=_types(graph, subject),
                line=line,
                start_node=_connected_node(
                    graph, begin, orientation_to_node, hulpstukken, hersteld
                ),
                end_node=_connected_node(graph, eind, orientation_to_node, hulpstukken, hersteld),
                bob_start_aspect=_bob(graph, begin, KLASSE_BOB_BEGIN),
                bob_end_aspect=_bob(graph, eind, KLASSE_BOB_EIND),
                aspects=_read_aspects(graph, subject),
                multipart=multipart,
                z_values=tuple(z_waarden),
            )

    return conduits, Koppelingsherstel(len(hersteld), len(set(hersteld)))


def _is_multipart(graph: GraafIndex, orientation: RdfNode, klasse: URIRef) -> bool:
    """Geeft aan of de geometrie van deze orientatie uit meerdere losse delen bestaat.

    Twee vormen tellen mee: een GML-literaal met een multi-geometrie erin, en meer
    dan een geometrie-aspect van dezelfde soort aan dezelfde orientatie.
    """
    literalen = [
        str(graph.value(aspect, HAS_VALUE))
        for aspect in aspects_of(graph, orientation)
        if (aspect, _RDF_TYPE, klasse) in graph and graph.value(aspect, HAS_VALUE) is not None
    ]
    if len(literalen) > 1:
        return True
    return any(is_multipart_literal(literal) for literal in literalen)


def _leiding_orientations(graph: GraafIndex):
    """De orientaties die een begin- of eindpunt van een leiding bevatten."""
    gezien = set()
    for klasse in (*KLASSEN_BEGINPUNT, *KLASSEN_EINDPUNT):
        for endpoint in graph.subjects(_RDF_TYPE, klasse):
            for orientation in part_holders_of(graph, endpoint):
                if orientation not in gezien:
                    gezien.add(orientation)
                    yield orientation


def _endpoint(
    graph: GraafIndex, orientation: RdfNode, klassen: tuple[URIRef, ...]
) -> RdfNode | None:
    """Het begin- of eindpunt van een verbinding, van welke soort dan ook."""
    for part in parts_of(graph, orientation):
        if any((part, _RDF_TYPE, klasse) in graph for klasse in klassen):
            return part
    return None


def _connected_node(
    graph: GraafIndex,
    endpoint: RdfNode | None,
    orientation_to_node: dict[str, str],
    hulpstukken: frozenset[str] = frozenset(),
    hersteld: list[str] | None = None,
) -> str | None:
    """Herleidt de hasConnection van een strengeindpunt naar de put erachter.

    Twee dingen die uit de GWSW-documentatie volgen. De koppeling wijst naar de
    putorientatie, niet naar de put zelf; die extra stap wordt hier gezet. En
    gwsw:hasConnection is een owl:SymmetricProperty zonder inverse, dus de
    tripel mag ook andersom geschreven zijn; beide richtingen tellen.

    Eén herstel, en niet meer (issue #60): wijst geen enkel doel naar een bekende
    orientatie, dan wordt per doel de staart `_put` gestript; is de stam een knoop
    met een Hulpstukorientatie, dan is dat de knoop en gaat het doel in `hersteld`.
    Ruimer zoeken is gokken op namen, en dat hoort niet in een kritiek pad.
    """
    if endpoint is None:
        return None
    doelen = [str(target) for target in _connections(graph, endpoint)]
    for doel in doelen:
        node_uri = orientation_to_node.get(doel)
        if node_uri is not None:
            return node_uri
    for doel in doelen:
        stam = doel.removesuffix(FANTOOM_STAART)
        if stam != doel and stam in hulpstukken:
            if hersteld is not None:
                hersteld.append(stam)
            return stam
    return None


# --------------------------------------------------------------------------------------
# De structurele herkenning naast de ontologische
# --------------------------------------------------------------------------------------


def _houders(graph: GraafIndex, orientaties: Iterable[RdfNode]) -> set[str]:
    """De objecten die deze orientaties dragen, als URI-teksten."""
    return {
        str(subject)
        for orientation in orientaties
        for subject in aspect_holders_of(graph, orientation)
    }


def _structural_diff(graph: GraafIndex, subclasses: dict[str, frozenset[str]]) -> dict[str, int]:
    """Vergelijkt de ontologische uitkomst met de structurele herkenning.

    Zonder ontologie herkent de lader knopen aan een puntgeometrie en verbindingen
    aan hun begin- en eindvertex. Die aanname is niet altijd waar: een knooppunt mag
    best geen geometrie hebben. Het verschil tussen beide manieren is een maat voor
    hoeveel de dataset op geometrie leunt, en hoort in het rapport te staan.

    De ontologische kant wordt hier zelf uit de graaf gehaald en niet aan de al
    ingelezen knopen ontleend. Anders zou dit instrument juist stil blijven in het
    geval waarvoor het bedoeld is: zonder klassenkennis *zijn* die knopen de
    structurele herkenning, en vergelijkt de telling zichzelf met zichzelf. Nu valt
    de ontologische kant via `_afsluiting` terug op de kale wortelklasse -- op een
    OroX-export die niets op wortelniveau typeert is dat nul, en dat is precies het
    cijfer dat de lezer moet zien.

    Neemt `subclasses` en niet de twee afsluitingen die `load_dataset` al berekende:
    `_bruikbare_afsluiting` levert exact `None` waar `_afsluiting` een singleton
    oplevert, dus die twee zouden hier alleen als omweg naar dezelfde uitkomst dienen.
    """
    ontologisch_knopen = _houders(
        graph, _orientations_of_class(graph, _afsluiting(subclasses, "Knooppunt"))
    )
    ontologisch_strengen = _houders(
        graph, _orientations_of_class(graph, _afsluiting(subclasses, "Verbinding"))
    )
    structureel_knopen = _houders(graph, _orientations_with(graph, KLASSE_PUNT))
    structureel_strengen = _houders(graph, _leiding_orientations(graph))

    verschillen: dict[str, int] = {}
    for rol, ontologisch, structureel in (
        ("knooppunten", ontologisch_knopen, structureel_knopen),
        ("strengen", ontologisch_strengen, structureel_strengen),
    ):
        zonder_geometrie = len(ontologisch - structureel)
        geen_knoop = len(structureel - ontologisch)
        if zonder_geometrie:
            verschillen[f"{rol}_zonder_geometrie"] = zonder_geometrie
        if geen_knoop:
            verschillen[f"{rol}_wel_geometrie_geen_rol"] = geen_knoop
    return verschillen
