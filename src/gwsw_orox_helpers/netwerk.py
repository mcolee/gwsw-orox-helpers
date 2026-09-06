"""De netwerkvragen over een ingelezen dataset: wat hangt erboven, welke kant op?

Twee vragen die de checks aan de topologie stellen en die niets van een `GwswDataset`
nodig hebben behalve de knopen en het typepredicaat:

- **wat is de knoop boven dit object?** Een streng koppelt in de GWSW-praktijk niet
  altijd aan een put maar aan een compartiment of een hulpstuk; voor de netwerkanalyse
  telt de put eromheen. `klim_naar_knoop` loopt daarvoor langs `hasPart` omhoog en
  `resolve_network_node` is de gememoiseerde vorm ervan.
- **loopt de lijn dezelfde kant op als de administratie?** `richting_van_geometrie`
  vergelijkt de tekenrichting van de leidinggeometrie met de van-naar-richting.

**Vrije functies, geen dataset** (issue #27). Ze nemen wat ze nodig hebben als
parameter: de knopen (`nodes`), het typepredicaat (`is_a`) en -- waar er gememoiseerd
wordt -- de memo zelf. Daarmee is de wandeling te toetsen op een handgebouwd
woordenboek in plaats van op een volledig ingelezen export, en staat de zwaarst
verweven logica van de leeslaag niet meer op het gezicht ervan.
`GwswDataset.klim_naar_knoop`, `.resolve_network_node` en `.richting_van_geometrie`
blijven bestaan met dezelfde handtekening en hetzelfde gedrag: ze zijn doorgeefluiken
naar deze module (Harde regel in `CLAUDE.md`; `tests/test_publieke_api.py` pint ze).

Vier keuzes die opvallen als je ze niet verwacht:

- **`netwerk` en niet `wandeling` of `topologie`.** De modulenaam noemt de *vraag* en niet
  de techniek, zoals elke rij in de lagentabel van `docs/architectuur.md` dat doet:
  `bestand` gaat over bestanden, `klassen` over klassen, deze over het netwerk. Een naam
  naar de techniek (`wandeling`) zou de tweede functie niet dekken -- `richting_van_geometrie`
  wandelt niet, die rekent -- en `topologie` is in het GWSW een ruimer begrip dan wat hier
  staat en zou de volgende lezer verleiden er ook aansluitingen en samenhang in te leggen.
  Die wonen bij de afnemer, niet in de leeslaag.
- **De parameternamen zijn die van de gepinde methoden** (`uri`, `roots`, `conduit`) en
  niet de Nederlandse die `CLAUDE.md` voor nieuwe namen vraagt. Dat is hier met opzet:
  de doorgeefluik geeft ze een-op-een door, en twee namen voor hetzelfde argument zou
  de lezer bij elke stap laten vertalen. Hetzelfde geldt voor `nodes` en `is_a` -- dat
  zijn de namen van het veld en de methode waar ze vandaan komen.
- **En om diezelfde reden houdt `resolve_network_node` zijn Engelse naam**, als enige van
  de vier. Bij issue #33 koos de auteur voor een *nieuwe* functie Nederlands boven
  symmetrie (`lees_ontologie(paden=...)` naast `load_dataset(ontology_paths=...)`); daar
  lag de naam nog vrij. Hier niet: deze functie *is* de verhuisde methode, die gepind
  Engels heet. Een Nederlandse vrije functie met een Engels doorgeefluik ervoor zou twee
  namen voor één ding opleveren -- precies wat deze package elders vermijdt -- en de
  bewaker `test_de_netwerksnit_ligt_vast` kan dan niet meer op naamgelijkheid toetsen.
  Dat de vier daardoor drie Nederlandse en één Engelse naam dragen is de eerlijke
  weergave van waar de grens van het bevroren contract loopt, en een auteursbeslissing
  om het ooit anders te doen.
- **De memo is een parameter en geen dictionary in deze module.** Hij hoort bij de
  *dataset* en niet bij de wandeling: een uitgedunde dataset kan anders resolven dan de
  volle export (de wandeling ziet minder knopen), dus twee datasets mogen nooit dezelfde
  memo delen. `GwswDataset._resolved_nodes` blijft daarom waar hij stond, met zijn
  `init=False`, en komt hier als argument binnen.

Eén ding *is* met de verhuizing veranderd, en het staat hier omdat het aan de uitkomsten
niet te zien is: waar de methoden elkaar via `self.` aanriepen, roepen deze functies
elkaar rechtstreeks aan. Een subklasse die `klim_naar_knoop` overschrijft of een
`monkeypatch.setattr(GwswDataset, "resolve_network_node", ...)` wordt door de wandeling
binnenin dus niet meer gezien; wie de wandeling wil onderscheppen, doet dat op deze
module. Een afnemer kent geen subklasse van `GwswDataset` en patcht geen van de drie,
dus in de praktijk raakt dit niemand -- maar "puur verplaatst" gaat over de bodies, niet
over de dispatch.

Deze module leunt alleen op `domein` (en op shapely voor het punt-en-lijnrekenwerk); van
`dataset` en `cache` weet hij niets. Hij staat wel in `cache.LADERMODULES`: de
wandelcode zat tot issue #27 in `dataset.py` en telde dus al mee in de cachesleutel, en
dat blijft zo -- zie `docs/architectuur.md`, "De cache leest mee met de lader".
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from shapely.geometry import LineString, Point

from gwsw_orox_helpers.domein import Conduit, Node

# De memo van `resolve_network_node`: per (uri, wortels) de gevonden knoop, of `None`.
# Waarom de wortels in de sleutel horen, staat bij die functie. `GwswDataset._resolved_nodes`
# is het exemplaar dat de leeslaag gebruikt; de alias staat hier omdat de vorm bij de
# wandeling hoort en niet bij de dataclass.
Knoopmemo = dict[tuple[str, tuple[str, ...]], str | None]

# Het smalle typepredicaat waarmee de wandeling beslist of zij er is: `GwswDataset.is_a`,
# en met opzet die en niet `graph_is_a`. De wandeling moet stoppen zodra zij een knoop uit
# het *domeinmodel* te pakken heeft (zie de docstring van `is_a`), en zij stelt de vraag
# ruim een miljoen keer per run -- de graafopvraging van `graph_types_of` zou daar elke
# keer bij komen.
TypePredicaat = Callable[[str, str], bool]


def _schakels(bezocht: set[str], nodes: Mapping[str, Node]) -> frozenset[str]:
    """De bezochte URI's die een knoop zijn; de rest hoort niet in een analyseset."""
    return frozenset(uri for uri in bezocht if uri in nodes)


def resolve_network_node(
    uri: str | None,
    roots: list[str],
    nodes: Mapping[str, Node],
    is_a: TypePredicaat,
    memo: Knoopmemo,
) -> str | None:
    """Herleidt een gekoppeld object naar het knooppunt waar het onderdeel van is.

    Een streng koppelt niet altijd aan een put: in de GWSW-praktijk wijst de
    koppeling ook naar een compartiment of een hulpstuk. Voor de netwerkanalyse
    telt de put eromheen, dus wordt via hasPart omhooggelopen tot een object van
    een van de opgegeven wortelklassen.

    Gememoiseerd per (uri, wortels) in de meegegeven `memo`: de wandeling is
    deterministisch en de checks stellen dezelfde vraag ruim een miljoen keer per run.
    De wortels horen in de sleutel -- in de praktijk zijn ze constant binnen een run,
    maar een memo die dat stilzwijgend aanneemt zou bij een afwijkende aanroep het
    verkeerde antwoord teruggeven.

    De memo komt van buiten en wordt hier niet aangemaakt: hij hoort bij de dataset
    waarop geklommen wordt (`GwswDataset._resolved_nodes`), en twee datasets met
    verschillende knopen mogen er nooit een delen.
    """
    if uri is None:
        return None
    sleutel = (uri, tuple(roots))
    if sleutel not in memo:
        memo[sleutel] = klim_naar_knoop(uri, roots, nodes, is_a)[0]
    return memo[sleutel]


def klim_naar_knoop(
    uri: str | None,
    roots: list[str],
    nodes: Mapping[str, Node],
    is_a: TypePredicaat,
) -> tuple[str | None, frozenset[str]]:
    """De knoop boven dit object, plus de knopen die de wandeling erheen tegenkwam.

    In de breedte en niet langs een enkel pad: een onderdeel kan meer dan een
    houder hebben (`Node.parents`), en de eerste die rdflib oplevert hoeft niet
    de houder te zijn die op een knoop uitkomt. Een enkelpadswandeling zou dan
    leeg teruggeven terwijl er wel degelijk een put boven hangt, en welke houder
    "de eerste" is hangt af van de schrijfvolgorde van de export.

    Bij gelijke diepte wint de kleinste URI: willekeurig maar deterministisch,
    en dat is wat telt -- twee runs op dezelfde bestanden moeten dezelfde
    meldingen opleveren.

    De tweede uitkomst is de verzameling bezochte schakels die zelf in `nodes`
    staan; een afnemer die de analyseset uitdunt heeft die nodig om ze erin te houden,
    anders loopt dezelfde wandeling op de uitgedunde dataset dood. Bewust ruimer dan het
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
            if any(is_a(huidig, root) for root in roots):
                return huidig, _schakels(gezien, nodes)
        hoger: set[str] = set()
        for huidig in laag:
            node = nodes.get(huidig)
            if node is not None:
                hoger.update(node.parents)
        volgende = sorted(hoger - gezien)
        gezien.update(volgende)
        laag = volgende
    return None, _schakels(gezien, nodes)


def richting_van_geometrie(
    conduit: Conduit,
    roots: list[str],
    nodes: Mapping[str, Node],
    is_a: TypePredicaat,
    memo: Knoopmemo,
) -> tuple[bool, Node, Node] | None:
    """Vergelijkt de tekenrichting van de lijn met de van-naar-richting.

    Geeft (omgekeerd, beginput, eindput) terug, waarbij `omgekeerd` zegt of de
    lijn bij de administratieve eindput begint. None als er niets te vergelijken
    valt: geen geometrie, geen echte lijngeometrie, geen twee verschillende
    putten, of putten zonder punt. Een topologiecheck op de tekenrichting en de
    kaartlaag met richtingspijlen lezen allebei deze functie, zodat het kaartbeeld
    en de bevinding niet uit elkaar kunnen lopen.

    De twee koppelingen gaan langs `resolve_network_node` en dus langs dezelfde memo
    als de rest van de wandeling; een streng die op een compartiment aansluit hoort
    hier met de put eromheen vergeleken te worden.
    """
    if conduit.line is None or conduit.line.is_empty:
        return None
    if not isinstance(conduit.line, LineString):
        # Een GML-literaal in de leidinggeometrie hoeft geen lijn te zijn (zie
        # TOP-016 en `checks.meetkunde.coords_of`); zonder lijn is er geen
        # tekenrichting om te vergelijken.
        return None
    begin = nodes.get(resolve_network_node(conduit.start_node, roots, nodes, is_a, memo) or "")
    eind = nodes.get(resolve_network_node(conduit.end_node, roots, nodes, is_a, memo) or "")
    if begin is None or eind is None or begin.point is None or eind.point is None:
        return None
    if begin.uri == eind.uri:
        return None
    punten = list(conduit.line.coords)
    eerste, laatste = Point(punten[0][:2]), Point(punten[-1][:2])
    juist = eerste.distance(begin.point) + laatste.distance(eind.point)
    omgekeerd = eerste.distance(eind.point) + laatste.distance(begin.point)
    return omgekeerd < juist, begin, eind
