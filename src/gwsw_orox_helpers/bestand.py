"""Van TTL-bestand naar een gevulde `GraafIndex`: het parseerpad van de leeskant.

Alles wat een *bestand* aanraakt om die index te vullen staat hier: de bytes van schijf,
de codering met haar terugval, de aanroep van de parser en het procesbrede neveneffect
dat daaromheen hangt (de cyclische GC). De domeinlezers van `inlezen` bevragen
uitsluitend een al gevulde `GraafIndex` en kennen sinds issue #26 geen paden, geen bytes
en geen coderingen meer. Die twee clusters deelden niets anders dan die index, en uit
elkaar gehaald is het testen van de lezers geen kwestie van een echt bestand meer.

**In de lagentabel staat deze module ónder `inlezen`, maar er loopt geen rand tússen de
twee.** Onder, omdat hij alleen op de bladeren leunt (`codering`, `errors`, `graaf`,
`rdfmotor`) en `inlezen` daar nog `domein`, `geometry`, `klassen` en `namen` bij heeft;
géén rand, omdat geen van beide de ander importeert -- `dataset` haalt `_parse` en
`_gc_uit` rechtstreeks hier op en `inlezen` her-exporteert ze niet.
`test_de_bestandssnit_ligt_vast` bewaakt precies die twee dingen.

**De leeskant van pyoxigraph.** `_parse` leest een TTL-bestand als quadstroom en vult
daarmee een `GraafIndex` met rdflib-termen. Dat is bewust een ander pad dan dat van
`schrijven`, dat dezelfde parser gebruikt maar de stroom rechtstreeks doorgeeft aan de
serializer: wie leest heeft een index nodig en betaalt daarvoor de termconversie, wie
terugschrijft heeft die index juist niet nodig en zou hem op een export van honderden
megabytes niet eens in het geheugen krijgen. De twee delen wat ze wel kunnen delen: de
coderingsregel (`codering`) en de aanroep van de motor zelf (`rdfmotor`, dat ook de
ondersteunde pyoxigraph-reeks bewaakt).

Alle namen hier zijn privé en dat blijft zo. Het oppervlak van de leeslaag ligt in
`dataset` -- `load_dataset` voor de dataset, `lees_ontologie` voor de ontologie -- en dat
is ook de enige aanroeper binnen de package.
"""

from __future__ import annotations

import gc
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from gwsw_orox_helpers import namen, rdfmotor
from gwsw_orox_helpers.codering import DecodeFallback, decodeer, terugvalverslag
from gwsw_orox_helpers.errors import BestandError, TurtleError
from gwsw_orox_helpers.graaf import GraafIndex

_logger = logging.getLogger(__name__)


@contextmanager
def _quiet_rdflib() -> Iterator[None]:
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


@contextmanager
def _gc_uit() -> Iterator[None]:
    """Legt de cyclische GC stil rond een leesfase.

    Hij zou anders bij elke paar duizend nieuwe dicts opnieuw door alles lopen wat er al
    staat, en dat groeit tot miljoenen containers -- op de De Wolden en Hoogeveen-export
    kostte dat 2,2 van de 14 seconden van de vullus alleen al. Er ontstaat per constructie
    geen kringetje: de dicts, de lijsten, de rdflib-termen en de waardeobjecten wijzen
    alleen naar beneden. Wat dit *niet* uitzet is de referentietelling, dus wat vrijkomt
    gaat nog altijd meteen weg.

    **Twee aanroepers, genest.** De buitenste is `dataset.load_dataset`, om het hele
    leesblok: beide parses, de klassenafleiding en de objectopbouw van `_read_nodes` en
    `_read_conduits`, die zelf miljoenen tuples en dataclasses maakt. De binnenste staat
    hieronder in `_parse`, om `GraafIndex.vul_uit` heen. Nesten is neveneffectvrij: de
    binnenste kijkt naar `gc.isenabled()`, ziet dat de buitenste de GC al uit heeft en
    laat die stand met rust.

    **Waarom hier en niet in `GraafIndex.vul_uit`.** De GC uitzetten is een procesbreed
    neveneffect en dat hoort niet in een publieke, gepinde methode: wie `vul_uit` van
    buiten aanroept, hoort niet ongevraagd de GC van zijn hele proces te zien wisselen.
    `_parse` is de enige productieweg ernaartoe -- voor de dataset zowel als voor elk
    ontologiebestand -- dus de winst is dezelfde. `load_dataset` is wél een eigen,
    buitenste productieaanroep, en zegt het neveneffect in haar eigen docstring toe.

    De oude stand komt in `finally` terug, ook als de stroom halverwege afbreekt, en een
    aanroeper die de GC zelf al uit had houdt hem uit.
    """
    stond_aan = gc.isenabled()
    if stond_aan:
        gc.disable()
    try:
        yield
    finally:
        if stond_aan:
            gc.enable()


def _parse(
    path: Path, fallback_encoding: str | None, index: GraafIndex | None = None
) -> tuple[GraafIndex, DecodeFallback | None]:
    """Leest een enkel TTL-bestand in, desnoods via een terugvalcodering.

    Het parsen zelf gaat via pyoxigraph's Rust-parser (ordegrootten sneller dan rdflib's
    pure-Python `notation3`), aangeroepen via `rdfmotor` -- de ene naad waarlangs deze
    package die motor bereikt; de triples vullen in stream-volgorde een `GraafIndex` met
    rdflib-termen, zodat de checks en de rest van de lader hun vergelijkingen houden.
    pyoxigraph verlangt UTF-8-bytes, dus de al gedecodeerde tekst wordt opnieuw als
    UTF-8 gecodeerd -- niet de ruwe bytes, die immers cp850 kunnen zijn. Een meegegeven
    `index` wordt aangevuld; zo stapelen meerdere ontologiebestanden in een index.
    """
    try:
        rauw = path.read_bytes()
    except OSError as error:
        raise BestandError(f"{path}: bestand kan niet gelezen worden ({error}).") from error

    tekst, fallback = _decode(path, rauw, fallback_encoding)

    index = index if index is not None else GraafIndex()
    try:
        quads = rdfmotor.ontleed_turtle(tekst.encode("utf-8"))
        # rdflib waarschuwt bij het bouwen van een literaal met een ongeldige lexicale
        # vorm (de meegeleverde ontologie draagt een xsd:date "20210830" zonder streepjes);
        # net als bij de oude parse hoort die traceback niet in de CLI-uitvoer thuis.
        with _quiet_rdflib(), _gc_uit():
            index.vul_uit(quads)
    except Exception as error:  # pyoxigraph gooit uiteenlopende parsefouten
        raise TurtleError(f"{path}: geen geldige Turtle ({error}).") from error
    # De gedetecteerde GWSW-basis van dit bestand (issue #32), hier gezet zodat de lezers
    # van `inlezen` hun predicaten en klasse-IRI's uit de bron afleiden in plaats van uit de
    # vaste 1.6-string. Twee wegen, in deze volgorde. De `gwsw:`-prefix van de bron is de
    # goedkope eerste: na `vul_uit` is `quads` uitgeput en zijn de prefixdeclaraties gelezen.
    # Ontbreekt die -- een export zonder de declaratie is geldig Turtle -- dan volgt een scan
    # over de predicaat-IRI's van de graaf (een OroX draagt `gwsw:hasAspect` en verwanten);
    # `index._pos` is de predicaatverzameling, klein en met de basis in de IRI zelf. Levert
    # ook dat niets op, dan valt de lezing terug op 1.6, nooit stil maar met een melding,
    # zodat een bron met een onherkenbare versie zichtbaar wordt in plaats van leeg gelezen.
    # Bij het stapelen van meerdere ontologiebestanden in dezelfde index wint de basis van
    # het laatst gelezen bestand -- die zijn in de praktijk allemaal van één versie.
    basis = namen.basis_uit_prefixen(quads.prefixes)
    if basis is None:
        basis = next(
            (b for term in index._pos if (b := namen.basis_uit_iri(str(term))) is not None),
            None,
        )
    if basis is None:
        _logger.warning(
            "%s: geen herkenbare GWSW-versie in de prefixen of de IRI's; de lezing valt terug "
            "op de gebundelde 1.6-termenset. Een bron op een andere versie wordt daarmee "
            "mogelijk leeg gelezen.",
            path,
        )
        basis = namen.GWSW
    index.gwsw_basis = basis
    return index, fallback


def _decode(
    path: Path, rauw: bytes, fallback_encoding: str | None
) -> tuple[str, DecodeFallback | None]:
    """Decodeert de inhoud, en legt vast als dat niet als UTF-8 lukte.

    De regel zelf -- UTF-8 heeft voorrang, de terugval geldt alleen voor een bestand dat
    daar niet aan voldoet, en zonder terugvalcodering is de afwijking een fout -- staat in
    `codering.decodeer`, want de schrijflaag leest hem daar ook. Wat hier bij komt is het
    verslag, en dat is het verschil tussen lezen en terugschrijven: een lezing wordt
    gerapporteerd (`GwswDataset.decode_fallback`), een terugschrijving niet.
    """
    tekst, gebruikt = decodeer(path, rauw, fallback_encoding)
    if gebruikt is None:
        return tekst, None
    return tekst, terugvalverslag(path, rauw, gebruikt)
