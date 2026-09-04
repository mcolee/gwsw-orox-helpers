"""Inlezen van een GWSW-OroX-dataset (TTL) tot een toetsbaar domeinmodel.

Dit is het gezicht van de leeslaag: `load_dataset` leest bestand en ontologie in,
`GwswDataset` beantwoordt de vragen die de checks erover stellen en `markeer_vulwaarden`
zet een hoogtekenmerk binnen de vulwaardeband op "niet geregistreerd". Wat eronder ligt
is in zes modules verdeeld, elk met een eigen vraag:

- `domein` -- de waardeobjecten (`Node`, `Conduit`, `Aspect`, ...), zonder graaf;
- `bestand` -- van een TTL-bestand naar een gevulde `GraafIndex`: het parsen zelf, de
  codering en de GC eromheen (sinds issue #26 los van `inlezen`);
- `inlezen` -- alles wat die gevulde graaf bevraagt om de objecten te vullen, inclusief
  de twee schrijfrichtingen van hasPart en hasAspect;
- `klassen` -- de subklasse-afsluiting en de woordenboeken die daaruit volgen;
- `codering` -- UTF-8 met terugval, gedeeld met de schrijflaag;
- `netwerk` -- de wandeling langs hasPart omhoog en de tekenrichting van een streng,
  als vrije functies op `nodes` en een typepredicaat (sinds issue #27 los van deze
  module; de drie methoden hieronder zijn er doorgeefluiken naartoe).

Die verdeling is intern. **Het oppervlak blijft hier**: elke naam die nlriochecker uit
`gwsw_orox_helpers.dataset` importeert, komt hier ook naar buiten -- de klassen, de
IRI-constanten en de graafhulpen -- met dezelfde handtekening en hetzelfde gedrag
(Harde regel in `CLAUDE.md`; `tests/test_publieke_api.py` is de scheidsrechter).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from rdflib import RDFS, BNode, URIRef
from rdflib.term import Node as RdfNode

# Als module en niet als losse namen (issue #27): de drie doorgeefluiken hieronder heten
# net zo als de vrije functies waar ze naartoe wijzen, en `netwerk.klim_naar_knoop(...)`
# in een methode `klim_naar_knoop` laat geen twijfel over waar de aanroep heen gaat.
from gwsw_orox_helpers import netwerk
from gwsw_orox_helpers.bestand import _gc_uit, _parse
from gwsw_orox_helpers.bronnen import (
    GEBUNDELDE_VERSIES,
    gebundelde_ontologie,
    gebundelde_ontologie_voor,
)
from gwsw_orox_helpers.codering import DecodeFallback
from gwsw_orox_helpers.domein import (
    ISO_DATUM,
    JAARTAL,
    Aspect,
    Conduit,
    Inwinning,
    Koppelingsherstel,
    Node,
    Vulwaarde,
)
from gwsw_orox_helpers.errors import InhoudError
from gwsw_orox_helpers.geometry import (
    GeometryError,
    is_multipart_literal,
    parse_gml,
    parse_gml_z,
)
from gwsw_orox_helpers.graaf import GraafIndex, _uriref_snel
from gwsw_orox_helpers.inlezen import (
    # `RDF.type` is geen attribuut maar een `__getattr__` op rdflib's `DefinedNamespace`
    # en kost bijna een microseconde per keer; `inlezen` leest hem daarom een keer. Hier
    # geleend en niet nog eens neergezet: de `URIRef`-vorm van een GWSW-IRI woont in
    # `inlezen` (zie `docs/architectuur.md`), en twee exemplaren van dezelfde term zouden
    # bij een wijziging uit elkaar kunnen lopen.
    _RDF_TYPE,
    FANTOOM_STAART,
    HAS_ASPECT,
    HAS_CONNECTION,
    HAS_PART,
    HAS_REFERENCE,
    HAS_VALUE,
    IS_ASPECT_OF,
    IS_PART_OF,
    KLASSE_BEGINPUNT,
    KLASSE_BOB_BEGIN,
    KLASSE_BOB_EIND,
    KLASSE_DATUM_INWINNING,
    KLASSE_EINDPUNT,
    KLASSE_INWINNING,
    KLASSE_LIJN,
    KLASSE_MAAIVELDHOOGTE,
    KLASSE_MAAIVELDORIENTATIE,
    KLASSE_PUNT,
    KLASSE_PUTDEKSELNIVEAU,
    KLASSE_WIJZE_VAN_INWINNING,
    KLASSEN_BEGINPUNT,
    KLASSEN_EINDPUNT,
    Leestermen,
    _leestermen,
    _read_aspects,
    _read_conduits,
    _read_nodes,
    _structural_diff,
    aspect_holders_of,
    aspects_of,
    part_holders_of,
    parts_of,
)
from gwsw_orox_helpers.klassen import (
    WORTEL_HULPSTUK,
    WORTEL_HULPSTUKORIENTATIE,
    WORTEL_KNOOPPUNT,
    WORTEL_VERBINDING,
    WORTELS_VOOR_HERKENNING,
    _afsluiting,
    _bruikbare_afsluiting,
    _kenmerk_properties,
    _klassefuncties,
    _subclass_closure,
)
from gwsw_orox_helpers.namen import (
    GWSW,
    _short,
    _uri,
    basis_uit_iri,
    versie_uit_basis,
    versie_van_basis,
)
from gwsw_orox_helpers.voortgang import NUL_VOORTGANG, Voortgang

_logger = logging.getLogger(__name__)

# De lijst is het oppervlak, niet een keuze van deze module: alles wat ooit uit
# `gwsw_orox_helpers.dataset` te importeren was, staat erin -- ook de namen die na de
# hersnit in `geometry` (`parse_gml`, `parse_gml_z`, `is_multipart_literal`,
# `GeometryError`) of in `domein` (`ISO_DATUM`, `JAARTAL`) terechtkwamen. Ze zijn hier
# niets meer dan een doorgeefluik; wie ze uit hun eigen module haalt, krijgt hetzelfde
# object. Bij twijfel over "is dit publiek?" blijft de naam staan: hem weghalen breekt
# een afnemer stil, hem laten staan kost niets.
__all__ = [
    "FANTOOM_STAART",
    "GWSW",
    "HAS_ASPECT",
    "HAS_CONNECTION",
    "HAS_PART",
    "HAS_REFERENCE",
    "HAS_VALUE",
    "ISO_DATUM",
    "IS_ASPECT_OF",
    "IS_PART_OF",
    "JAARTAL",
    "KLASSEN_BEGINPUNT",
    "KLASSEN_EINDPUNT",
    "KLASSE_BEGINPUNT",
    "KLASSE_BOB_BEGIN",
    "KLASSE_BOB_EIND",
    "KLASSE_DATUM_INWINNING",
    "KLASSE_EINDPUNT",
    "KLASSE_INWINNING",
    "KLASSE_LIJN",
    "KLASSE_MAAIVELDHOOGTE",
    "KLASSE_MAAIVELDORIENTATIE",
    "KLASSE_PUNT",
    "KLASSE_PUTDEKSELNIVEAU",
    "KLASSE_WIJZE_VAN_INWINNING",
    "WORTELS_VOOR_HERKENNING",
    "WORTEL_HULPSTUK",
    "WORTEL_HULPSTUKORIENTATIE",
    "WORTEL_KNOOPPUNT",
    "WORTEL_VERBINDING",
    "Aspect",
    "Conduit",
    "DecodeFallback",
    "GeometryError",
    "GwswDataset",
    "GwswVersie",
    "Inwinning",
    "Koppelingsherstel",
    "Leestermen",
    "Node",
    "Vulwaarde",
    "aspect_holders_of",
    "aspects_of",
    "is_multipart_literal",
    "lees_ontologie",
    "load_dataset",
    "markeer_vulwaarden",
    "ontologiepaden",
    "parse_gml",
    "parse_gml_z",
    "part_holders_of",
    "parts_of",
]


@dataclass(frozen=True)
class GwswVersie:
    """De GWSW-versie waarop een dataset gelezen is (issue #39).

    Drie tekens, alle drie afgeleid en geen van alle een init-veld op `GwswDataset`:
    `basis` is de namespace (bv. `http://data.gwsw.nl/1.7/totaal/`), `versie` het
    versienummer daaruit (`"1.6"`, `"1.7"`; via `namen.versie_uit_basis`, hetzelfde
    patroon als `bronnen.GEBUNDELDE_VERSIES`) en `gedetecteerd` of een knoop of streng van de
    dataset een GWSW-type droeg waaruit die basis is afgeleid (`True`) dan wel geen enkele --
    de terugval op de gepinde 1.6-basis (`False`). Dit is wat een afnemer die geen internals
    mag aanraken (`nlriochecker`) in zijn rapportkop kan tonen.

    Let wel: de vlag is de leesweg van `gwsw_versie` (typen van knopen en strengen, zodat het
    cachepad de graafpickle niet laadt), niet die van `bestand._parse` (prefix en IRI-scan).
    Een dataset waarvan de bron wél een GWSW-basis droeg maar geen enkel object een
    GWSW-eigentype, meldt hier de terugval; de `_parse`-terugval (`logging.warning`) komt
    alleen voor bij een bron zonder enige GWSW-marker, en die laadt niet.
    """

    basis: str
    versie: str
    gedetecteerd: bool


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
    #
    # De wandeling zelf woont sinds issue #27 in `netwerk` en de memo *niet*: die hoort
    # bij de dataset waarop geklommen wordt, precies om de reden hierboven. Het
    # doorgeefluik geeft hem als argument mee; de vorm staat als `netwerk.Knoopmemo`
    # één keer opgeschreven.
    _resolved_nodes: netwerk.Knoopmemo = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    # Memo voor `types_of`, volgens hetzelfde patroon als `_resolved_nodes` hierboven;
    # waarom hij er is, staat bij die methode. Ook hier `init=False`, zodat een
    # `replace()`-afgeleide (`subset`, `markeer_vulwaarden`, het cachepad) met een lege
    # memo begint: die afgeleiden hebben andere `nodes`/`conduits`, dus een gedeelde memo
    # zou typen melden voor een knoop die er niet meer in staat -- en `cache._schrijf`
    # houdt het veld daardoor net zo goed buiten de pickle.
    # Hij groeit met het aantal *bevraagde* URI's en niet met `len(nodes) +
    # len(conduits)`: `graph_types_of` voert er ook URI's doorheen die alleen in de graaf
    # staan, en die missers worden net zo goed onthouden. Dat is bedoeld -- ze zijn de
    # hele run een misser -- maar het is de grens van wat hij aan geheugen kost.
    _types_memo: dict[str, frozenset[str]] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    # De gedetecteerde GWSW-versie van deze dataset (issue #39), gememoiseerd. Hij hoort bij
    # de gepinde `dataset.GWSW`-constante géén tweede *veld* op `GwswDataset` te worden: de
    # dataclass-handtekening en de veldenlijst staan in `tests/test_publieke_api.py` letterlijk
    # vast, en een init-veld erbij zou die breken. Daarom een `init=False`-memo, net als
    # `_types_memo`: hij telt niet mee in de handtekening en wordt niet gepickeld. De publieke
    # leesweg is de property `gwsw_versie`; `_basis` (voor `closure`/`is_connection_class`)
    # leest hem voor de basis. Bewust niet uit `self.graph.gwsw_basis`: op het luie cachepad
    # (`cache.LuieGraaf`) zou die attribuuttoegang de graafpickle van schijf trekken voor een
    # run die de graaf verder niet aanraakt. De basis komt daarom uit de typen van de knopen
    # en strengen, die al in het geheugen staan en dezelfde versie dragen als de graaf.
    _gwsw_versie_memo: list[GwswVersie] = field(
        default_factory=list, init=False, repr=False, compare=False
    )
    # De versie-juiste `URIRef`-termenset van deze dataset (issue #51), gememoiseerd volgens
    # precies hetzelfde patroon als `_gwsw_versie_memo` hierboven: een `init=False`-lijst die
    # niet in de handtekening telt en die `cache._schrijf` buiten de pickle houdt (het leidt de
    # niet-init-velden zelf af). De publieke leesweg is de property `termen`; hij hangt af van
    # `gwsw_versie.basis` en is dus, net als dat memo, uit de al gepicklede knopen en strengen
    # af te leiden zonder de graafpickle van schijf te trekken.
    _termen_memo: list[Leestermen] = field(
        default_factory=list, init=False, repr=False, compare=False
    )

    @property
    def gwsw_versie(self) -> GwswVersie:
        """De GWSW-versie waarop deze dataset gelezen is; de publieke leesweg (issue #39).

        Gememoiseerd, en afgeleid uit de typen van de knopen en strengen -- niet uit
        `self.graph.gwsw_basis`: op een cachetreffer is `self.graph` een `cache.LuieGraaf`
        en zou die attribuuttoegang de graafpickle laden. De knopen en strengen staan al in
        het geheugen (ze worden mee gepickeld, de graaf niet) en dragen dezelfde basis; de
        eerste GWSW-getypeerde daarvan levert haar (`gedetecteerd=True`). Draagt geen enkele
        knoop of streng een GWSW-type -- een dataset zonder enige GWSW-klasse -- dan is dat
        per definitie de terugval op de gepinde 1.6-basis (`gedetecteerd=False`). Het
        versienummer komt via `namen.versie_uit_basis`, zodat basis en cijfer dezelfde tekens
        spreken als `bronnen.GEBUNDELDE_VERSIES`.
        """
        if not self._gwsw_versie_memo:
            gevonden: str | None = None
            for objecten in (self.nodes.values(), self.conduits.values()):
                for obj in objecten:
                    treffer = next(
                        (b for typ in obj.types if (b := basis_uit_iri(typ)) is not None), None
                    )
                    if treffer is not None:
                        gevonden = treffer
                        break
                else:
                    continue
                break
            basis = gevonden if gevonden is not None else GWSW
            self._gwsw_versie_memo.append(
                GwswVersie(
                    basis=basis,
                    versie=versie_uit_basis(basis),
                    gedetecteerd=gevonden is not None,
                )
            )
        return self._gwsw_versie_memo[0]

    @property
    def _basis(self) -> str:
        """De GWSW-basis van deze dataset; interne leesweg voor `closure`/`is_connection_class`.

        De publieke leesweg is `gwsw_versie`; dit is `gwsw_versie.basis`. Zie die property
        voor waarom de basis uit de typen van de objecten komt en niet uit `self.graph`.
        """
        return self.gwsw_versie.basis

    @property
    def termen(self) -> Leestermen:
        """De versie-juiste `URIRef`-termenset van deze dataset; de publieke leesweg (issue #51).

        De gepinde module-constanten (`HAS_*`, `KLASSE_*`) spellen altijd 1.6 -- dat is het
        bevroren contract dat nlriochecker importeert. Op een 1.7-dataset vindt een bevraging
        met die constanten stil nul. `termen` levert dezelfde predicaten en klasse-IRI's voor de
        gedetecteerde basis (`gwsw_versie.basis`), zodat een afnemer de graaf versie-juist kan
        bevragen -- of, eenvoudiger, de drie str-methoden `uris_of_class`, `buren` en
        `kenmerken_met_waarde` gebruikt, die hier al doorheen lezen.

        Gememoiseerd volgens hetzelfde patroon als `gwsw_versie`, en om dezelfde reden lui:
        `_leestermen` is zelf `@functools.cache`, maar het memo houdt de property net als daar
        buiten de handtekening en de pickle. De basis komt uit `gwsw_versie` (de typen van de
        knopen en strengen), niet uit `self.graph`, zodat het luie cachepad de graafpickle niet
        laadt.
        """
        if not self._termen_memo:
            self._termen_memo.append(_leestermen(self.gwsw_versie.basis))
        return self._termen_memo[0]

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

        `isdisjoint` en niet `bool(... & ...)`: die doorsnede was een wegwerp-verzameling
        waar alleen de leegheid van gevraagd werd, en dit predicaat wordt ruim een miljoen
        keer per run gesteld (issue #12, doorgevoerd bij #23). Het antwoord is aan beide
        kanten hetzelfde -- ook met een lege typenverzameling en met een wortel die de
        hierarchie niet kent, waar `closure` op de wortel zelf blijft steken.
        """
        object_types = self.types_of(uri)
        return not object_types.isdisjoint(self.closure(root))

    def types_of(self, uri: str) -> frozenset[str]:
        """De typen van een object, inclusief die van zijn orientatie.

        Het GWSW legt de topologische rol bij de orientatie: klassen als
        Lozingspunt, Overnamepunt en UitlaatPunt zijn subklassen van Knooppunt en
        staan dus op de orientatie, niet op de put of het bouwwerk zelf. Wie op
        zulke klassen wil selecteren, moet ze hier terugvinden.

        Alleen knopen en strengen: een onderdeel dat via hasPart aan een put hangt
        levert hier een lege verzameling op. Daarvoor is `graph_types_of()`.

        Gememoiseerd per URI (`_types_memo`), om dezelfde reden als
        `resolve_network_node`: `is_a` stelt deze vraag ruim een miljoen keer per run en
        voor een knoop kostte dat elke keer een verse unie. Ook een lege uitkomst wordt
        onthouden -- een URI die geen knoop en geen streng is, is dat de hele run.
        De memo neemt aan dat `nodes` en `conduits` na het aanmaken van de dataset niet
        meer wijzigen; een `replace()`-afgeleide begint met een lege memo (zie het veld).
        """
        # `.get()` en niet `in`: dat scheelt op dit pad de tweede opzoeking, en een
        # opgeslagen waarde is nooit `None` -- ook de lege uitkomst is een frozenset.
        onthouden = self._types_memo.get(uri)
        if onthouden is not None:
            return onthouden
        if uri in self.nodes:
            node = self.nodes[uri]
            typen = node.types | node.orientation_types
        elif uri in self.conduits:
            typen = self.conduits[uri].types
        else:
            typen = frozenset()
        self._types_memo[uri] = typen
        return typen

    def graph_types_of(self, uri: str) -> frozenset[str]:
        """De typen van een willekeurige URI, ook als hij geen knoop of streng is.

        `types_of()` kent alleen het domeinmodel. Een constructieonderdeel als een
        overstortdrempel of een ledigingsvoorziening hangt via hasPart aan een put
        en draagt geen Knooppunt-orientatie; het wordt dus nooit een knoop en is met
        `types_of()` niet te herkennen. Hier komt het type rechtstreeks uit de graaf,
        met de typen uit het domeinmodel erbij, zodat een orientatieklasse als
        Lozingspunt vindbaar blijft.

        De twee termen komen kant-en-klaar: het subject via `graaf._uriref_snel` (de tekst
        is al een geldige graafsleutel, dus rdflib's validatieregex kost hier alleen tijd)
        en het predicaat als eenmalig gelezen `_RDF_TYPE`. Allebei zijn het dezelfde term
        als voorheen -- `tests/test_graaf.py` houdt het snelpad tegen `URIRef()` op elke
        IRI van de gebundelde ontologie -- dus het antwoord verandert niet (issue #23).
        """
        uit_graaf = {str(soort) for soort in self.graph.objects(_uriref_snel(uri), _RDF_TYPE)}
        return self.types_of(uri) | uit_graaf

    def graph_is_a(self, uri: str, root: str) -> bool:
        """Als `is_a`, maar ook voor onderdelen die alleen in de graaf staan.

        Dezelfde formulering als `is_a` en om dezelfde reden (issue #23): één predicaat
        hoort er in deze klasse niet in twee gedaanten te staan.
        """
        return not self.graph_types_of(uri).isdisjoint(self.closure(root))

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

        Doorgeefluik naar `netwerk.resolve_network_node`, met de memo van *deze*
        instantie erbij: `_resolved_nodes` blijft op de dataclass staan (zie het veld),
        zodat een `replace()`-afgeleide met een lege memo begint.
        """
        return netwerk.resolve_network_node(uri, roots, self.nodes, self.is_a, self._resolved_nodes)

    def klim_naar_knoop(
        self, uri: str | None, roots: list[str]
    ) -> tuple[str | None, frozenset[str]]:
        """De knoop boven dit object, plus de knopen die de wandeling erheen tegenkwam.

        Doorgeefluik naar `netwerk.klim_naar_knoop`, dat de wandeling zelf beschrijft:
        in de breedte, deterministisch bij gelijke diepte, en met de bezochte schakels
        als tweede uitkomst. Wat de wandeling nodig heeft gaat hier mee -- de knopen en
        het typepredicaat -- en verder niets.
        """
        return netwerk.klim_naar_knoop(uri, roots, self.nodes, self.is_a)

    def _schakels(self, bezocht: set[str]) -> frozenset[str]:
        """De bezochte URI's die een knoop zijn; de rest hoort niet in een analyseset.

        Doorgeefluik naar `netwerk._schakels`, en het enige van de vier dat binnen deze
        package door niemand meer aangeroepen wordt: `klim_naar_knoop` roept sinds issue
        #27 de vrije vorm aan. Hij blijft staan omdat #27 een *additieve* wijziging is en
        een methode weghalen een aftrekkende -- niet omdat een afnemer hem zou kunnen
        aanroepen, want een naam met een underscore is geen belofte (zie
        `docs/architectuur.md`) en nlriochecker roept hem nergens aan. Schrappen is
        daarmee een auteursbeslissing van één regel: de bewaker
        `test_de_netwerksnit_ligt_vast` slaat een methode die er niet meer is over.
        """
        return netwerk._schakels(bezocht, self.nodes)

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

        Doorgeefluik naar `netwerk.richting_van_geometrie`, met dezelfde memo als
        `resolve_network_node` hierboven: de twee koppelingen van de streng worden er
        net zo goed langs herleid en horen dezelfde antwoorden te krijgen.
        """
        return netwerk.richting_van_geometrie(
            conduit, roots, self.nodes, self.is_a, self._resolved_nodes
        )

    def closure(self, root: str) -> frozenset[str]:
        """De klasse zelf plus al haar subklassen, als volledige URI's."""
        return _afsluiting(self.subclasses, root, self._basis)

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
            _bruikbare_afsluiting(self.subclasses, wortel, self._basis) is not None
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
        return _uri(root, self._basis) in self.closure("Verbinding")

    def of_class(self, root: str) -> list[str]:
        """De URI's van alle knooppunten en strengen van dit type.

        Een klasse uit de Verbinding-afsluiting kan hier nooit een treffer geven
        (zie `is_connection_class`). De selectie zou stil nul opleveren, en die nul
        is niet te onderscheiden van een dataset zonder die objecten; op een
        geconfigureerde rol is dat daarom een harde fout.
        """
        if self.is_connection_class(root):
            raise InhoudError(
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

        De termen komen langs hetzelfde snelpad als bij `graph_types_of` (issue #23): de
        klassen uit een afsluiting zijn al geldige graafsleutels, dus rdflib's
        validatieregex kost hier alleen tijd. Dezelfde term, dus dezelfde treffers.
        """
        gevonden: list[RdfNode] = []
        for klasse in self.closure(root):
            gevonden.extend(self.graph.subjects(_RDF_TYPE, _uriref_snel(klasse)))
        return gevonden

    def uris_of_class(self, root: str) -> list[str]:
        """De URI's van alle objecten van dit type in de graaf, als tekst (issue #51).

        De versie-juiste, tekst-teruggevende tegenhanger van `subjects_of_class` (die
        `list[RdfNode]` levert): dezelfde afsluiting via `closure(root)`, die de klasse-IRI's al
        uit de gedetecteerde basis opbouwt, maar dan als `list[str]` zodat een afnemer de graaf,
        `URIRef` of de 1.6-`KLASSE_*`-constanten niet hoeft aan te raken. Ook onderdelen zonder
        eigen geometrie (een overstortdrempel) staan erbij, net als bij `subjects_of_class`.
        """
        return [str(subject) for subject in self.subjects_of_class(root)]

    def buren(self, uri: str) -> list[str]:
        """De hasConnection-buren van een object, in beide richtingen, als tekst (issue #51).

        `gwsw:hasConnection` is een `owl:SymmetricProperty` zonder inverse, dus de tripel mag
        ook andersom geschreven zijn; beide richtingen tellen -- dezelfde lezing als
        `inlezen._connections`, maar dan versie-juist (via `self.termen.has_connection`, niet de
        1.6-`HAS_CONNECTION`-constante) en als `list[str]`. De voorwaartse richting gaat voorop
        en elke buur komt hoogstens een keer terug.
        """
        has_connection = self.termen.has_connection
        term = _uriref_snel(uri)
        gezien: set[str] = set()
        buren: list[str] = []
        for buur in (
            *self.graph.objects(term, has_connection),
            *self.graph.subjects(has_connection, term),
        ):
            tekst = str(buur)
            if tekst not in gezien:
                gezien.add(tekst)
                buren.append(tekst)
        return buren

    def kenmerken_met_waarde(self, kenmerk: str) -> list[str]:
        """De hasValue-waarden van elk kenmerk van deze klasse in de graaf (issue #51).

        `kenmerk` is een korte klassenaam (`"Putdekselniveau"`, `"BobBeginpuntLeiding"`); de
        klasse-IRI en het `hasValue`-predicaat komen versie-juist uit de gedetecteerde basis
        (`self.termen`), niet uit een 1.6-constante die op een 1.7-graaf stil nul zou treffen.
        Terug komt de waarde als tekst, een per kenmerkknoop met een `hasValue`; een kenmerk
        zonder waarde (een orientatie, een verwijzing) valt weg.
        """
        klasse = _uriref_snel(_uri(kenmerk, self._basis))
        has_value = self.termen.has_value
        waarden: list[str] = []
        for aspect in self.graph.subjects(_RDF_TYPE, klasse):
            waarde = self.graph.value(aspect, has_value)
            if waarde is not None:
                waarden.append(str(waarde))
        return waarden

    def onderdelen(self, uri: str, wortel: str | None = None) -> list[str]:
        """De directe onderdelen van een object, optioneel beperkt tot een klasse.

        De neerwaartse tegenhanger van `klim_naar_knoop`: een stap langs hasPart
        omlaag, in beide schrijfrichtingen. Met een `wortel` blijven alleen de delen
        over die volgens `graph_is_a` van die klasse zijn -- ook delen die geen knoop
        of streng zijn, zoals een overstortdrempel. De volgorde is de graafvolgorde
        van `parts_of`, ongewijzigd; sorteren zou de uitvoer van de checks die hierop
        leunen veranderen.

        Voorbehoud: het wortelfilter loopt via `graph_types_of`, dat zijn subject nog
        altijd als URIRef opzoekt (sinds issue #23 met `graaf._uriref_snel`, dezelfde
        term) -- een BNode-onderdeel valt daar dus uit het gefilterde antwoord, terwijl
        de ongefilterde lijst (en `onderdeel_label`/`onderdeel_aspecten`, via
        `_subject_term`) hem wel ziet.
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

        Dezelfde lezing als `inlezen._read_aspects`, maar dan als methode: de checks
        hoeven de graaf er niet meer voor aan te raken.
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

        `geometry_errors` gaat sinds issue #36 met zijn object mee: de lezer sleutelt
        elke melding op de knoop- of streng-URI, dus dit filter houdt precies de fouten
        van de behouden objecten -- `subset([*nodes, *conduits])` geeft dezelfde
        `geometry_errors` als de bron. Eén uitzondering, uit voorzorg: een kapotte
        *wees-orientatie* zonder enkele houder is op de orientatie-URI gesleuteld, en die
        hoort bij geen enkel object; zo'n melding valt dus altijd uit elke subset.
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


def _gebundelde_paden_voor_basis(basis: str) -> list[Path]:
    """De gebundelde ontologie die bij een gedetecteerde dataset-basis hoort (issue #32).

    `load_dataset` roept dit aan wanneer de afnemer geen ontologie opgaf: dan kiest de lader
    de gebundelde ontologie op de versie die hij uit de dataset detecteerde, zodat een
    1.7-dataset de 1.7-hierarchie krijgt en niet stil op de 1.6-bundel terugvalt. Is de
    gedetecteerde versie niet gebundeld (een 1.8-bron, of een onherkenbare basis), dan valt
    hij terug op de 1.6-bundel -- met een melding, want de termenset volgt dan nog wel de
    gedetecteerde basis en de hierarchie kan niet meer matchen (`klassenhierarchie_bekend`
    meldt dat eerlijk als terugval op geometrie).
    """
    versie = versie_van_basis(basis)
    if versie in GEBUNDELDE_VERSIES:
        return [gebundelde_ontologie_voor(versie)]
    _logger.warning(
        "De dataset draagt GWSW-basis %r, maar daar is geen ontologie voor gebundeld "
        "(gebundeld zijn %s); de lezing valt terug op de 1.6-ontologie. De klassenhierarchie "
        "kan dan niet matchen en het lezen leunt op geometrie.",
        basis,
        ", ".join(GEBUNDELDE_VERSIES),
    )
    return [gebundelde_ontologie()]


def _stapel_ontologie(
    paden: Sequence[Path], fallback_encoding: str | None, voortgang: Voortgang
) -> GraafIndex:
    """Parseert de ontologiebestanden op volgorde in één index, met een stap per bestand.

    **Zonder eigen fase, en dat is de hele reden dat deze functie bestaat.** `load_dataset`
    en `lees_ontologie` moeten hetzelfde parseerpad delen -- één plek die weet dat
    meerdere ontologiebestanden in dezelfde `GraafIndex` stapelen -- maar ze melden hun
    voortgang anders: `load_dataset` telt de ontologiebestanden mee in zijn eigen fase
    "TTL laden" (`1 + len(paden)` stappen, met de dataset als eerste), `lees_ontologie`
    opent er zijn eigen fase "Ontologie laden" voor. Zou het delen op het niveau van de
    fase gebeuren, dan zou `load_dataset` er een tweede fase bij krijgen en dus een
    andere voortgang tonen dan voorheen -- en die is bevroren (`CLAUDE.md`, Harde
    regels). Wat hier staat is precies de lus die `load_dataset` altijd al had: per
    bestand een `bestand._parse` in de gedeelde index en daarna een `stap` met de
    bestandsnaam.

    Ook de GC blijft buiten deze functie: allebei de aanroepers zetten hem zelf stil
    (`bestand._gc_uit`), `load_dataset` om zijn hele leesblok en `lees_ontologie` om deze
    lus.
    """
    ontology = GraafIndex()
    for pad in paden:
        _parse(pad, fallback_encoding, index=ontology)
        voortgang.stap(label=pad.name)
    return ontology


def lees_ontologie(
    paden: list[Path] | None = None,
    terugvalcodering: str | None = None,
    *,
    voortgang: Voortgang = NUL_VOORTGANG,
) -> GraafIndex:
    """Leest de ontologiebestanden in tot de `GraafIndex` waarop de lezers werken.

    Dit is de index die `load_dataset` intern als `restrictiebron` opbouwt en daarna
    weggooit: `GwswDataset.graph` is de *dataset*graaf en `GwswDataset.ontologies` draagt
    alleen de paden. Wie de ontologische lezers van `gwsw_orox_helpers.ontologie` op een
    geladen dataset wil gebruiken -- `facetbereik`, `datatype_van_kenmerk`,
    `kenmerkbereik`, `verwachte_property`, `functie_van_klasse` -- haalt de bron ervoor
    hier op, langs precies dezelfde weg als de lader (issue #33, vervolg op #19).

    De padkeuze is die van `ontologiepaden` en dus dezelfde als bij `load_dataset`:
    `None` betekent de gebundelde GWSW-ontologie, een lege lijst is de expliciete keuze
    om zonder ontologie te lezen (en levert een lege index op), en een opgegeven lijst
    wordt in volgorde in één index gestapeld. De terugvalcodering betekent hetzelfde als
    daar; zie `codering.decodeer`. De parameters heten Nederlands (`paden`,
    `terugvalcodering`) zoals `CLAUDE.md` vraagt, en dus anders dan de bevroren
    `ontology_paths`/`fallback_encoding` van `load_dataset` -- een auteursbeslissing bij
    issue #33; `paden` en niet `ontologiepaden`, omdat dat de naam van de padkeuzefunctie
    hierboven is.

    De voortgang gaat per bestand, in een eigen fase "Ontologie laden" met één stap per
    bestand. Dat is een andere fase dan de "TTL laden" van `load_dataset` -- die telt de
    ontologie bij de dataset in één fase, en dat blijft zo.

    **Ook met een lege lijst is er precies één fase**, dan met totaal nul en zonder
    stappen. Dat is een keuze en geen restje: een aanroeper die de fasen meetelt (een
    balk per fase, een teller in een log) hoort de fase-indeling niet van de *inhoud* van
    zijn argument te zien afhangen -- "soms een fase, soms geen" is het lastigere
    contract om tegenaan te programmeren. `Voortgang.start_fase` neemt `totaal` als
    `int | None` en nul is daar een geldige waarde.

    Hetzelfde neveneffect als bij `load_dataset`, en om dezelfde reden: tijdens het lezen
    ligt de cyclische garbage collector van het hele proces stil en komt hij daarna terug,
    ook na een fout (zie `bestand._gc_uit`).
    """
    ontologie_paden = ontologiepaden(paden)
    voortgang.start_fase("Ontologie laden", len(ontologie_paden))
    with _gc_uit():
        try:
            return _stapel_ontologie(ontologie_paden, terugvalcodering, voortgang)
        finally:
            voortgang.einde_fase()


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

    Eén neveneffect om te weten: tijdens de lezing ligt de cyclische garbage collector van
    het hele proces stil en komt hij daarna terug, ook na een fout -- de referentietelling
    blijft aan, dus wat vrijkomt gaat nog altijd meteen weg (zie `bestand._gc_uit`).
    """
    dataset_path = Path(dataset_path)
    expliciet = ontology_paths is not None
    ontologie_paden = ontologiepaden(ontology_paths)
    voortgang.start_fase("TTL laden", 1 + len(ontologie_paden))
    # Om het hele leesblok en niet alleen om het vullen van de index (`bestand._parse`):
    # ook de objectopbouw hieronder maakt miljoenen dicts, tuples en dataclasses aan, en
    # bij elke paar duizend daarvan zou de GC opnieuw door de al gevulde index lopen. Er
    # ontstaat per constructie geen kringetje -- de index, de termen en de waardeobjecten
    # wijzen alleen naar beneden. De binnenste `_gc_uit` in `bestand._parse` blijft staan
    # en is neveneffectvrij: die kijkt naar `gc.isenabled()` en laat deze stand met rust.
    with _gc_uit():
        try:
            graph, fallback = _parse(dataset_path, fallback_encoding)
            voortgang.stap(label=dataset_path.name)

            # Zonder opgegeven ontologie kiest de lader de gebundelde ontologie op de versie
            # die hij zojuist uit de dataset detecteerde (issue #32): de dataset wordt dus
            # éérst geparst, dan de bijpassende ontologie gestapeld. Een expliciet opgegeven
            # `ontology_paths` blijft leidend. Het aantal paden -- en dus de fasetelling
            # hierboven -- verandert niet: `ontologiepaden(None)` en de versiekeuze leveren
            # allebei één gebundeld bestand.
            if not expliciet:
                ontologie_paden = _gebundelde_paden_voor_basis(graph.gwsw_basis)

            # Dezelfde lus als voorheen, nu gedeeld met `lees_ontologie`; hij meldt zijn
            # stappen in de fase die hierboven al loopt en opent er geen eigen (zie
            # `_stapel_ontologie`).
            ontology = _stapel_ontologie(ontologie_paden, fallback_encoding, voortgang)
        finally:
            voortgang.einde_fase()

        # De basis van de dataset (voor het lezen van de graaf) en die van de restrictiebron
        # (voor het lezen van de ontologie) kunnen verschillen wanneer de afnemer expliciet
        # een ontologie van een andere versie opgeeft. De closures die de dataset bevragen
        # gebruiken de datasetbasis; de afgeleiden uit de restrictiebron haar eigen basis.
        data_basis = graph.gwsw_basis
        restrictiebron = ontology if len(ontology) else graph
        onto_basis = restrictiebron.gwsw_basis
        subclasses = _subclass_closure(restrictiebron)
        kenmerk_property = _kenmerk_properties(restrictiebron, subclasses, onto_basis)
        functie_per_klasse = _klassefuncties(restrictiebron, subclasses, onto_basis)
        geometry_errors: dict[str, str] = {}
        # Dezelfde twee vragen die `GwswDataset.klassenhierarchie_bekend` stelt, met
        # dezelfde functie: `None` hier betekent terugval op geometrie, en dat is precies
        # wat het voorbehoud in de uitvoer zegt.
        knooppunt = _bruikbare_afsluiting(subclasses, WORTEL_KNOOPPUNT, data_basis)
        verbinding = _bruikbare_afsluiting(subclasses, WORTEL_VERBINDING, data_basis)
        # De afsluiting, niet de kale klasse: zie `inlezen._deksel_kenmerk`. Zonder
        # klassenkennis blijft het bij Putdeksel zelf, net als bij elke andere `closure()`.
        deksel = _afsluiting(subclasses, "Putdeksel", data_basis)
        hulpstuk = _afsluiting(subclasses, WORTEL_HULPSTUKORIENTATIE, data_basis)
        nodes = _read_nodes(graph, geometry_errors, knooppunt, deksel)
        conduits, herstel = _read_conduits(graph, nodes, geometry_errors, verbinding, hulpstuk)

    if not nodes and not conduits:
        raise InhoudError(
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
    # Eén waarschuwing wanneer de dataset niet de leidende 1.6-versie is (issue #51): de
    # gepinde module-constanten (`HAS_*`, `KLASSE_*`) spellen 1.6 en treffen op deze graaf
    # stil nul. Wie versie-juist wil bevragen, gebruikt `GwswDataset.termen` of de
    # str-methoden. Precies hier en nergens anders: een cachetreffer loopt niet langs
    # `load_dataset` (zie `cache.laad_met_cache`), dus die waarschuwt niet nog eens.
    if dataset.gwsw_versie.versie != "1.6":
        _logger.warning(
            "De dataset is GWSW-versie %s; de gepinde module-constanten (HAS_*, KLASSE_*) "
            "spellen 1.6 en gelden niet voor deze dataset -- gebruik de versie-juiste "
            "`GwswDataset.termen` of de str-methoden (uris_of_class, buren, "
            "kenmerken_met_waarde).",
            dataset.gwsw_versie.versie,
        )
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
