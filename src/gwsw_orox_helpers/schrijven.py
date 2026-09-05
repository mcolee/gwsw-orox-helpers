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

Wat ze wel met de leeslaag deelt is de kennis die anders uit elkaar zou lopen, en die
staat onder allebei: de IRI's in `namen`, de coderingsregel in `codering` en de aanroep
van de motor in `rdfmotor` (`ontleed_turtle` / `serialiseer_turtle`, plus de poort op de
ondersteunde pyoxigraph-reeks). Dat is geen gat in het eigen pad maar de reden dat het er
een blijft -- een tweede exemplaar van de `gwsw:`-IRI of van de UTF-8-terugval zou pas
opvallen als de twee lagen dezelfde bron verschillend lazen.

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
import secrets
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final, cast

import pyoxigraph

from gwsw_orox_helpers import namen, rdfmotor
from gwsw_orox_helpers.codering import hercodeerstroom
from gwsw_orox_helpers.errors import BestandError, CoderingError, TurtleError
from gwsw_orox_helpers.namen import GWSW

# De kop van een OroX-export. De IRI's komen uit `namen`, de ene plek waar ze staan: de
# `gwsw:`-prefix hier en de klassen die de leeslaag opzoekt horen dezelfde versie te
# spellen, en dat is met twee lijstjes niet vol te houden. Declareert de bron een andere,
# dan wint die van de bron (zie `lees_orox`). De dataset-basis `:` zit hier niet in: die
# verschilt per dataset en komt uit de bron of van de afnemer. Onmuteerbaar, want dit is
# gedeelde staat: één afnemer die er een sleutel in verzet, verzet hem voor iedereen die
# daarna schrijft.
STANDAARD_PREFIXEN: Final[Mapping[str, str]] = MappingProxyType(
    {
        "rdf": namen.RDF,
        "rdfs": namen.RDFS,
        "owl": namen.OWL,
        "xsd": namen.XSD,
        "skos": namen.SKOS,
        "geo": namen.GEO,
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


def lees_orox(bron: str | os.PathLike[str], fallback_encoding: str | None = None) -> OroxBron:
    """Opent `bron` als quadstroom en haalt de prefixdeclaraties eruit.

    pyoxigraph kent de prefixen pas nadat het de kop gelezen heeft, dus wordt de stroom
    hier met één quad op gang gebracht en die quad er daarna weer voorgeplakt. Zo staat
    de prefixmap klaar vóór de eerste regel uitvoer, zonder dat het hele bestand eerst
    in het geheugen moet.

    `fallback_encoding` betekent hetzelfde als in `load_dataset`: zonder opgave moet de
    bron UTF-8 zijn (en dan leest de parser hem streamend van schijf), met opgave wordt
    een bron die dat niet is alsnog gelezen. Ook die tak **streamt** sinds issue #66: hij
    bouwt geen volledige `str` meer maar geeft een hercodeerstroom
    (`codering.hercodeerstroom`) aan `ontleed_turtle_stroom`, die de bron blokgewijs van de
    terugvalcodering naar UTF-8 hercodeert. Zo houdt ook een cp850-export van honderden
    megabytes maar één blok tegelijk in het geheugen in plaats van de hele bron als bytes
    én als `str`.

    Een lege bron (nul quads) levert een lege stroom met alleen de bronprefixen die de
    parser tot dan toe zag.

    Draagt de bron een UTF-8-BOM, dan helpt het bestandspad niet: pyoxigraph opent het
    bestand dan zelf en struikelt over de `U+FEFF` als eerste subject (issue #53). Daarom
    wordt de kop gepeekt en gaat een bron met BOM langs de hercodeerstroom -- dezelfde tak
    die er al is voor een terugvalcodering -- die de tekst zonder BOM (`utf-8-sig`) streamend
    aan de motor levert. Zonder BOM en zonder terugvalcodering blijft het bestandspad
    byte-gelijk naar de motor gaan, dus blijft de export van honderden megabytes buiten het
    geheugen.

    Een str- of ander `os.PathLike`-pad wordt hier tot `Path` gemaakt: een bibliotheek
    hoort een str-pad te accepteren, en de hercodeerstroom opent `bron` zelf (issue #55).
    """
    bron = Path(bron)
    try:
        if fallback_encoding is None and not _begint_met_bom(bron):
            parser = rdfmotor.ontleed_turtle_bestand(bron)
        else:
            parser = rdfmotor.ontleed_turtle_stroom(hercodeerstroom(bron, fallback_encoding))
    except OSError as fout:
        raise BestandError(f"{bron}: bestand kan niet gelezen worden ({fout}).") from fout

    stroom = _gecontroleerd(bron, parser, fallback_encoding)
    eerste = list(itertools.islice(stroom, 1))
    prefixen = {**STANDAARD_PREFIXEN, **rdfmotor.prefixen_van(parser)}
    return OroxBron(quads=itertools.chain(eerste, stroom), prefixen=prefixen)


def schrijf_orox(
    bron: str | os.PathLike[str],
    doel: str | os.PathLike[str],
    fallback_encoding: str | None = None,
    *,
    deterministisch: bool = False,
) -> None:
    """Leest de OroX-TTL `bron` en schrijft hem als Turtle naar `doel`.

    Niet byte-gelijk aan de bron, wel graaf-gelijk: `doel` parseert naar dezelfde RDF-graaf
    (zie de moduledocstring). De prefixen van de bron -- inclusief de dataset-basis `:` --
    komen mee, aangevuld met `STANDAARD_PREFIXEN`. `fallback_encoding` betekent hetzelfde
    als in `load_dataset` en `lees_orox`; de uitvoer is hoe dan ook UTF-8. Een str- of ander
    `os.PathLike`-pad mag: `lees_orox` en `schrijf_orox_quads` coerceren zelf naar `Path`.

    `deterministisch` gaat ongewijzigd door naar `schrijf_orox_quads`; met de default
    `False` verandert er geen byte aan de bestaande uitvoer, met `True` zijn twee beurten
    van dezelfde bron byte-gelijk. Zie `schrijf_orox_quads` voor wat het doet en kost. De
    graaf blijft in beide gevallen dezelfde.
    """
    geopend = lees_orox(bron, fallback_encoding)
    schrijf_orox_quads(
        geopend.quads, doel, prefixen=geopend.prefixen, deterministisch=deterministisch
    )


def schrijf_orox_quads(
    quads: Iterable[pyoxigraph.Quad] | Iterable[pyoxigraph.Triple],
    doel: str | os.PathLike[str],
    *,
    prefixen: Mapping[str, str] | None = None,
    deterministisch: bool = False,
) -> None:
    """Schrijft een al geparseerde quad- of triplestroom als OroX-Turtle naar `doel`.

    Dit is de ingang voor afnemers die de bron zelf al in handen hebben -- de clip van
    fase 3 filtert de stroom van `lees_orox` en schrijft de helften hiermee weg, zonder
    de bron opnieuw te parsen. `quads` mag een luie iterator zijn; hij wordt al
    schrijvend afgelopen en niet eerst verzameld. Een gemengde Quad/Triple-stroom mag:
    Turtle kent geen benoemde grafen, dus een default-graaf-`Quad` schrijft byte-gelijk aan
    de gelijke `Triple`, en de clip van fase 3 leunt daarop (issue #64) -- hij geeft de
    bron-`Quad` ongewijzigd door waar hij niets herschrijft en mengt dat met de `Triple`-en
    van het herschrijfpad. Het uniontype verwoordt de stroom homogeen; de clip cast de mix.

    `prefixen` zijn de declaraties in de kop; zonder opgave staat er alleen
    `STANDAARD_PREFIXEN` (dus geen dataset-basis `:`, want die kent deze functie niet).
    Ze veranderen alleen de schrijfwijze van de IRI's, niet de graaf. De sleutels moeten
    wel PN_PREFIX-en zijn (`PREFIX_PATROON`); pyoxigraph controleert dat niet en zou een
    kapotte sleutel gewoon uitschrijven.

    `deterministisch` (default `False`) maakt twee schrijfbeurten van dezelfde stroom
    byte-gelijk. pyoxigraph mint per parse eigen namen voor blanke knopen (`_:<random>`),
    dus verschilt de default-uitvoer per beurt -- graaf-gelijk maar niet byte-gelijk, en
    dus diff- en git-onvriendelijk. Met `True` loopt de stroom eerst door `_hernummerd`,
    dat elke blanke knoop op eerste ontmoeting (subject vóór object) hernummert naar
    `_:b<n>` in stroomvolgorde; dezelfde stroom levert dan dezelfde bytes. Het **kost** een
    extra gang over elke term en een tabel van de blanke knopen in het geheugen (niet de
    hele stroom, alleen de labels), en het **verandert de graaf niet**: blanke-knooplabels
    zijn documentgebonden, dus hernummeren geeft een isomorfe graaf. Met de default `False`
    gaat de stroom onveranderd naar de serializer en verandert er geen byte aan wat de
    functie tot nu toe schreef.

    **rdflib-beperking (`:eind\\.`).** Draagt een IRI onder een prefix een lokaal deel dat
    op een punt eindigt (bv. `<...#eind.>`), dan schrijft pyoxigraph dat als `:eind\\.`
    (PN_LOCAL_ESC). Dat is geldig Turtle 1.1 en pyoxigraph leest het lexicaal identiek
    terug, maar rdflib 7.x weigert de escape aan het eind van een PN_LOCAL met `BadSyntax`.
    Deze serializer wijkt daar niet voor uit -- de basisprefix weglaten zou de bytes van de
    default-uitvoer veranderen -- dus zo'n bron blijft door rdflib onleesbaar tot rdflib het
    repareert (upstream te melden). `tests/test_schrijven.py` pint die stand.

    Er wordt naar een tmp-bestand naast `doel` geschreven en pas na de laatste quad
    hernoemd. Een luie bron kan halverwege afbreken -- een syntaxfout op regel 900.000 --
    en dan hoort er geen afgekapte export achter te blijven die zich als een hele
    voordoet. Wie na een `DatasetError` naar `doel` kijkt, ziet het oude bestand of niets.

    Dat tmp-bestand krijgt een naam met het proces-ID en een willekeurig deel erin, en
    wordt aangemaakt met `open(..., 'xb')` (`O_CREAT | O_EXCL`). Om twee redenen. `O_EXCL`
    weigert een naam die er al is en volgt dus geen symlink: een vooraf geplant tijdelijk
    pad in een gedeelde uitmap zou anders doorgeschreven worden naar waar het heen wijst
    (CWE-59/377). En het willekeurige deel houdt twee gelijktijdige runs naar hetzelfde
    doel uit elkaars tijdelijke bestand. De rechten zijn de rechten van een nieuw
    aangemaakt bestand (`0o666 & ~umask`).

    Een str- of ander `os.PathLike`-pad wordt hier tot `Path` gemaakt (issue #55): een
    bibliotheek hoort een str-pad te accepteren, en hieronder wordt `doel.parent` gelezen.
    """
    doel = Path(doel)
    stroom: Iterable[pyoxigraph.Quad] | Iterable[pyoxigraph.Triple] = (
        cast(
            "Iterable[pyoxigraph.Quad] | Iterable[pyoxigraph.Triple]",
            _hernummerd(quads),
        )
        if deterministisch
        else quads
    )
    kop = dict(prefixen) if prefixen is not None else dict(STANDAARD_PREFIXEN)
    for sleutel in kop:
        if not PREFIX_PATROON.match(sleutel):
            raise TurtleError(
                f"{doel}: {sleutel!r} is geen geldige Turtle-prefix; een prefix begint met "
                "een letter, bestaat verder uit letters, cijfers, '_', '-' en '.', en "
                "eindigt niet op een punt (de lege sleutel is de dataset-basis ':')."
            )

    # Dezelfde map, want `replace` is alleen binnen één bestandssysteem atomair. `None`
    # zolang het tijdelijke bestand niet aan de beurt was: faalt het aanmaken van de
    # doelmap, dan is er ook geen tijdelijk bestand om op te ruimen.
    tijdelijk: Path | None = None
    try:
        doel.parent.mkdir(parents=True, exist_ok=True)
        # Eigen naam plus de `x`-modus (`O_CREAT | O_EXCL`, mode 0o666) in plaats van
        # `tempfile.mkstemp`, anders dan in `cache._schrijf_atomair`: die schrijft privé
        # pickles in `~/.cache`, waar de 0600 van `mkstemp` gewenst is, maar de schrijflaag
        # levert een bestand af in andermans uitmap en mag de rechten van de gebruiker niet
        # verstrengen. `O_EXCL` geeft dezelfde symlink-afsluiting; de kernel past
        # `0o666 & ~umask` toe, zoals `open('wb')` deed. Een naambotsing (kans ~0 bij 8 hex)
        # is een `FileExistsError` en gaat als `BestandError` naar boven, net als elke
        # andere OSError hier.
        kandidaat = doel.parent / f"{doel.name}.{os.getpid()}.{secrets.token_hex(4)}.tijdelijk"
        with open(kandidaat, "xb") as bestand:
            # De `open` staat bewust buiten het opruimbereik: pas hier, ná een geslaagd
            # aanmaken, wordt het pad opruimbaar. De `finally` mag alleen weghalen wat hij
            # zelf maakte -- weigert de `x` de naam, dan is dat bestand van iemand anders.
            tijdelijk = kandidaat
            rdfmotor.serialiseer_turtle(stroom, bestand, prefixen=kop)
        tijdelijk.replace(doel)
        # Na de hernoeming bestaat het tijdelijke pad niet meer; de `finally` mag er dan
        # ook niet meer naar grijpen (een minuscule TOCTOU als de naam intussen hergebruikt
        # zou zijn).
        tijdelijk = None
    except OSError as fout:
        raise BestandError(f"{doel}: bestand kan niet geschreven worden ({fout}).") from fout
    finally:
        # Na een geslaagde hernoeming is er niets meer op te ruimen; na een fout onderweg
        # (parsefout, OSError, Ctrl-C) wel. Het opruimen mag de oorspronkelijke fout niet
        # overschreeuwen -- ligt `doel` onder een bestand, dan faalt ook deze `unlink`.
        if tijdelijk is not None:
            with contextlib.suppress(OSError):
                tijdelijk.unlink(missing_ok=True)


def _hernummerd(
    quads: Iterable[pyoxigraph.Quad] | Iterable[pyoxigraph.Triple],
) -> Iterator[pyoxigraph.Quad | pyoxigraph.Triple]:
    """De stroom met elke blanke knoop hernummerd naar `_:b<n>` in stroomvolgorde.

    Dit is het codepad achter `deterministisch=True`. Elke `BlankNode` krijgt op eerste
    ontmoeting -- subject vóór object, altijd in die volgorde -- een naam `b<n>` die de
    stroomvolgorde volgt, en is daarmee bij elke lezing van dezelfde bron dezelfde, anders
    dan de willekeurige namen die pyoxigraph zelf mint. Een term die geen blanke knoop is
    (een `NamedNode`, een `Literal`, of een RDF-ster-`Triple`) blijft ongewijzigd; een
    RDF-ster-triple wordt dus als geheel doorgegeven en zijn binnenste knopen worden niet
    hernummerd. Een quad zonder blanke knoop gaat ongewijzigd door -- geen nieuwe term, geen
    nieuwe quad.

    De pyoxigraph-term-fabrieken (`BlankNode`, `Quad`, `Triple`) worden hier rechtstreeks
    aangeroepen en niet via `rdfmotor`: die naad draagt alleen parse en serialize, de
    fabrieken staan bewust buiten de adapter (zie `docs/architectuur.md`, "Wat er niet
    doorheen gaat"). De twee takken staan, net als in `clip.plan._genummerd`, uitgeschreven
    in plaats van in een hulp per term: deze lus draait per quad van de bron.
    """
    labels: dict[str, pyoxigraph.BlankNode] = {}
    teller = itertools.count()
    blank_node = pyoxigraph.BlankNode
    quad_type = pyoxigraph.Quad
    triple_type = pyoxigraph.Triple
    for item in quads:
        subject = item.subject
        nieuw_subject: pyoxigraph.NamedNode | pyoxigraph.BlankNode | pyoxigraph.Triple
        if isinstance(subject, blank_node):
            gevonden_s = labels.get(subject.value)
            if gevonden_s is None:
                gevonden_s = labels[subject.value] = blank_node(f"b{next(teller)}")
            nieuw_subject = gevonden_s
        else:
            nieuw_subject = subject

        object_ = item.object
        nieuw_object: (
            pyoxigraph.NamedNode | pyoxigraph.BlankNode | pyoxigraph.Literal | pyoxigraph.Triple
        )
        if isinstance(object_, blank_node):
            gevonden_o = labels.get(object_.value)
            if gevonden_o is None:
                gevonden_o = labels[object_.value] = blank_node(f"b{next(teller)}")
            nieuw_object = gevonden_o
        else:
            nieuw_object = object_

        if nieuw_subject is subject and nieuw_object is object_:
            yield item
        elif isinstance(item, quad_type):
            yield quad_type(nieuw_subject, item.predicate, nieuw_object, item.graph_name)
        else:
            yield triple_type(nieuw_subject, item.predicate, nieuw_object)


def _begint_met_bom(bron: Path) -> bool:
    """Of `bron` begint met de drie bytes van een UTF-8-BOM (`EF BB BF`).

    Alleen de kop wordt gelezen (drie bytes), zodat de streamende leesweg heel blijft voor
    een gewone bron. Een `OSError` bij het openen wordt hier ingeslikt en als "geen BOM"
    behandeld: een ontbrekende bron of een map hoort langs de bestaande leesweg dezelfde
    `BestandError` te geven als voorheen (`lees_orox` / `_gecontroleerd`), niet hier al een
    andere fout. Zo verandert er niets aan het gedrag van een bron zonder BOM.
    """
    try:
        with open(bron, "rb") as bestand:
            return bestand.read(3) == b"\xef\xbb\xbf"
    except OSError:
        return False


def _gecontroleerd(
    bron: Path, parser: Iterator[pyoxigraph.Quad], fallback_encoding: str | None
) -> Iterator[pyoxigraph.Quad]:
    """Vertaalt parse- en I/O-fouten onderweg naar de juiste `DatasetError`-familie.

    De parser is lui: een syntaxfout halverwege een export van 112 MB komt pas boven bij
    de quad waar hij staat, dus midden in het schrijven. Zonder deze laag zou de afnemer
    daar een pyoxigraph-`SyntaxError` zien in plaats van de `DatasetError` die de package
    voor onleesbare bronnen belooft.

    Eén parsefout krijgt een eigen formulering. Leest de parser rechtstreeks van schijf
    (geen `fallback_encoding`) en draagt de bron niet-UTF-8-bytes, dan struikelt hij over
    de codering en niet over de syntaxis; "geen geldige Turtle" zou de afnemer dan naar
    een niet-bestaande syntaxfout sturen. De leeslaag zegt in dat geval dat er een
    terugvalcodering ontbreekt (`codering.decodeer`), en dat zegt deze laag hem na. Het
    kost geen tweede lezing: het oordeel komt uit de foutmelding van de parser, dus de
    bron blijft streamen.

    Ook `OSError` valt hier, want de streamende parser leest schijf pas terwijl hij
    afgelopen wordt: een map als bron (`IsADirectoryError` op de eerste quad, buiten de
    constructie-vangst van `lees_orox`) of een leesfout halverwege (`EIO` op een
    weggevallen share) hoort dezelfde `BestandError` "kan niet gelezen worden" te geven als
    een ontbrekende bron, en niet als rauwe OSError langs de afnemer te glippen of door de
    schrijf-vangst als "kan niet geschreven worden" verkeerd gelabeld te worden (issue #49).
    De eerste-quad-pull in `lees_orox` drijft deze generator, dus valt óók binnen deze vangst.
    """
    try:
        yield from parser
    except rdfmotor.MOTORFOUTEN as fout:
        if fallback_encoding is None and rdfmotor.is_coderingsfout(fout):
            raise CoderingError(
                f"{bron}: geen geldige UTF-8 ({fout}) en er is geen terugvalcodering opgegeven."
            ) from fout
        raise TurtleError(f"{bron}: geen geldige Turtle ({fout}).") from fout
    except OSError as fout:
        raise BestandError(f"{bron}: bestand kan niet gelezen worden ({fout}).") from fout
