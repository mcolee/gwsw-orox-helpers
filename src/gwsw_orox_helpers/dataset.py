"""Inlezen van een GWSW-OroX-dataset (TTL) tot een toetsbaar domeinmodel."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path

import pyoxigraph
from rdflib import RDF, RDFS, BNode, URIRef
from rdflib.term import Node as RdfNode
from shapely.geometry import LineString, Point

from gwsw_orox_helpers.bronnen import gebundelde_ontologie
from gwsw_orox_helpers.errors import DatasetError
from gwsw_orox_helpers.geometry import (
    GeometryError,
    is_multipart_literal,
    parse_gml,
    parse_gml_z,
)
from gwsw_orox_helpers.graaf import GraafIndex
from gwsw_orox_helpers.voortgang import NUL_VOORTGANG, Voortgang

GWSW = "http://data.gwsw.nl/1.6/totaal/"

HAS_ASPECT = URIRef(f"{GWSW}hasAspect")
HAS_PART = URIRef(f"{GWSW}hasPart")
# Het GWSW declareert `isPartOf owl:inverseOf hasPart` en `isAspectOf owl:inverseOf
# hasAspect`. Een conforme export mag dus de inverse schrijven; wie alleen de
# voorwaartse richting leest, krijgt van zo'n export een leeg domeinmodel zonder een
# enkele melding. Lees daarom beide, net als bij hasConnection.
IS_PART_OF = URIRef(f"{GWSW}isPartOf")
IS_ASPECT_OF = URIRef(f"{GWSW}isAspectOf")
HAS_CONNECTION = URIRef(f"{GWSW}hasConnection")
HAS_VALUE = URIRef(f"{GWSW}hasValue")
HAS_REFERENCE = URIRef(f"{GWSW}hasReference")

KLASSE_INWINNING = URIRef(f"{GWSW}Inwinning")
KLASSE_WIJZE_VAN_INWINNING = URIRef(f"{GWSW}WijzeVanInwinning")
KLASSE_DATUM_INWINNING = URIRef(f"{GWSW}DatumInwinning")
KLASSE_MAAIVELDORIENTATIE = URIRef(f"{GWSW}Maaiveldorientatie")
KLASSE_MAAIVELDHOOGTE = URIRef(f"{GWSW}Maaiveldhoogte")
KLASSE_PUTDEKSELNIVEAU = URIRef(f"{GWSW}Putdekselniveau")

KLASSE_PUNT = URIRef(f"{GWSW}Punt")
KLASSE_LIJN = URIRef(f"{GWSW}Lijn")
# Het GWSW kent drie soorten verbindingen, elk met een eigen begin- en eindvertex.
# Alle zes zijn subklassen van gwsw:Vertex.
KLASSEN_BEGINPUNT = tuple(
    URIRef(f"{GWSW}{naam}")
    for naam in ("BeginpuntLeiding", "BeginpuntOnderdeel", "BeginpuntAfvoerrelatie")
)
KLASSEN_EINDPUNT = tuple(
    URIRef(f"{GWSW}{naam}")
    for naam in ("EindpuntLeiding", "EindpuntOnderdeel", "EindpuntAfvoerrelatie")
)
KLASSE_BEGINPUNT = KLASSEN_BEGINPUNT[0]
KLASSE_EINDPUNT = KLASSEN_EINDPUNT[0]
KLASSE_BOB_BEGIN = URIRef(f"{GWSW}BobBeginpuntLeiding")
KLASSE_BOB_EIND = URIRef(f"{GWSW}BobEindpuntLeiding")

# De twee wortels waarmee de lader knopen en strengen uit de graaf haalt. Blijft de
# afsluiting van een van beide op de wortel zelf steken, dan valt dat lezen terug op
# geometrie; `GwswDataset.klassenhierarchie_bekend` is precies die vraag.
WORTEL_KNOOPPUNT = "Knooppunt"
WORTEL_VERBINDING = "Verbinding"
WORTELS_VOOR_HERKENNING = (WORTEL_KNOOPPUNT, WORTEL_VERBINDING)

WORTEL_HULPSTUK = "Hulpstuk"
WORTEL_HULPSTUKORIENTATIE = "Hulpstukorientatie"
# De staart die de BrutIS-export achter de naam van een hulpstuk plakt in het
# hasConnection-doel van een leidingeinde, waar de orientatie zelf anders heet.
FANTOOM_STAART = "_put"


@dataclass(frozen=True)
class Inwinning:
    """De inwinningsmetagegevens die aan een kenmerk kunnen hangen."""

    wijze: str | None = None
    datum: date | None = None

    def __bool__(self) -> bool:
        """Waar zodra er iets ingevuld is."""
        return self.wijze is not None or self.datum is not None


@dataclass(frozen=True)
class Aspect:
    """Een kenmerk van een object: een waarde of een verwijzing naar een GWSW-begrip.

    Het GWSW hangt kenmerken als `gwsw:hasAspect [ rdf:type gwsw:MateriaalLeiding ;
    gwsw:hasReference gwsw:Beton ]` aan een object. Waardekenmerken gebruiken
    `hasValue`, domeinlijstkenmerken `hasReference`.
    """

    kind: str
    value: str | None = None
    reference: str | None = None
    inwinning: Inwinning | None = None

    @property
    def number(self) -> float | None:
        """De waarde als getal, of None als die er niet is of niet numeriek is."""
        if self.value is None:
            return None
        try:
            return float(self.value)
        except ValueError:
            return None

    @property
    def date(self) -> date | None:
        """De waarde als datum (ISO of jaartal), of None."""
        return _as_date(self.value)


@dataclass(frozen=True)
class Vulwaarde:
    """Een hoogtekenmerk dat een vulwaarde droeg en bij het lezen als ontbrekend geldt."""

    kind: str
    value: float


class _MetAspecten:
    """Toegang tot de kenmerken van een object, per GWSW-klassenaam."""

    aspects: tuple[Aspect, ...]

    def aspect(self, kind: str) -> Aspect | None:
        """Het eerste kenmerk van deze soort, of None."""
        for aspect in self.aspects:
            if aspect.kind == kind:
                return aspect
        return None

    def number(self, kind: str) -> float | None:
        """De numerieke waarde van dit kenmerk, of None."""
        aspect = self.aspect(kind)
        return aspect.number if aspect is not None else None

    def reference(self, kind: str) -> str | None:
        """De domeinlijstverwijzing van dit kenmerk (korte naam), of None."""
        aspect = self.aspect(kind)
        return aspect.reference if aspect is not None else None

    def date(self, kind: str) -> date | None:
        """De datumwaarde van dit kenmerk, of None."""
        aspect = self.aspect(kind)
        return aspect.date if aspect is not None else None


@dataclass(frozen=True)
class Node(_MetAspecten):
    """Een knooppunt in het netwerk: een put, gemaal of lozingspunt."""

    uri: str
    label: str
    types: frozenset[str]
    orientation: str | None
    orientation_types: frozenset[str]
    point: Point | None
    z: float | None
    parents: tuple[str, ...]
    aspects: tuple[Aspect, ...] = ()
    maaiveld_aspect: Aspect | None = None
    maaiveld_inwinning: Inwinning | None = None
    deksel_aspect: Aspect | None = None
    deksel_inwinning: Inwinning | None = None
    multipart: bool = False
    vulwaarden: tuple[Vulwaarde, ...] = ()

    @property
    def maaiveld(self) -> float | None:
        """De maaiveldhoogte bij dit knooppunt, in m NAP."""
        return self.maaiveld_aspect.number if self.maaiveld_aspect is not None else None

    @property
    def dekselniveau(self) -> float | None:
        """Het putdekselniveau, in m NAP."""
        return self.deksel_aspect.number if self.deksel_aspect is not None else None

    @property
    def bovenkant(self) -> float | None:
        """Het bovenkantniveau: het dekselniveau, of anders het maaiveld.

        Het register spreekt bij HGT-004, HGT-012 en HGT-018 over de dekselhoogte.
        Ontbreekt die, dan is de maaiveldhoogte de dichtstbijzijnde benadering; welke
        van de twee gebruikt is, hoort in de bevinding te staan.
        """
        return self.dekselniveau if self.dekselniveau is not None else self.maaiveld

    @property
    def hoogte_m(self) -> float | None:
        """De hoogte van de put in meters; het GWSW noteert die in millimeters."""
        waarde = self.number("HoogtePut")
        return waarde / 1000 if waarde is not None else None

    @property
    def bodem(self) -> float | None:
        """Het putbodemniveau, afgeleid uit bovenkant minus puthoogte.

        Het GWSW kent geen kenmerk `Putbodemniveau`; de bodem volgt uit het
        dekselniveau en `HoogtePut`. Ontbreekt een van beide, dan is de bodem
        onbekend en mag er niet op getoetst worden.
        """
        boven, hoogte = self.bovenkant, self.hoogte_m
        if boven is None or hoogte is None:
            return None
        return boven - hoogte


@dataclass(frozen=True)
class Conduit(_MetAspecten):
    """Een streng: een leiding met een begin- en eindpunt."""

    uri: str
    label: str
    types: frozenset[str]
    line: LineString | None
    start_node: str | None
    end_node: str | None
    bob_start_aspect: Aspect | None = None
    bob_end_aspect: Aspect | None = None
    aspects: tuple[Aspect, ...] = ()
    multipart: bool = False
    z_values: tuple[float | None, ...] = ()
    vulwaarden: tuple[Vulwaarde, ...] = ()

    @property
    def z_start(self) -> float | None:
        """De z-waarde van het eerste lijnpunt, als de geometrie er een heeft."""
        return self.z_values[0] if self.z_values else None

    @property
    def z_end(self) -> float | None:
        """De z-waarde van het laatste lijnpunt, als de geometrie er een heeft."""
        return self.z_values[-1] if self.z_values else None

    @property
    def bob_start(self) -> float | None:
        """De binnenonderkant buis aan het beginpunt, in m NAP."""
        return self.bob_start_aspect.number if self.bob_start_aspect is not None else None

    @property
    def bob_end(self) -> float | None:
        """De binnenonderkant buis aan het eindpunt, in m NAP."""
        return self.bob_end_aspect.number if self.bob_end_aspect is not None else None

    @property
    def bob_verval(self) -> float | None:
        """Het verval van de bodem over de streng, in meters.

        Positief als de bodem van het administratieve beginpunt naar het eindpunt
        daalt. Ontbreekt een van beide BOB's, dan valt er niets te zeggen.
        """
        if self.bob_start is None or self.bob_end is None:
            return None
        return self.bob_start - self.bob_end

    @property
    def breedte_mm(self) -> float | None:
        """De breedte (bij een rond profiel: de diameter) in millimeters."""
        return self.number("BreedteLeiding")

    @property
    def hoogte_mm(self) -> float | None:
        """De hoogte van het profiel in millimeters."""
        return self.number("HoogteLeiding")

    @property
    def lengte_m(self) -> float | None:
        """De administratieve lengte in meters."""
        return self.number("LengteLeiding")

    @property
    def materiaal(self) -> str | None:
        """Het leidingmateriaal als korte GWSW-naam."""
        return self.reference("MateriaalLeiding")

    @property
    def vorm(self) -> str | None:
        """De profielvorm als korte GWSW-naam."""
        return self.reference("VormLeiding")

    @property
    def begindatum_jaar(self) -> int | None:
        """Het jaartal uit de begindatum (GWSW-kenmerk `Begindatum`)."""
        datum = self.date("Begindatum")
        return datum.year if datum is not None else None


@dataclass(frozen=True)
class DecodeFallback:
    """Vastlegging dat een bestand niet als UTF-8 gelezen kon worden."""

    path: Path
    encoding: str
    byte_count: int
    samples: list[str]


@dataclass(frozen=True)
class Koppelingsherstel:
    """Hoeveel `hasConnection`-doelen de lader op naamstam naar een hulpstuk herleid heeft.

    De BrutIS-export van De Wolden en Hoogeveen koppelt élk leidingeinde dat op een
    hulpstuk uitkomt aan `<hulpstuk>_put`, een URI zonder type of aspect, terwijl de
    orientatie `<hulpstuk>_put<n>` heet. Zonder herstel ziet de engine bij alle 1054
    T-stukken nul leidingen en hangen 3024 strengeinden aan niets. Het herstel is
    bewust smal (alleen een onbekend doel, alleen als de stam een hulpstukknoop is) en
    wordt hier geteld, zodat het rapport de aanlevering blijft aanwijzen in plaats van
    het gebrek stilletjes op te ruimen (issue #60).
    """

    koppelingen: int = 0
    hulpstukken: int = 0


@dataclass(frozen=True)
class GwswDataset:
    """De ingelezen dataset met de knooppunten, strengen en de klassenhierarchie."""

    source: Path
    graph: GraafIndex
    nodes: dict[str, Node]
    conduits: dict[str, Conduit]
    subclasses: dict[str, frozenset[str]]
    geometry_errors: dict[str, str] = field(default_factory=dict)
    decode_fallback: DecodeFallback | None = None
    ontologies: tuple[Path, ...] = ()
    structural_diff: dict[str, int] = field(default_factory=dict)
    # Per kenmerktype de property die de ontologie voor zijn waarde voorschrijft
    # (`hasValue` of `hasReference`), afgeleid uit de `owl:onProperty`-restricties.
    # Dit is de ontologische kennis die ATTR-014 nodig heeft en die anders na het
    # berekenen van `subclasses` verloren gaat; het is een klein afgeleid woordenboek
    # zoals `subclasses`, niet de hele ontologiegraaf. Leeg zonder klassenkennis.
    kenmerk_property: dict[str, str] = field(default_factory=dict)
    # Per hulpstukklasse (volledige URI) de functiewaarde uit de `gwsw:functie`-restrictie
    # van de ontologie, overgeerfd naar subklassen zonder eigen restrictie. TOP-022 en
    # TOP-023 lezen er het verwachte aantal leidingen uit (issue #60). Net als
    # `kenmerk_property` een klein afgeleid woordenboek; leeg zonder klassenkennis.
    functie_per_klasse: dict[str, str] = field(default_factory=dict)
    # Het herstel van de fantoomkoppeling naar hulpstukken (issue #60); nul zonder
    # fantomen. Het rapport meldt het als datasetsignaal `SIG-hulpstukkoppeling`.
    koppelingsherstel: Koppelingsherstel = Koppelingsherstel()
    # Memo voor `resolve_network_node`: de klim door hasPart is deterministisch en
    # wordt in een run ruim een miljoen keer met dezelfde argumenten gevraagd.
    # Bewust `init=False`: zo krijgt elke instantie -- ook een `replace()`-afgeleide
    # zoals `subset()` -- een eigen, lege memo. Een uitgedunde dataset kan anders
    # resolven dan de volle export (de wandeling ziet minder knopen), en een via
    # `replace()` gedeelde dict zou antwoorden tussen de twee laten lekken.
    # `cache._schrijf` slaat dit veld bij het picklen over.
    _resolved_nodes: dict[tuple[str, tuple[str, ...]], str | None] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def is_a(self, uri: str, root: str) -> bool:
        """Geeft aan of dit domeinobject van het type `root` of een subklasse is.

        **Let op: dit is de smalle van de twee, en hij faalt stil.** `types_of()` kent
        alleen knopen en strengen, dus voor een onderdeel dat via hasPart aan een put
        hangt -- een overstortdrempel, een ledigingsvoorziening -- geeft deze methode
        `False` en niet een fout. Wie hem daar per ongeluk gebruikt krijgt een dode
        checktak die er groen uitziet; issue #34 vond er zo twee. `graph_is_a()` is de
        strikte versterking (`graph_types_of ⊇ types_of`), dus de verkeerde keuze die
        kant op is hooguit ruim -- en dat is precies waarom de kortste en algemeenst
        klinkende naam de gevaarlijke is.

        Twee redenen dat hij blijft bestaan. Hij drukt "is een gemodelleerde knoop of
        streng van dit type" uit, en dat is wat `klim_naar_knoop` en `uitvoer/melding.py`
        vragen: de eerste moet stoppen zodra hij een knoop uit het domeinmodel te pakken
        heeft, de tweede weegt de prioriteit van een melding op het knoop- of
        strengobject waaraan zij hangt. En hij spaart de
        graafopvraging van `graph_types_of()` uit, die op elke wandeling over De Wolden en Hoogeveen
        meetelt.
        """
        object_types = self.types_of(uri)
        return bool(object_types & self.closure(root))

    def types_of(self, uri: str) -> frozenset[str]:
        """De typen van een object, inclusief die van zijn orientatie.

        Het GWSW legt de topologische rol bij de orientatie: klassen als
        Lozingspunt, Overnamepunt en UitlaatPunt zijn subklassen van Knooppunt en
        staan dus op de orientatie, niet op de put of het bouwwerk zelf. Wie op
        zulke klassen wil selecteren, moet ze hier terugvinden.

        Alleen knopen en strengen: een onderdeel dat via hasPart aan een put hangt
        levert hier een lege verzameling op. Daarvoor is `graph_types_of()`.
        """
        if uri in self.nodes:
            node = self.nodes[uri]
            return node.types | node.orientation_types
        if uri in self.conduits:
            return self.conduits[uri].types
        return frozenset()

    def graph_types_of(self, uri: str) -> frozenset[str]:
        """De typen van een willekeurige URI, ook als hij geen knoop of streng is.

        `types_of()` kent alleen het domeinmodel. Een constructieonderdeel als een
        overstortdrempel of een ledigingsvoorziening hangt via hasPart aan een put
        en draagt geen Knooppunt-orientatie; het wordt dus nooit een knoop en is met
        `types_of()` niet te herkennen. Hier komt het type rechtstreeks uit de graaf,
        met de typen uit het domeinmodel erbij, zodat een orientatieklasse als
        Lozingspunt vindbaar blijft.
        """
        uit_graaf = {str(soort) for soort in self.graph.objects(URIRef(uri), RDF.type)}
        return self.types_of(uri) | uit_graaf

    def graph_is_a(self, uri: str, root: str) -> bool:
        """Als `is_a`, maar ook voor onderdelen die alleen in de graaf staan."""
        return bool(self.graph_types_of(uri) & self.closure(root))

    def beheerobjecttype(self, uri: str) -> str:
        """De korte naam van het beheerobjecttype van een object.

        `types_of()` voegt de typen van de orientatie bij die van het object, en
        terecht: Lozingspunt en UitlaatPunt staan volgens het GWSW op de orientatie.
        Voor een soortnaam is dat aspecttype juist het verkeerde antwoord -- een
        knoop heet Uitlaatconstructie, niet Bouwwerkorientatie. De typen van het
        object zelf gaan daarom voor; alleen als die ontbreken valt de naam terug
        op het aspect.

        Draagt een object meer dan een type, dan wint het meest specifieke: een type
        waarvan een ander type uit dezelfde verzameling een subklasse is, is de
        algemenere van de twee en valt af. Die rangorde komt uit de
        subsumptierelatie van de ontologie en nergens anders vandaan. Blijven er
        onvergelijkbare typen over -- het GWSW is een meervoudige hierarchie, dus
        dat kan -- dan wint alfabetisch de eerste; willekeurig, maar deterministisch.
        """
        node = self.nodes.get(uri)
        types = node.types if node is not None and node.types else self.types_of(uri)
        namen = sorted(_short(naam) for naam in self._meest_specifiek(types))
        return namen[0] if namen else ""

    def _meest_specifiek(self, types: frozenset[str]) -> frozenset[str]:
        """De typen waarvan geen ander type uit dezelfde verzameling een subklasse is."""
        if len(types) < 2:
            return types
        algemener = {
            soort
            for soort in types
            # `closure` is zelf-insluitend; het type zelf mag zichzelf niet wegstrepen.
            for ander in types & self.subclasses.get(soort, frozenset())
            if ander != soort
        }
        # `or types`: bij een cyclus in de ontologie (A subklasse van B en andersom)
        # zou alles wegvallen, en een object zonder soortnaam is de slechtste uitkomst.
        return (types - algemener) or types

    def resolve_network_node(self, uri: str | None, roots: list[str]) -> str | None:
        """Herleidt een gekoppeld object naar het knooppunt waar het onderdeel van is.

        Een streng koppelt niet altijd aan een put: in de GWSW-praktijk wijst de
        koppeling ook naar een compartiment of een hulpstuk. Voor de netwerkanalyse
        telt de put eromheen, dus wordt via hasPart omhooggelopen tot een object van
        een van de opgegeven wortelklassen.

        Gememoiseerd per (uri, wortels): de wandeling is deterministisch en de
        checks stellen dezelfde vraag ruim een miljoen keer per run. De wortels
        horen in de sleutel -- in de praktijk zijn ze constant binnen een run, maar
        een memo die dat stilzwijgend aanneemt zou bij een afwijkende aanroep het
        verkeerde antwoord teruggeven.
        """
        if uri is None:
            return None
        sleutel = (uri, tuple(roots))
        if sleutel not in self._resolved_nodes:
            self._resolved_nodes[sleutel] = self.klim_naar_knoop(uri, roots)[0]
        return self._resolved_nodes[sleutel]

    def klim_naar_knoop(
        self, uri: str | None, roots: list[str]
    ) -> tuple[str | None, frozenset[str]]:
        """De knoop boven dit object, plus de knopen die de wandeling erheen tegenkwam.

        In de breedte en niet langs een enkel pad: een onderdeel kan meer dan een
        houder hebben (`Node.parents`), en de eerste die rdflib oplevert hoeft niet
        de houder te zijn die op een knoop uitkomt. Een enkelpadswandeling zou dan
        leeg teruggeven terwijl er wel degelijk een put boven hangt, en welke houder
        "de eerste" is hangt af van de schrijfvolgorde van de export.
        `nulbevinding._Joiner` loopt om diezelfde reden al in de breedte omhoog.

        Bij gelijke diepte wint de kleinste URI: willekeurig maar deterministisch,
        en dat is wat telt -- twee runs op dezelfde bestanden moeten dezelfde
        meldingen opleveren.

        De tweede uitkomst is de verzameling bezochte schakels die zelf in `nodes`
        staan; `afbakening` heeft die nodig om ze in de analyseset te houden, anders
        loopt dezelfde wandeling op de uitgedunde dataset dood. Bewust ruimer dan het
        gevonden pad: het zijn alle bezochte knopen, dus ook broers op de laag waar de
        knoop gevonden werd en takken die doodliepen. Met enkelvoudige houders vallen
        de twee samen; met meervoudige houders is dit een superset. Dat is de veilige
        kant -- de lezer gebruikt hem om de wandeling herhaalbaar te houden op een
        uitgedunde dataset, en een schakel te veel bewaren kost hoogstens ruimte,
        terwijl er een te weinig de wandeling laat doodlopen.
        """
        if uri is None:
            return None, frozenset()
        gezien = {uri}
        laag = [uri]
        while laag:
            for huidig in laag:
                if any(self.is_a(huidig, root) for root in roots):
                    return huidig, self._schakels(gezien)
            hoger: set[str] = set()
            for huidig in laag:
                node = self.nodes.get(huidig)
                if node is not None:
                    hoger.update(node.parents)
            volgende = sorted(hoger - gezien)
            gezien.update(volgende)
            laag = volgende
        return None, self._schakels(gezien)

    def _schakels(self, bezocht: set[str]) -> frozenset[str]:
        """De bezochte URI's die een knoop zijn; de rest hoort niet in een analyseset."""
        return frozenset(uri for uri in bezocht if uri in self.nodes)

    def richting_van_geometrie(
        self, conduit: Conduit, roots: list[str]
    ) -> tuple[bool, Node, Node] | None:
        """Vergelijkt de tekenrichting van de lijn met de van-naar-richting.

        Geeft (omgekeerd, beginput, eindput) terug, waarbij `omgekeerd` zegt of de
        lijn bij de administratieve eindput begint. None als er niets te vergelijken
        valt: geen geometrie, geen echte lijngeometrie, geen twee verschillende
        putten, of putten zonder punt. TOP-020 en de kaartlaag met richtingspijlen
        lezen allebei deze methode, zodat het kaartbeeld en de bevinding niet uit
        elkaar kunnen lopen.
        """
        if conduit.line is None or conduit.line.is_empty:
            return None
        if not isinstance(conduit.line, LineString):
            # Een GML-literaal in de leidinggeometrie hoeft geen lijn te zijn (zie
            # TOP-016 en `checks.meetkunde.coords_of`); zonder lijn is er geen
            # tekenrichting om te vergelijken.
            return None
        begin = self.nodes.get(self.resolve_network_node(conduit.start_node, roots) or "")
        eind = self.nodes.get(self.resolve_network_node(conduit.end_node, roots) or "")
        if begin is None or eind is None or begin.point is None or eind.point is None:
            return None
        if begin.uri == eind.uri:
            return None
        punten = list(conduit.line.coords)
        eerste, laatste = Point(punten[0][:2]), Point(punten[-1][:2])
        juist = eerste.distance(begin.point) + laatste.distance(eind.point)
        omgekeerd = eerste.distance(eind.point) + laatste.distance(begin.point)
        return omgekeerd < juist, begin, eind

    def closure(self, root: str) -> frozenset[str]:
        """De klasse zelf plus al haar subklassen, als volledige URI's."""
        return _afsluiting(self.subclasses, root)

    @property
    def klassenhierarchie_bekend(self) -> bool:
        """Of de lader knopen en strengen aan hun GWSW-type heeft kunnen herkennen.

        Precies dezelfde vraag die `load_dataset` stelt, en met dezelfde functie
        gesteld: `_bruikbare_afsluiting` levert `None` waar de afsluiting van een
        wortel op die wortel zelf blijft steken, en dan valt het lezen van die kant
        terug op geometrie -- een knooppunt zonder punt valt dan buiten de selectie en
        een object met een punt dat geen knooppunt is valt erbinnen. Wat er dan uit de
        checks komt draagt geen oordeel, en de uitvoer moet dat kunnen zeggen.

        `bool(self.subclasses)` was hier eerder het antwoord, en dat is een ander en
        ruimer predicaat: een enkele subklasserelatie ergens in de export -- ook een
        die met knopen en strengen niets te maken heeft -- zette het op `True` terwijl
        de lader wel degelijk op geometrie terugviel. Een deel van de TTL-fixtures in
        deze repo zit in die tussentoestand: hierarchie voor `Put` en `Leiding`, geen
        voor `Knooppunt` en `Verbinding`.

        Niet af te lezen aan `ontologies`: een handgeschreven fixture die haar eigen
        subklassen declareert heeft geen ontologiebestand nodig en toetst wel degelijk.
        De vraag is wat de graaf over klassen weet, niet waar die kennis vandaan komt.
        """
        return all(
            _bruikbare_afsluiting(self.subclasses, wortel) is not None
            for wortel in WORTELS_VOOR_HERKENNING
        )

    def is_connection_class(self, root: str) -> bool:
        """Geeft aan of deze klasse in de Verbinding-afsluiting valt.

        Zulke klassen staan op de orientatie van een streng, en `Conduit` draagt
        haar orientatietypen niet zoals `Node` dat wel doet; een selectie erop kan
        dus nooit een treffer geven. `of_class()` weigert er een, want daar is de
        klassenaam configuratie. Wie een klassenaam uit een *meting* krijgt --
        `analysis.bepaal_typeringspoort` leest ze uit de CfkTypes_typ-regels van de
        SHACL-nulmeting -- vraagt het hier vooraf: een meetuitkomst hoort de run
        niet te laten vallen, maar als onbeoordeelbaar in het rapport te komen.

        Zonder ontologie is de afsluiting alleen `Verbinding` zelf, dus dan wordt
        alleen die naam herkend.
        """
        return _uri(root) in self.closure("Verbinding")

    def of_class(self, root: str) -> list[str]:
        """De URI's van alle knooppunten en strengen van dit type.

        Een klasse uit de Verbinding-afsluiting kan hier nooit een treffer geven
        (zie `is_connection_class`). De selectie zou stil nul opleveren, en die nul
        is niet te onderscheiden van een dataset zonder die objecten; op een
        geconfigureerde rol is dat daarom een harde fout.
        """
        if self.is_connection_class(root):
            raise DatasetError(
                f"{root} is een verbindingsklasse en kan als rol nooit een object opleveren: "
                f"die klassen staan op de orientatie van een streng, en het domeinmodel "
                f"draagt de orientatietypen van een streng niet. Configureer de klasse van "
                f"het object zelf, bijvoorbeeld een subklasse van Leiding."
            )
        gesloten = self.closure(root)
        return [uri for uri in (*self.nodes, *self.conduits) if self.types_of(uri) & gesloten]

    def subjects_of_class(self, root: str) -> list[RdfNode]:
        """Alle objecten van dit type in de graaf, ook zonder eigen geometrie.

        Onderdelen als een overstortdrempel hebben geen punt- of lijngeometrie en
        komen daarom niet in `nodes` of `conduits` voor; die zijn hier wel te vinden.
        """
        gevonden: list[RdfNode] = []
        for klasse in self.closure(root):
            gevonden.extend(self.graph.subjects(RDF.type, URIRef(klasse)))
        return gevonden

    def onderdelen(self, uri: str, wortel: str | None = None) -> list[str]:
        """De directe onderdelen van een object, optioneel beperkt tot een klasse.

        De neerwaartse tegenhanger van `klim_naar_knoop`: een stap langs hasPart
        omlaag, in beide schrijfrichtingen. Met een `wortel` blijven alleen de delen
        over die volgens `graph_is_a` van die klasse zijn -- ook delen die geen knoop
        of streng zijn, zoals een overstortdrempel. De volgorde is de graafvolgorde
        van `parts_of`, ongewijzigd; sorteren zou de uitvoer van de checks die hierop
        leunen veranderen.

        Voorbehoud: het wortelfilter loopt via `graph_types_of`, dat zijn subject nog
        met een vaste `URIRef(uri)` opzoekt -- een BNode-onderdeel valt daar dus uit
        het gefilterde antwoord, terwijl de ongefilterde lijst (en `onderdeel_label`/
        `onderdeel_aspecten`, via `_subject_term`) hem wel ziet.
        """
        delen = [str(deel) for deel in parts_of(self.graph, self._subject_term(uri))]
        if wortel is None:
            return delen
        return [deel for deel in delen if self.graph_is_a(deel, wortel)]

    def onderdeel_label(self, uri: str) -> str | None:
        """Het rdfs:label van een willekeurig subject in de graaf, of None.

        Ook voor onderdelen die geen `Node` of `Conduit` zijn en dus geen eigen
        labelveld in het domeinmodel hebben.
        """
        waarde = self.graph.value(self._subject_term(uri), RDFS.label)
        return str(waarde) if waarde is not None else None

    def onderdeel_aspecten(self, uri: str) -> list[Aspect]:
        """De kenmerken die via hasAspect aan een willekeurig subject hangen.

        Dezelfde lezing als `_read_aspects`, maar dan als methode: de checks hoeven
        de graaf er niet meer voor aan te raken.
        """
        return list(_read_aspects(self.graph, self._subject_term(uri)))

    def _subject_term(self, uri: str) -> RdfNode:
        """De graafterm achter deze URI-tekst: de URIRef, of anders de BNode.

        De `onderdeel_*`-lezers krijgen hun subject als tekst, meestal via
        `str(subject)` op een term uit `subjects_of_class`. Voor een BNode-subject
        verloor de vaste `URIRef(uri)`-omweg dan het label en de kenmerken (bevinding
        uit de review van issue #26): `str(BNode("b1"))` is "b1", en `URIRef("b1")`
        staat nergens in de graaf. Hier wint de URIRef als die als subject voorkomt;
        anders telt de gelijknamige BNode. Een tekst die geen van beide is, blijft de
        URIRef -- hetzelfde lege antwoord als voorheen.
        """
        term: RdfNode = URIRef(uri)
        if self.graph.heeft_subject(term):
            return term
        bnode = BNode(uri)
        if self.graph.heeft_subject(bnode):
            return bnode
        return term

    def stelsel_leden(self, uri: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """De streng- en knoop-URI's die dit stelsel via `hasPart` draagt.

        Twee gesorteerde tuples: (strengen, knopen). Voor de stelsellaag (#25) en de
        nulmetingjoin, die allebei hetzelfde onderscheid nodig hebben en niet uit elkaar
        mogen lopen. Een stelsel met knopen erin is een gemeentebrede `_geb_0`-bucket
        (#17): die verzamelt de putten van een heel type naast verspreide strengen en is
        geen lokaal stelsel -- de stelsellaag slaat hem daarom over.
        """
        strengen: list[str] = []
        knopen: list[str] = []
        for lid in parts_of(self.graph, URIRef(uri)):
            fragment = str(lid)
            if fragment in self.conduits:
                strengen.append(fragment)
            elif fragment in self.nodes:
                knopen.append(fragment)
        return tuple(sorted(strengen)), tuple(sorted(knopen))

    def subset(self, uris: Iterable[str]) -> GwswDataset:
        """Dezelfde dataset met alleen deze knopen en verbindingen.

        De graafindex gaat ongewijzigd mee: hij is de bron waaruit de checks hun
        onderdelen opzoeken, en hem meesnijden zou stilzwijgend gegevens weglaten.
        Alleen `subjects_of_class()` loopt daardoor nog over de volledige export;
        dat zijn de drempels in NET-007 en RVZ, en dat staat in het rapport.
        """
        behouden = frozenset(uris)
        return replace(
            self,
            nodes={uri: node for uri, node in self.nodes.items() if uri in behouden},
            conduits={uri: kant for uri, kant in self.conduits.items() if uri in behouden},
            geometry_errors={
                uri: fout for uri, fout in self.geometry_errors.items() if uri in behouden
            },
        )


def _uri(naam: str) -> str:
    """Maakt van een korte klassenaam een volledige GWSW-URI."""
    return naam if naam.startswith("http") else f"{GWSW}{naam}"


def _short(uri: str) -> str:
    """De korte klassenaam achter de laatste scheidingstekens van een URI."""
    return uri.rsplit("/", 1)[-1].rsplit("#", 1)[-1]


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


ISO_DATUM = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
JAARTAL = re.compile(r"^(\d{4})$")


def _as_date(waarde: str | None) -> date | None:
    """Leest een GWSW-datumwaarde; een kaal jaartal telt als 1 januari."""
    if waarde is None:
        return None
    match = ISO_DATUM.match(waarde)
    if match is not None:
        try:
            return date(int(match[1]), int(match[2]), int(match[3]))
        except ValueError:
            return None
    jaar = JAARTAL.match(waarde.strip())
    if jaar is not None:
        try:
            return date(int(jaar[1]), 1, 1)
        except ValueError:
            return None
    return None


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
        for soort in graph.objects(aspect, RDF.type):
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
        if (aspect, RDF.type, KLASSE_INWINNING) not in graph:
            continue
        wijze: str | None = None
        datum: date | None = None
        for deel in aspects_of(graph, aspect):
            if (deel, RDF.type, KLASSE_WIJZE_VAN_INWINNING) in graph:
                referentie = graph.value(deel, HAS_REFERENCE)
                wijze = _short(str(referentie)) if referentie is not None else None
            elif (deel, RDF.type, KLASSE_DATUM_INWINNING) in graph:
                waarde = graph.value(deel, HAS_VALUE)
                datum = _as_date(str(waarde)) if waarde is not None else None
        gevonden = Inwinning(wijze=wijze, datum=datum)
        if gevonden:
            return gevonden
    return None


def _aspect_van_klasse(graph: GraafIndex, subject: RdfNode, klasse: URIRef) -> Aspect | None:
    """Het kenmerk van deze klasse dat direct aan het object hangt."""
    for aspect in aspects_of(graph, subject):
        if (aspect, RDF.type, klasse) not in graph:
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
        if (buur, RDF.type, KLASSE_MAAIVELDORIENTATIE) not in graph:
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
    graph: GraafIndex, subject: RdfNode, deksel_klassen: frozenset[str]
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
        if not any((deel, RDF.type, URIRef(klasse)) in graph for klasse in deksel_klassen):
            continue
        for orientatie in aspects_of(graph, deel):
            aspect = _aspect_van_klasse(graph, orientatie, KLASSE_PUTDEKSELNIVEAU)
            if aspect is not None:
                return aspect, _herkomst(graph, orientatie, aspect)
        aspect = _aspect_van_klasse(graph, deel, KLASSE_PUTDEKSELNIVEAU)
        if aspect is not None:
            return aspect, _herkomst(graph, deel, aspect)
    return None, None


def ontologiepaden(ontology_paths: list[Path] | None) -> list[Path]:
    """De ontologiebestanden waarmee gelezen wordt, met `None` als de gebundelde.

    Twee verschillende dingen die makkelijk voor elkaar doorgaan: *niets opgegeven*
    (`None`) betekent de meegeleverde GWSW-ontologie, en een *lege lijst* is de
    expliciete keuze om zonder ontologie te lezen. Dat onderscheid staat hier en
    nergens anders, zodat `load_dataset` en `cache` het niet elk anders kunnen
    invullen.

    De gebundelde ontologie is de standaard omdat de andere kant geen stille keuze
    mag zijn: zonder klassenhierarchie herkent de lader knopen en strengen niet aan
    hun GWSW-type en valt hij terug op geometrie -- zie
    `GwswDataset.klassenhierarchie_bekend`.
    """
    if ontology_paths is None:
        return [gebundelde_ontologie()]
    return [Path(pad) for pad in ontology_paths]


def load_dataset(
    dataset_path: Path,
    ontology_paths: list[Path] | None = None,
    fallback_encoding: str | None = None,
    *,
    voortgang: Voortgang = NUL_VOORTGANG,
) -> GwswDataset:
    """Leest de OroX-dataset en de ontologie(en) en bouwt het domeinmodel op.

    Zonder `ontology_paths` wordt de gebundelde GWSW-ontologie gelezen; een lege lijst
    betekent expliciet geen ontologie. Zie `ontologiepaden`.

    De voortgang gaat per bestand. rdflib geeft geen tussenstand binnen een bestand,
    en juist het parsen van de dataset is de lange stap; er wordt daarom geen
    percentage getoond dat er niet is.

    Turtle hoort volgens de spec UTF-8 te zijn en zonder `fallback_encoding` wordt niets
    anders geaccepteerd: een bestand dat er niet aan voldoet levert een `DatasetError`.
    Sommige exports (BrutIS) schrijven een handvol bytes in een MS-DOS-codering; de
    afnemer die dat weet, geeft de codering op (`"cp850"` is de gangbare Nederlandse
    variant). Welke dat is, is een keuze van de afnemer en niet van deze package.
    """
    dataset_path = Path(dataset_path)
    ontologie_paden = ontologiepaden(ontology_paths)
    voortgang.start_fase("TTL laden", 1 + len(ontologie_paden))
    try:
        graph, fallback = _parse(dataset_path, fallback_encoding)
        voortgang.stap(label=dataset_path.name)

        ontology = GraafIndex()
        for pad in ontologie_paden:
            _parse(pad, fallback_encoding, index=ontology)
            voortgang.stap(label=pad.name)
    finally:
        voortgang.einde_fase()

    restrictiebron = ontology if len(ontology) else graph
    subclasses = _subclass_closure(restrictiebron)
    kenmerk_property = _kenmerk_properties(restrictiebron, subclasses)
    functie_per_klasse = _klassefuncties(restrictiebron, subclasses)
    geometry_errors: dict[str, str] = {}
    # Dezelfde twee vragen die `GwswDataset.klassenhierarchie_bekend` stelt, met
    # dezelfde functie: `None` hier betekent terugval op geometrie, en dat is precies
    # wat het voorbehoud in de uitvoer zegt.
    knooppunt = _bruikbare_afsluiting(subclasses, WORTEL_KNOOPPUNT)
    verbinding = _bruikbare_afsluiting(subclasses, WORTEL_VERBINDING)
    # De afsluiting, niet de kale klasse: zie `_deksel_kenmerk`. Zonder klassenkennis
    # blijft het bij Putdeksel zelf, net als bij elke andere `closure()`.
    deksel = _afsluiting(subclasses, "Putdeksel")
    hulpstuk = _afsluiting(subclasses, WORTEL_HULPSTUKORIENTATIE)
    nodes = _read_nodes(graph, geometry_errors, knooppunt, deksel)
    conduits, herstel = _read_conduits(graph, nodes, geometry_errors, verbinding, hulpstuk)

    if not nodes and not conduits:
        raise DatasetError(
            f"{dataset_path}: geen knooppunten of strengen aangetroffen. Is dit een "
            f"GWSW-OroX-dataset?"
        )

    dataset = GwswDataset(
        source=dataset_path,
        graph=graph,
        nodes=nodes,
        conduits=conduits,
        subclasses=subclasses,
        geometry_errors=geometry_errors,
        decode_fallback=fallback,
        ontologies=tuple(ontologie_paden),
        kenmerk_property=kenmerk_property,
        functie_per_klasse=functie_per_klasse,
        koppelingsherstel=herstel,
    )
    # Altijd, en juist ook zonder klassenkennis: dan laat het verschil zien dat de
    # ontologische route nul objecten oplevert en de hele lezing op geometrie rust.
    dataset.structural_diff.update(_structural_diff(graph, subclasses))
    return dataset


def markeer_vulwaarden(
    dataset: GwswDataset, kenmerken: Sequence[str], band_m: float
) -> GwswDataset:
    """Leest een hoogtekenmerk binnen de vulwaardeband als niet geregistreerd.

    Sommige exports schrijven 0,000 waar het kenmerk leeg hoort te zijn (De Wolden en Hoogeveen:
    een kwart van de BOB's). De checks zouden die nul als meting lezen en er duizenden
    hoogtefouten van maken. Deze stap zet zo'n kenmerk op `None` en onthoudt op het
    object dat en welke waarde er stond, zodat ATTR-013 het een keer kan melden en de
    hoogtechecks het object overslaan en dat in hun toelichting zeggen.

    De stap staat los van het laden: de cache bewaart de ruwe parse, de band is
    projectconfiguratie. De meegegeven dataset blijft onaangeraakt; met een lege
    kenmerkenlijst is dit de identiteit.
    """
    if not kenmerken:
        return dataset
    gekozen = frozenset(kenmerken)

    def vulwaarde(aspect: Aspect | None) -> Vulwaarde | None:
        """De vulwaarde die dit kenmerk draagt, of None als het een meting is."""
        if aspect is None or aspect.kind not in gekozen:
            return None
        getal = aspect.number
        if getal is None or abs(getal) > band_m:
            return None
        return Vulwaarde(aspect.kind, getal)

    nodes: dict[str, Node] = {}
    for uri, node in dataset.nodes.items():
        maaiveld, deksel = vulwaarde(node.maaiveld_aspect), vulwaarde(node.deksel_aspect)
        gevonden = tuple(vul for vul in (maaiveld, deksel) if vul is not None)
        nodes[uri] = (
            replace(
                node,
                maaiveld_aspect=None if maaiveld is not None else node.maaiveld_aspect,
                deksel_aspect=None if deksel is not None else node.deksel_aspect,
                vulwaarden=gevonden,
            )
            if gevonden
            else node
        )

    conduits: dict[str, Conduit] = {}
    for uri, conduit in dataset.conduits.items():
        begin, eind = vulwaarde(conduit.bob_start_aspect), vulwaarde(conduit.bob_end_aspect)
        gevonden = tuple(vul for vul in (begin, eind) if vul is not None)
        conduits[uri] = (
            replace(
                conduit,
                bob_start_aspect=None if begin is not None else conduit.bob_start_aspect,
                bob_end_aspect=None if eind is not None else conduit.bob_end_aspect,
                vulwaarden=gevonden,
            )
            if gevonden
            else conduit
        )

    return replace(dataset, nodes=nodes, conduits=conduits)


@contextmanager
def _quiet_rdflib():
    """Dempt rdflib-waarschuwingen over onjuiste literalen tijdens het parsen.

    De meegeleverde GWSW-ontologie bevat een xsd:date "20210830" zonder streepjes;
    rdflib logt daar een volledige traceback bij. Dat is geen fout in onze invoer en
    hoort niet in de CLI-uitvoer thuis.
    """
    logger = logging.getLogger("rdflib.term")
    oud = logger.level
    logger.setLevel(logging.ERROR)
    try:
        yield
    finally:
        logger.setLevel(oud)


def _afsluiting(subclasses: dict[str, frozenset[str]], wortel: str) -> frozenset[str]:
    """De subklasse-afsluiting van een wortel; zonder klassenkennis de wortel zelf.

    De enige plek waar die terugval opgeschreven staat. Stond hij er twee keer, dan
    zou een van beide bij een wijziging achterblijven zonder dat het opvalt: een
    afsluiting die stilzwijgend krimpt levert geen fout op maar een lege selectie.
    """
    return subclasses.get(_uri(wortel), frozenset({_uri(wortel)}))


def _bruikbare_afsluiting(
    subclasses: dict[str, frozenset[str]], wortel: str
) -> frozenset[str] | None:
    """De subklasse-afsluiting van een wortel, of None als de ontologie ontbreekt."""
    afsluiting = _afsluiting(subclasses, wortel)
    return afsluiting if len(afsluiting) > 1 else None


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


def _parse(
    path: Path, fallback_encoding: str | None, index: GraafIndex | None = None
) -> tuple[GraafIndex, DecodeFallback | None]:
    """Leest een enkel TTL-bestand in, desnoods via een terugvalcodering.

    Het parsen zelf gaat via pyoxigraph's Rust-parser (ordegrootten sneller dan rdflib's
    pure-Python `notation3`); de triples vullen in stream-volgorde een `GraafIndex` met
    rdflib-termen, zodat de checks en de rest van de lader hun vergelijkingen houden.
    pyoxigraph verlangt UTF-8-bytes, dus de al gedecodeerde tekst wordt opnieuw als
    UTF-8 gecodeerd -- niet de ruwe bytes, die immers cp850 kunnen zijn. Een meegegeven
    `index` wordt aangevuld; zo stapelen meerdere ontologiebestanden in een index.
    """
    try:
        rauw = path.read_bytes()
    except OSError as error:
        raise DatasetError(f"{path}: bestand kan niet gelezen worden ({error}).") from error

    tekst, fallback = _decode(path, rauw, fallback_encoding)

    index = index if index is not None else GraafIndex()
    try:
        quads = pyoxigraph.parse(tekst.encode("utf-8"), format=pyoxigraph.RdfFormat.TURTLE)
        # rdflib waarschuwt bij het bouwen van een literaal met een ongeldige lexicale
        # vorm (de meegeleverde ontologie draagt een xsd:date "20210830" zonder streepjes);
        # net als bij de oude parse hoort die traceback niet in de CLI-uitvoer thuis.
        with _quiet_rdflib():
            index.vul_uit(quads)
    except Exception as error:  # pyoxigraph gooit uiteenlopende parsefouten
        raise DatasetError(f"{path}: geen geldige Turtle ({error}).") from error
    return index, fallback


def _decode(
    path: Path, rauw: bytes, fallback_encoding: str | None
) -> tuple[str, DecodeFallback | None]:
    """Decodeert de inhoud als UTF-8, of anders met de terugvalcodering.

    Turtle hoort UTF-8 te zijn, maar niet elke exporttool houdt zich daaraan. Wijkt
    een bestand af, dan wordt dat vastgelegd en gerapporteerd; stilzwijgend
    vervangen van tekens zou de inhoud ongemerkt veranderen. Zonder terugvalcodering
    (`None`) is er niets om op terug te vallen en is de afwijking een fout: welke
    codering een afwijkend bestand dan wel draagt, weet alleen de afnemer.
    """
    try:
        return rauw.decode("utf-8"), None
    except UnicodeDecodeError as error:
        # De uitzondering bestaat niet meer buiten dit blok; leg de feiten nu vast.
        eerste_byte, eerste_positie = rauw[error.start], error.start

    if fallback_encoding is None:
        raise DatasetError(
            f"{path}: geen geldige UTF-8 (byte {eerste_byte:#04x} op positie "
            f"{eerste_positie}) en er is geen terugvalcodering opgegeven."
        )

    try:
        tekst = rauw.decode(fallback_encoding)
    except (UnicodeDecodeError, LookupError) as fout:
        raise DatasetError(
            f"{path}: geen geldige UTF-8 (byte {eerste_byte:#04x} op positie "
            f"{eerste_positie}) en ook niet te lezen als {fallback_encoding} ({fout})."
        ) from fout

    # De niet-ASCII-bytes tellen zonder een Python-lus over alle 112 MB: `translate`
    # verwijdert in C alle bytes 0x00-0x7F, en wat overblijft zijn er precies de bytes
    # groter dan 0x7F.
    byte_count = len(rauw.translate(None, bytes(range(0x80))))
    return tekst, DecodeFallback(
        path=path,
        encoding=fallback_encoding,
        byte_count=byte_count,
        samples=_fallback_samples(rauw, fallback_encoding),
    )


def _fallback_samples(rauw: bytes, encoding: str, limiet: int = 5) -> list[str]:
    """De regels waarin de niet-ASCII-bytes staan, ter controle door de gebruiker."""
    voorbeelden: list[str] = []
    for index, byte in enumerate(rauw):
        if byte <= 0x7F:
            continue
        start = rauw.rfind(b"\n", 0, index) + 1
        eind = rauw.find(b"\n", index)
        regel = rauw[start : eind if eind != -1 else len(rauw)]
        tekst = regel.decode(encoding, "replace").strip()
        if tekst not in voorbeelden:
            voorbeelden.append(tekst)
        if len(voorbeelden) >= limiet:
            break
    return voorbeelden


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


def _kenmerk_properties(graph: GraafIndex, subclasses: dict[str, frozenset[str]]) -> dict[str, str]:
    """Per kenmerktype de property die de ontologie voor zijn waarde voorschrijft.

    Loopt over de subklassen van `Kenmerk` en houdt alleen de types die een
    `hasValue`- of `hasReference`-restrictie dragen. Leest uit dezelfde graaf als
    `subclasses` (de ontologie, of bij een fixture de dataset zelf), zodat het met
    `--geen-ontologie` en inline-hierarchieen meebeweegt. Zonder klassenkennis blijft
    de afsluiting op `Kenmerk` zelf steken en levert dit een leeg woordenboek.
    """
    from gwsw_orox_helpers.ontologie import verwachte_property

    gevonden: dict[str, str] = {}
    for uri in _afsluiting(subclasses, "Kenmerk"):
        property_ = verwachte_property(graph, URIRef(uri))
        if property_ is not None:
            gevonden[_short(uri)] = property_
    return gevonden


def _klassefuncties(graph: GraafIndex, subclasses: dict[str, frozenset[str]]) -> dict[str, str]:
    """Per hulpstukklasse de functiewaarde uit de ontologie, overgeerfd naar subklassen.

    Loopt over de afsluiting van `Hulpstuk`; een klasse met een eigen restrictie wint
    van wat zij van een bovenklasse zou erven. Sleutel is de volledige URI, zodat een
    knoop er met zijn `types` direct in kan kijken.
    """
    from gwsw_orox_helpers.ontologie import functie_van_klasse

    eigen: dict[str, str] = {}
    for uri in _afsluiting(subclasses, WORTEL_HULPSTUK):
        functie = functie_van_klasse(graph, URIRef(uri))
        if functie is not None:
            eigen[uri] = functie
    gevonden = dict(eigen)
    for uri, functie in sorted(eigen.items()):
        for sub in _afsluiting(subclasses, _short(uri)):
            gevonden.setdefault(sub, functie)
    return gevonden


def _label(graph: GraafIndex, subject: RdfNode) -> str:
    """Het rdfs:label van een object, of een lege tekst."""
    waarde = graph.value(subject, RDFS.label)
    return str(waarde) if waarde is not None else ""


def _types(graph: GraafIndex, subject: RdfNode) -> frozenset[str]:
    """Alle rdf:type-waarden van een object."""
    return frozenset(str(waarde) for waarde in graph.objects(subject, RDF.type))


def _geometry(graph: GraafIndex, orientation: RdfNode, klasse: URIRef, errors: dict[str, str]):
    """Zoekt de geometrie van een orientatie en geeft die met haar z-waarden terug."""
    for aspect in aspects_of(graph, orientation):
        if (aspect, RDF.type, klasse) not in graph:
            continue
        literal = graph.value(aspect, HAS_VALUE)
        if literal is None:
            continue
        try:
            return parse_gml(str(literal)), parse_gml_z(str(literal))
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
            deksel, deksel_inwinning = _deksel_kenmerk(graph, subject, deksel_klassen)
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
        for orientation in graph.subjects(RDF.type, URIRef(klasse)):
            if orientation not in gezien:
                gezien.add(orientation)
                yield orientation


def _orientations_with(graph: GraafIndex, klasse: URIRef):
    """De orientaties die via hasAspect een geometrie van dit type dragen."""
    gezien = set()
    for aspect in graph.subjects(RDF.type, klasse):
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
        if (aspect, RDF.type, klasse) in graph and graph.value(aspect, HAS_VALUE) is not None
    ]
    if len(literalen) > 1:
        return True
    return any(is_multipart_literal(literal) for literal in literalen)


def _leiding_orientations(graph: GraafIndex):
    """De orientaties die een begin- of eindpunt van een leiding bevatten."""
    gezien = set()
    for klasse in (*KLASSEN_BEGINPUNT, *KLASSEN_EINDPUNT):
        for endpoint in graph.subjects(RDF.type, klasse):
            for orientation in part_holders_of(graph, endpoint):
                if orientation not in gezien:
                    gezien.add(orientation)
                    yield orientation


def _endpoint(
    graph: GraafIndex, orientation: RdfNode, klassen: tuple[URIRef, ...]
) -> RdfNode | None:
    """Het begin- of eindpunt van een verbinding, van welke soort dan ook."""
    for part in parts_of(graph, orientation):
        if any((part, RDF.type, klasse) in graph for klasse in klassen):
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


def _connections(graph: GraafIndex, subject: RdfNode):
    """De hasConnection-buren van een object, in beide schrijfrichtingen."""
    yield from graph.objects(subject, HAS_CONNECTION)
    yield from graph.subjects(HAS_CONNECTION, subject)


def _bob(graph: GraafIndex, endpoint: RdfNode | None, klasse: URIRef) -> Aspect | None:
    """Het BOB-kenmerk dat aan een strengeindpunt hangt, met zijn inwinning."""
    if endpoint is None:
        return None
    return _aspect_van_klasse(graph, endpoint, klasse)
