"""Een OroX-graaf terugschrijven als Turtle.

Dit is een **regenererende** serializer, geen bron-lexer: hij leest de bron met dezelfde
pyoxigraph-parser als de leeslaag en schrijft de triples opnieuw uit. Bronvolgorde,
commentaar, inspringing en de oorspronkelijke namen van blanke knopen zijn daarmee weg,
en een gewone string-literaal komt zonder `^^xsd:string` terug (pyoxigraph vouwt die
RDF-1.1-vorm samen, zie `graaf.naar_rdflib`). De belofte is dus niet byte-gelijkheid maar
**graafgelijkheid**: het teruggeschreven bestand parseert naar dezelfde RDF-graaf --
dezelfde triples, dezelfde literalen, dezelfde blanke-knoopstructuur. GML-literalen
(`^^geo:gmlLiteral`) en getaltypen gaan ongewijzigd mee; er wordt niets afgerond,
genormaliseerd of opnieuw opgemaakt.

De module heeft een **eigen pad, los van `load_dataset`**. Ze raakt `dataset.py` en
`graaf.py` niet aan en bouwt geen `GraafIndex`: de quads gaan als stroom van de parser
naar de serializer, zodat een export van honderden megabytes niet eerst als domeinmodel
in het geheugen hoeft. Wie de dataset ook wil *lezen*, gebruikt daarnaast `load_dataset`.

Twee ingangen, want een clip (fase 3) wil de twee helften wegschrijven zonder de bron
een tweede keer te parsen:

- `schrijf_orox(bron, doel)` -- bestand naar bestand, prefixen uit de bron;
- `lees_orox(bron)` plus `schrijf_orox_quads(quads, doel, prefixen=...)` -- de stroom komt
  één keer uit de parser, de afnemer filtert of vermenigvuldigt hem en schrijft hem zo
  vaak weg als nodig.

**Blanke knopen zijn documentgebonden, en dat is een eis aan de filter van fase 3.** Een
`_:b` heeft alleen betekenis binnen het bestand waarin hij staat; twee bestanden die
dezelfde knoop noemen, noemen na het lezen twee knopen. Een clip die de stroom in tweeën
deelt moet daarom **elke bnode-sluiting aan één kant houden**: gaat `:X gwsw:hasAspect
_:b` naar binnen, dan horen `_:b rdf:type gwsw:Punt` en al het andere dat aan `_:b` hangt
daar ook heen. Wie dwars door een blanke knoop snijdt, raakt geen triple kwijt maar wel de
brug ertussen -- de helften zijn dan niet meer tot de bron te herenigen, en geen
serializer kan dat repareren. `tests/test_schrijven.py` legt beide uitkomsten vast: een
snede langs een gewoon subject herenigt wel, een snede door een blanke knoop niet. In
OroX hangen de meeste aspectwaarden aan zulke knopen, dus dit is de regel en niet de
uitzondering.

De prefixmap is expliciet (`STANDAARD_PREFIXEN`: rdf, rdfs, owl, xsd, skos, geo, gwsw)
en wordt aangevuld met wat de bron zelf declareert -- onder meer de dataset-basis `:`,
die per dataset verschilt (`http://sparql.gwsw.nl/repositories/<naam>#`). Prefixen zijn
schrijfwijze, geen inhoud: een prefix meer of minder verandert de graaf niet.

Coderingen: er wordt altijd UTF-8 geschreven, want dat is wat Turtle voorschrijft. Aan de
leeskant kent deze module dezelfde `fallback_encoding` als `load_dataset`, want niet elke
exporttool houdt zich aan die regel -- de BrutIS-export van De Wolden en Hoogeveen draagt
een handvol cp850-bytes (`"cavaljéweg"`), en zonder terugval loopt de parser daarop stuk.
Zo'n bestand komt er dus als UTF-8 uit; dat is geen verlies maar een reparatie, en het is
de enige plek waar de uitvoer bewust van de bron afwijkt.
"""

from __future__ import annotations

import contextlib
import itertools
import os
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final

import pyoxigraph

from gwsw_orox_helpers.errors import DatasetError

GWSW = "http://data.gwsw.nl/1.6/totaal/"

# De kop van een OroX-export. `gwsw` staat op 1.6 (de leidende versie, zie CLAUDE.md);
# declareert de bron een andere, dan wint die van de bron (zie `lees_orox`). De
# dataset-basis `:` zit hier niet in: die verschilt per dataset en komt uit de bron of
# van de afnemer. Onmuteerbaar, want dit is gedeelde staat: één afnemer die er een sleutel
# in verzet, verzet hem voor iedereen die daarna schrijft.
STANDAARD_PREFIXEN: Final[Mapping[str, str]] = MappingProxyType(
    {
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "owl": "http://www.w3.org/2002/07/owl#",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
        "skos": "http://www.w3.org/2004/02/skos/core#",
        "geo": "http://www.opengis.net/ont/geosparql#",
        "gwsw": GWSW,
    }
)

# PN_PREFIX uit de Turtle-grammatica, vereenvoudigd: een letter, daarna letters, cijfers,
# `_`, `-` of `.`, en niet eindigend op een punt. De lege sleutel hoort erbij: dat is de
# dataset-basis `:`. pyoxigraph controleert dit zelf niet -- `{"kapot prefix": ...}` komt
# er ongemoeid als `@prefix kapot prefix: <...> .` uit, en dat leest niemand meer terug.
PREFIX_PATROON: Final = re.compile(r"\A(?:[^\W\d_](?:[\w.\-]*[\w\-])?)?\Z")


@dataclass(frozen=True)
class OroxBron:
    """Een geopende OroX-bron: de quadstroom plus de prefixen die de bron declareert.

    `quads` is een stroom die één keer af te lopen is, niet een verzameling in het
    geheugen. Wie hem twee keer nodig heeft (een clip die een binnen- en een
    buitenhelft schrijft), loopt hem één keer af en verdeelt onderweg zelf.
    """

    quads: Iterator[pyoxigraph.Quad]
    prefixen: dict[str, str]


def lees_orox(bron: Path, fallback_encoding: str | None = None) -> OroxBron:
    """Opent `bron` als quadstroom en haalt de prefixdeclaraties eruit.

    pyoxigraph kent de prefixen pas nadat het de kop gelezen heeft, dus wordt de stroom
    hier met één quad op gang gebracht en die quad er daarna weer voorgeplakt. Zo staat
    de prefixmap klaar vóór de eerste regel uitvoer, zonder dat het hele bestand eerst
    in het geheugen moet.

    `fallback_encoding` betekent hetzelfde als in `load_dataset`: zonder opgave moet de
    bron UTF-8 zijn (en dan leest de parser hem streamend van schijf), met opgave wordt
    een bron die dat niet is alsnog gelezen. Dat laatste kost geheugen -- het bestand
    moet dan eerst in zijn geheel gedecodeerd worden -- en gebeurt daarom alleen als de
    afnemer erom vraagt.

    Een lege bron (nul quads) levert een lege stroom met alleen de bronprefixen die de
    parser tot dan toe zag.
    """
    try:
        if fallback_encoding is None:
            parser = pyoxigraph.parse(path=bron, format=pyoxigraph.RdfFormat.TURTLE)
        else:
            parser = pyoxigraph.parse(
                _gedecodeerd(bron, fallback_encoding), format=pyoxigraph.RdfFormat.TURTLE
            )
    except OSError as fout:
        raise DatasetError(f"{bron}: bestand kan niet gelezen worden ({fout}).") from fout

    stroom = _gecontroleerd(bron, parser, fallback_encoding)
    eerste = list(itertools.islice(stroom, 1))
    prefixen = {**STANDAARD_PREFIXEN, **parser.prefixes}
    return OroxBron(quads=itertools.chain(eerste, stroom), prefixen=prefixen)


def schrijf_orox(bron: Path, doel: Path, fallback_encoding: str | None = None) -> None:
    """Leest de OroX-TTL `bron` en schrijft hem als Turtle naar `doel`.

    Niet byte-gelijk aan de bron, wel graaf-gelijk: `doel` parseert naar dezelfde RDF-graaf
    (zie de moduledocstring). De prefixen van de bron -- inclusief de dataset-basis `:` --
    komen mee, aangevuld met `STANDAARD_PREFIXEN`. `fallback_encoding` betekent hetzelfde
    als in `load_dataset` en `lees_orox`; de uitvoer is hoe dan ook UTF-8.
    """
    geopend = lees_orox(bron, fallback_encoding)
    schrijf_orox_quads(geopend.quads, doel, prefixen=geopend.prefixen)


def schrijf_orox_quads(
    quads: Iterable[pyoxigraph.Quad] | Iterable[pyoxigraph.Triple],
    doel: Path,
    *,
    prefixen: Mapping[str, str] | None = None,
) -> None:
    """Schrijft een al geparseerde quad- of triplestroom als OroX-Turtle naar `doel`.

    Dit is de ingang voor afnemers die de bron zelf al in handen hebben -- de clip van
    fase 3 filtert de stroom van `lees_orox` en schrijft de helften hiermee weg, zonder
    de bron opnieuw te parsen. `quads` mag een luie iterator zijn; hij wordt al
    schrijvend afgelopen en niet eerst verzameld. Quads en triples zijn niet te mengen:
    pyoxigraph wil één van beide (Turtle kent geen benoemde grafen).

    `prefixen` zijn de declaraties in de kop; zonder opgave staat er alleen
    `STANDAARD_PREFIXEN` (dus geen dataset-basis `:`, want die kent deze functie niet).
    Ze veranderen alleen de schrijfwijze van de IRI's, niet de graaf. De sleutels moeten
    wel PN_PREFIX-en zijn (`PREFIX_PATROON`); pyoxigraph controleert dat niet en zou een
    kapotte sleutel gewoon uitschrijven.

    Er wordt naar een tmp-bestand naast `doel` geschreven en pas na de laatste quad
    hernoemd. Een luie bron kan halverwege afbreken -- een syntaxfout op regel 900.000 --
    en dan hoort er geen afgekapte export achter te blijven die zich als een hele
    voordoet. Wie na een `DatasetError` naar `doel` kijkt, ziet het oude bestand of niets.
    """
    kop = dict(prefixen) if prefixen is not None else dict(STANDAARD_PREFIXEN)
    for sleutel in kop:
        if not PREFIX_PATROON.match(sleutel):
            raise DatasetError(
                f"{doel}: {sleutel!r} is geen geldige Turtle-prefix; een prefix begint met "
                "een letter, bestaat verder uit letters, cijfers, '_', '-' en '.', en "
                "eindigt niet op een punt (de lege sleutel is de dataset-basis ':')."
            )

    # Dezelfde map, want `os.replace` is alleen binnen één bestandssysteem atomair.
    tijdelijk = doel.with_suffix(doel.suffix + ".tmp")
    try:
        doel.parent.mkdir(parents=True, exist_ok=True)
        with tijdelijk.open("wb") as bestand:
            pyoxigraph.serialize(quads, bestand, pyoxigraph.RdfFormat.TURTLE, prefixes=kop)
        os.replace(tijdelijk, doel)
    except OSError as fout:
        raise DatasetError(f"{doel}: bestand kan niet geschreven worden ({fout}).") from fout
    finally:
        # Na een geslaagde hernoeming is er niets meer op te ruimen; na een fout onderweg
        # (parsefout, OSError, Ctrl-C) wel. Het opruimen mag de oorspronkelijke fout niet
        # overschreeuwen -- ligt `doel` onder een bestand, dan faalt ook deze `unlink`.
        with contextlib.suppress(OSError):
            tijdelijk.unlink(missing_ok=True)


def _gedecodeerd(bron: Path, fallback_encoding: str) -> str:
    """De inhoud van `bron` als tekst: UTF-8, of anders de opgegeven terugvalcodering.

    Dezelfde regel als aan de leeskant (`dataset._decode`): UTF-8 heeft voorrang en de
    terugval geldt alleen voor een bron die geen geldige UTF-8 is. Wat de leeskant er
    extra bij doet -- het aantal afwijkende bytes en een paar voorbeeldregels vastleggen
    in `DecodeFallback` -- hoort bij het rapporteren van een lezing, niet bij het
    terugschrijven ervan; die weg wordt hier dus niet gedeeld maar ook niet nagebouwd.
    """
    rauw = bron.read_bytes()
    try:
        return rauw.decode("utf-8")
    except UnicodeDecodeError as fout:
        eerste_byte, eerste_positie = rauw[fout.start], fout.start

    try:
        return rauw.decode(fallback_encoding)
    except (UnicodeDecodeError, LookupError) as fout:
        raise DatasetError(
            f"{bron}: geen geldige UTF-8 (byte {eerste_byte:#04x} op positie "
            f"{eerste_positie}) en ook niet te lezen als {fallback_encoding} ({fout})."
        ) from fout


def _gecontroleerd(
    bron: Path, parser: Iterator[pyoxigraph.Quad], fallback_encoding: str | None
) -> Iterator[pyoxigraph.Quad]:
    """Vertaalt parsefouten onderweg naar `DatasetError`, net als de leeslaag doet.

    De parser is lui: een syntaxfout halverwege een export van 112 MB komt pas boven bij
    de quad waar hij staat, dus midden in het schrijven. Zonder deze laag zou de afnemer
    daar een pyoxigraph-`SyntaxError` zien in plaats van de `DatasetError` die de package
    voor onleesbare bronnen belooft.

    Eén parsefout krijgt een eigen formulering. Leest de parser rechtstreeks van schijf
    (geen `fallback_encoding`) en draagt de bron niet-UTF-8-bytes, dan struikelt hij over
    de codering en niet over de syntaxis; "geen geldige Turtle" zou de afnemer dan naar
    een niet-bestaande syntaxfout sturen. De leeslaag zegt in dat geval dat er een
    terugvalcodering ontbreekt (`dataset._decode`), en dat zegt deze laag hem na. Het
    kost geen tweede lezing: het oordeel komt uit de foutmelding van de parser, dus de
    bron blijft streamen.
    """
    try:
        yield from parser
    except (SyntaxError, ValueError) as fout:
        if fallback_encoding is None and "Invalid UTF-8" in str(fout):
            raise DatasetError(
                f"{bron}: geen geldige UTF-8 ({fout}) en er is geen terugvalcodering opgegeven."
            ) from fout
        raise DatasetError(f"{bron}: geen geldige Turtle ({fout}).") from fout
