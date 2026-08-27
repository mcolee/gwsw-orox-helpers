"""Een OroX-dataset ruimtelijk verdelen en de delen weer verliesloos herenigen.

`clip_orox` knipt een OroX-export langs een grenslaag (GeoJSON, N vlakken) in N
OroX-bestanden; `merge_orox` maakt daar weer het origineel van. "Weer het origineel"
is hier geen benadering maar de eis: `merge(clip(bron))` parseert naar dezelfde
RDF-graaf als `bron` -- dezelfde triples, dezelfde literalen tot op de byte, dezelfde
blanke-knoopstructuur.

**Eigen pad, net als `schrijven`.** Deze module raakt `dataset.py` en `graaf.py` niet
aan en bouwt geen domeinmodel: ze leest de bron met `schrijven.lees_orox` als
quadstroom en schrijft de delen met `schrijven.schrijf_orox_quads` weg. Gedeeld met de
leeslaag zijn alleen de GML-lezers uit `geometry` -- de knip moet dezelfde coordinaten
zien als de leeslaag -- en de IRI's uit `namen`, want een `hasAspect` die hier anders
gespeld werd dan daar zou de verkeerde helft van de graaf verdelen zonder ergens te
klagen.

## Wat er verdeeld wordt

De graaf valt uiteen in **blokken**: een blok is een benoemd subject met al zijn
triples, plus de blanke knopen die eraan hangen (en die aan die knopen hangen). Blanke
knopen zijn documentgebonden -- zie de moduledocstring van `schrijven` -- dus een blok
gaat altijd in zijn geheel naar een deel en wordt nooit doormidden gesneden. Moet een
blok in meer dan een deel staan (gedeelde structuur, of een leiding die de grens
kruist), dan draagt **elk deel zijn eigen volledige kopie** en ontdubbelt `merge_orox`
op inhoud.

De toewijzing van blokken aan vlakken gaat in vier stappen:

1. **Geometrie zaait.** De geometrie zit niet op het object maar op een
   orientatie-aspect (`gwsw:Punt` / `gwsw:Lijn` met `gwsw:hasValue
   "<gml...>"^^geo:gmlLiteral`, zie `inlezen._geometry`). Een punt gaat naar het vlak
   waarin het valt; een lijn die binnen een vlak blijft ook; een lijn die de grens
   kruist wordt doorgeknipt (zie hieronder). Een vlakgeometrie (`gwsw:Buitengrens`)
   wordt niet geknipt maar op haar representatieve punt toegewezen.
2. **Omhoog.** Elke houder (via `hasPart`/`hasAspect`, in beide schrijfrichtingen)
   krijgt de vereniging van de vlakken van zijn afstammelingen. Zo staat de gedeelde
   structuur -- de wortel, het `Rioleringsgebied`, het stelsel, de straat -- in elk
   deel dat een afstammeling bevat.
3. **Omlaag.** Wat dan nog geen vlak heeft (een onderdeel zonder eigen geometrie: een
   drempel, een hulpstuk, een BOB-kenmerk) erft de vlakken van zijn houders. Zit de
   houder aan beide kanten van de grens -- een doorgeknipte leiding -- dan versmalt
   het **aanhechtingspunt** de keuze: de `gwsw:hasConnection` van het onderdeel wijst
   naar een orientatie die zelf wel een vlak heeft, en dat vlak wint.
4. **Rest.** Wat nergens aan hangt (de ontologiekop) gaat naar elk deel.

Daarna gaat stap 2 nog een keer, zodat de vlakken van een houder altijd die van zijn
onderdelen omvatten -- voor elke `hasPart`/`hasAspect`-rand. Die insluiting is wat elk
deel zelfdekkend maakt: zo'n rand wordt namelijk naar de vlakken van het *onderdeel*
geschreven, en die zitten dan altijd ook in de houder.

**Wat wel over de grens mag wijzen.** Een `gwsw:hasConnection` van een geknipte
leiding naar de put aan de overkant blijft staan. Dat is geen weesverwijzing die op te
lossen valt maar de knip zelf: de put in het andere deel halen zou hem verdubbelen en
de objecttelling per deel onbruikbaar maken. Het is ook precies de verwijzing die na
`merge_orox` weer klopt.

Datzelfde geldt voor een verwijzing *naar* een geknipte geometrieknoop uit een vlak waar
die geen enkel stuk heeft. Voor `hasPart`/`hasAspect` valt zo'n rand hier weg -- die
wordt naar de vlakken van het onderdeel geschreven en staat daar wel -- maar elk ander
predicaat heeft die tweede thuisbasis niet. Zo'n triple blijft dus staan en wijst naar de
*ongeknipte* naam: de naam die na de hereniging weer bestaat. Stil overslaan zou hem uit
de hereniging laten verdwijnen, en dat is precies wat deze module belooft niet te doen.

## De knip en zijn omkering

Een lijn die de grens kruist wordt op de kruispunten in stukken gedeeld. Elk stuk
komt op een eigen knoop te staan -- `<origineel>__knip<k>`, met dezelfde soort en
dezelfde overige triples als het origineel -- en draagt daarnaast zijn knipmerken:

- `knip:herkomst` -- de sleutel van de oorspronkelijke geometrieknoop;
- `knip:volgnummer` en `knip:aantal` -- de plaats in het origineel;
- `knip:ingevoegdEinde` -- of het laatste punt van dit stuk een ingevoegd knippunt is.

`merge_orox` naait ze per herkomst weer aaneen: van elk stuk na het eerste vervalt het
eerste punt (dat herhaalt het laatste punt van het vorige stuk) en van elk stuk met
`knip:ingevoegdEinde` vervalt het laatste punt (dat is het ingevoegde knippunt).

Daarnaast krijgt de **houder** van een geknipte geometrie het merk `knip:geknipt`. Dat
merk leest `merge_orox` niet -- het gaat met de rest van de `knip:`-naamruimte weg -- het
is er voor de afnemer van een deel. Wie een deel op zichzelf leest, ziet daar een leiding
met een geometrie die korter is dan haar lengtekenmerk en die niet meer in haar
eindpunten aankomt; `knip:geknipt` op de orientatie is het antwoord op de vraag of dat
een fout in de data is of het gevolg van de knip. Het staat op de orientatie en niet op
het stuk, want dat is de knoop waar een controle op geometrie en aanhechting kijkt.

**Twee stukken in dezelfde helft.** Een leiding die de grens heen en weer kruist, laat in
een helft meer dan een stuk na. Die stukken sluiten nooit op elkaar aan: tussen twee
stukken van dezelfde helft ligt per constructie een stuk van een andere (`_segmenten`
voegt gelijke buren samen), dus er valt in die helft geen enkele lijn van te maken. Wat
de helft draagt is dan een leiding met een **meerdelige** geometrie, en dat is precies wat
meer dan een `gwsw:Lijn`-aspect onder een orientatie in OroX betekent. De leeslaag leest
het ook zo: `load_dataset` zet `Conduit.multipart` aan (`inlezen._is_multipart`), dus er
komt geen halve leiding uit die zich als een hele voordoet. De stukken een eigen
orientatie geven zou het alternatief zijn, maar dat vraagt om een kopie van het hele
orientatieblok inclusief zijn blanke knopen en om het terugvouwen daarvan bij de
hereniging -- meer risico voor de exactheid dan de meerdelige geometrie kost.

**Waarom dat exact is en geen float-tolerantie nodig heeft.** De stukken worden niet
uit shapely-coordinaten teruggeschreven maar uit de **tekst** van de bron: de
coordinatenlijst van de GML-literaal wordt op tokens gesplitst en de stukken krijgen
plakjes van diezelfde tokens, met alleen het knippunt als nieuw geschreven getal. Wat
er na het snoeien overblijft is dus letterlijk de oorspronkelijke tekst, tot en met de
`233000.00` die een float-omweg als `233000.0` zou hebben teruggegeven. Het issue nam
aan dat het knippunt aan zijn collineariteit herkend moest worden, met een tolerantie
die bros kon blijken; dat is hier niet nodig -- welk punt ingevoegd is staat
opgeschreven. Een tolerantie speelt alleen bij het *zoeken* van de kruispunten
(`_TOLERANTIE`, 1 micrometer): valt een kruispunt op een bestaande vertex, dan wordt
er geen punt ingevoegd en blijft die vertex gewoon staan.

**Niet geknipt** wordt een multi-geometrie, en dat is `geometry.is_multipart_literal`
zijn definitie: meer dan een GML-literaal op de knoop, *of* een literaal die er zelf meer
dan een deel in draagt (een `gml:MultiCurve`, of twee `gml:posList`-en naast elkaar). Van
zo'n literaal leest de shapely-lezer alleen het eerste deel, dus knippen zou een
tekstplakje uit dat eerste deel snijden en de rest ongemoeid in beide delen laten staan.
Niet geknipt wordt verder een lijn met een andere `srsDimension` dan 2 of 3, en een lijn
waarvan de coordinatentekst niet al genormaliseerd is -- dubbele spaties, newlines of
randspaties in de posList. De stukken zijn tekstplakjes en de hereniging zet ze met een
enkele spatie aaneen; van een bron met andere scheiders zouden de getallen wel exact
terugkomen maar de tekst eromheen niet, en dan is `merge(clip(bron))` niet meer
byte-gelijk aan `bron`. Zo'n knoop gaat ongeknipt naar elk vlak dat hij raakt (van een
multi-geometrie: elk vlak dat het gelezen deel raakt); de hereniging blijft daarmee
exact, alleen staat de hele geometrie dan in beide delen.

## Blanke knopen krijgen een vaste naam

pyoxigraph verzint bij elke lezing nieuwe namen voor blanke knopen -- twee lezingen
van hetzelfde bestand leveren andere labels op. De clip leest de bron een keer per
vlak en moet in elk deel dezelfde knoop dezelfde naam geven, anders is er na de
hereniging geen brug meer tussen de delen. Daarom krijgt elke blanke knoop hier een
naam naar zijn plaats in de stroom (`b0`, `b1`, ...); de leesvolgorde van een bestand
ligt vast, dus die naam is bij elke lezing dezelfde. `merge_orox` leest de namen weer
uit de delen terug en gebruikt ze als identiteit -- dat pyoxigraph labels van blanke
knopen bij het schrijven en lezen ongemoeid laat, is een eigenschap waar deze module
op leunt en die `tests/test_clip.py` apart vastlegt.
"""

from __future__ import annotations

import itertools
import json
import re
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import pyoxigraph
from shapely.geometry import LineString, Point
from shapely.geometry import shape as _vorm
from shapely.geometry.base import BaseGeometry
from shapely.prepared import PreparedGeometry, prep

from gwsw_orox_helpers.errors import DatasetError
from gwsw_orox_helpers.geometry import (
    GeometryError,
    is_multipart_literal,
    parse_gml,
    parse_gml_z,
)
from gwsw_orox_helpers.namen import (
    GML_LITERAL,
    HAS_ASPECT,
    HAS_CONNECTION,
    HAS_PART,
    HAS_VALUE,
    IS_ASPECT_OF,
    IS_PART_OF,
    XSD,
)
from gwsw_orox_helpers.schrijven import lees_orox, schrijf_orox_quads

# De eigen naamruimte voor de knipmerken. Ze staan alleen in de geknipte delen; `merge_orox`
# gooit elke triple met een predicaat uit deze naamruimte weg.
KNIP: Final = "https://github.com/mcolee/gwsw-orox-helpers/ns/clip#"
KNIP_PREFIX: Final = "knip"

_HAS_VALUE_KNOOP: Final = pyoxigraph.NamedNode(HAS_VALUE)
_GML_TYPE: Final = pyoxigraph.NamedNode(GML_LITERAL)
_HERKOMST: Final = pyoxigraph.NamedNode(f"{KNIP}herkomst")
_VOLGNUMMER: Final = pyoxigraph.NamedNode(f"{KNIP}volgnummer")
_AANTAL: Final = pyoxigraph.NamedNode(f"{KNIP}aantal")
_INGEVOEGD_EINDE: Final = pyoxigraph.NamedNode(f"{KNIP}ingevoegdEinde")
_GEKNIPT: Final = pyoxigraph.NamedNode(f"{KNIP}geknipt")
_INTEGER: Final = pyoxigraph.NamedNode(f"{XSD}integer")
_BOOLEAN: Final = pyoxigraph.NamedNode(f"{XSD}boolean")
_WAAR: Final = pyoxigraph.Literal("true", datatype=_BOOLEAN)

# De inhoud van de gml:pos of gml:posList, met de omhulsels eromheen. Alleen de middelste
# groep wordt vervangen; al het andere in de literaal blijft letterlijk staan (srsName,
# srsDimension, de soort geometrie).
_COORDINATEN: Final = re.compile(r"(<gml:(?:pos|posList)\b[^>]*>)([^<]*)(</gml:(?:pos|posList)>)")

# De namen die de clip zelf mint, hangen deze staart achter de sleutel van de bron. Een bron
# die zulke namen al draagt zou na de hereniging met zichzelf samenvallen; dat wordt geweigerd.
_KNIPSTAART: Final = re.compile(r"__knip\d+\Z")

# Afstandstolerantie langs een lijn, in meters. Valt een kruispunt hierbinnen op een
# bestaande vertex, dan wordt er geen punt ingevoegd; valt het op het begin of het eind
# van de lijn, dan is er niets te knippen. RD-coordinaten liggen rond 2e5 m en float64
# houdt daar zo'n 1e-11 m over, dus 1e-6 m is ruim en nog altijd onzichtbaar klein.
_TOLERANTIE: Final = 1e-6

# Het aantal decimalen waarmee een ingevoegd knippunt geschreven wordt. Alleen zichtbaar in
# de delen: bij de hereniging vervalt het punt, dus het raakt de round-trip niet.
_KNIPPUNT_DECIMALEN: Final = 3


@dataclass(frozen=True)
class _Stuk:
    """Een stuk van een doorgeknipte lijn, klaar om als GML weggeschreven te worden."""

    deel: int
    volgnummer: int
    coordinaten: str
    ingevoegd_einde: bool


@dataclass
class _Plan:
    """Wat er per vlak weggeschreven moet worden; de uitkomst van de analyseronde."""

    namen: tuple[str, ...]
    # Blok-sleutel -> bitmasker van vlakken. Een blok is een benoemd subject met de blanke
    # knopen die eraan hangen; `eigenaar` wijst elke blanke knoop naar zijn blok.
    toewijzing: dict[str, int] = field(default_factory=dict)
    eigenaar: dict[str, str] = field(default_factory=dict)
    # Sleutel van een geometrieknoop -> de stukken waarin zijn lijn uiteenvalt.
    stukken: dict[str, tuple[_Stuk, ...]] = field(default_factory=dict)
    # Blok-sleutel van een houder van een geknipte geometrie -> bitmasker; draagt `knip:geknipt`.
    geknipte_houders: dict[str, int] = field(default_factory=dict)

    def blok(self, sleutel: str) -> str:
        """Het blok waar deze term in valt: hijzelf, of het blok van zijn blanke knoop."""
        return self.eigenaar.get(sleutel, sleutel)

    def masker(self, sleutel: str) -> int:
        """Het bitmasker van vlakken waar het blok van deze term in staat."""
        return self.toewijzing.get(self.blok(sleutel), 0)


def clip_orox(
    bron: Path,
    grenzen: Path,
    uitmap: Path,
    *,
    sleutel: str,
    fallback_encoding: str | None = None,
) -> list[Path]:
    """Knipt de OroX-export `bron` langs `grenzen` in een bestand per vlak.

    `grenzen` is een GeoJSON-FeatureCollection met N vlakken in EPSG:28992 -- hetzelfde
    stelsel als de GML-literalen in de bron, die het impliciet laten (RD, geen srsName
    dat er iets anders van maakt). Dat wordt aangenomen en niet gevalideerd. `sleutel`
    is de property waaruit de bestandsnaam volgt (`gemeentenaam`, `gemeentecode`, ...);
    de waarden moeten onderling verschillen, anders zouden twee vlakken hetzelfde
    bestand willen schrijven.

    Levert de N geschreven paden op, in de volgorde van de vlakken in `grenzen`. Elk
    bestand is een geldige OroX-TTL met de prefixen van de bron plus `knip:` voor de
    knipmerken; samen dragen ze elke triple van de bron minstens een keer, zodat
    `merge_orox` de bron weer oplevert.

    `fallback_encoding` betekent hetzelfde als in `load_dataset` en `schrijf_orox`: de
    BrutIS-export van De Wolden en Hoogeveen is geen zuivere UTF-8 en is zonder
    terugval niet te lezen. De uitvoer is hoe dan ook UTF-8.

    De bron wordt N+1 keer gelezen: een keer om te bepalen wat waarheen gaat, en daarna
    een keer per vlak om te schrijven. Dat is bewust: de toewijzing is pas rond als de
    hele graaf gezien is, en de delen daarna uit een gefilterde stroom schrijven kost
    geen geheugen voor de triples zelf.
    """
    vlakken = _lees_grenzen(grenzen, sleutel)
    plan = _maak_plan(bron, vlakken, fallback_encoding)

    uitmap = Path(uitmap)
    paden: list[Path] = []
    for index, naam in enumerate(plan.namen):
        doel = uitmap / f"{bron.stem}__{_bestandsnaam(naam)}.ttl"
        geopend = lees_orox(bron, fallback_encoding)
        prefixen = {**geopend.prefixen, KNIP_PREFIX: KNIP}
        schrijf_orox_quads(_deelstroom(geopend.quads, plan, index), doel, prefixen=prefixen)
        paden.append(doel)
    return paden


def merge_orox(delen: list[Path], doel: Path) -> None:
    """Voegt de delen van `clip_orox` weer samen tot een OroX-TTL op `doel`.

    Drie dingen tegelijk: de vereniging van de triples met ontdubbeling op inhoud (een
    blok dat in meer dan een deel staat, staat er in elk deel volledig in en hoort er
    hier een keer uit te komen), het aaneen naaien van de geknipte lijnstukken per
    herkomst, en het weggooien van de knipmerken. Wat eruit komt is de bron: dezelfde
    triples, dezelfde literalen, dezelfde blanke-knoopstructuur.

    De delen moeten samen compleet zijn -- van elke geknipte lijn moeten alle stukken
    er zijn. Ontbreekt er een, dan is de lijn niet te herstellen en volgt een
    `DatasetError` in plaats van een stilzwijgend kortere geometrie.
    """
    if not delen:
        raise DatasetError("merge_orox: geen delen opgegeven; er valt niets samen te voegen.")

    scan = _scan_delen(delen)
    schrijf_orox_quads(_samengevoegd(delen, scan), doel, prefixen=scan.prefixen)


# --------------------------------------------------------------------------------------
# De grenslaag
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Vlak:
    """Een vlak uit de grenslaag: zijn naam, zijn meetkunde en de voorbereide vorm."""

    naam: str
    meetkunde: BaseGeometry
    voorbereid: PreparedGeometry


def _lees_grenzen(grenzen: Path, sleutel: str) -> tuple[_Vlak, ...]:
    """Leest de GeoJSON-grenslaag als vlakken, in bestandsvolgorde."""
    try:
        rauw = json.loads(Path(grenzen).read_text(encoding="utf-8"))
    except OSError as fout:
        raise DatasetError(f"{grenzen}: grenslaag kan niet gelezen worden ({fout}).") from fout
    except (json.JSONDecodeError, UnicodeDecodeError) as fout:
        raise DatasetError(f"{grenzen}: geen leesbare GeoJSON ({fout}).") from fout

    kenmerken = rauw.get("features") if isinstance(rauw, dict) else None
    if not kenmerken:
        raise DatasetError(f"{grenzen}: geen features in de grenslaag; er valt niets te knippen.")

    vlakken: list[_Vlak] = []
    gezien: set[str] = set()
    for kenmerk in kenmerken:
        eigenschappen = kenmerk.get("properties") or {}
        if sleutel not in eigenschappen or eigenschappen[sleutel] is None:
            raise DatasetError(
                f"{grenzen}: een feature draagt geen {sleutel!r}; die property bepaalt de "
                f"uitvoernaam en moet op elk vlak staan."
            )
        naam = str(eigenschappen[sleutel])
        if naam in gezien:
            raise DatasetError(
                f"{grenzen}: {sleutel!r} is {naam!r} op meer dan een vlak; twee vlakken zouden "
                f"dan hetzelfde bestand schrijven."
            )
        gezien.add(naam)

        try:
            meetkunde = _vorm(kenmerk["geometry"])
        except (KeyError, TypeError, ValueError, AttributeError) as fout:
            raise DatasetError(
                f"{grenzen}: {naam!r} heeft geen leesbare geometrie ({fout})."
            ) from fout
        if meetkunde.geom_type not in ("Polygon", "MultiPolygon") or meetkunde.is_empty:
            raise DatasetError(
                f"{grenzen}: {naam!r} is een {meetkunde.geom_type} en geen (multi)vlak; "
                f"een clip verdeelt langs vlakken."
            )
        vlakken.append(_Vlak(naam=naam, meetkunde=meetkunde, voorbereid=prep(meetkunde)))
    return tuple(vlakken)


def _bestandsnaam(naam: str) -> str:
    """De naam van een vlak als bestandsnaamdeel; alles wat geen naam mag zijn wordt `_`."""
    veilig = re.sub(r"[^A-Za-z0-9._-]+", "_", naam).strip("._-")
    return veilig or "vlak"


# --------------------------------------------------------------------------------------
# De analyseronde: wie hoort waar
# --------------------------------------------------------------------------------------


def _sleutel(term: object, namen: dict[str, str], teller: Iterator[int]) -> str | None:
    """De sleutel van een term: zijn IRI, of `_:b<n>` voor een blanke knoop.

    De nummering volgt de stroomvolgorde en is daarmee bij elke lezing van hetzelfde
    bestand dezelfde -- anders dan de namen die pyoxigraph zelf verzint.
    """
    if isinstance(term, pyoxigraph.NamedNode):
        return term.value
    if isinstance(term, pyoxigraph.BlankNode):
        naam = namen.get(term.value)
        if naam is None:
            naam = f"b{next(teller)}"
            namen[term.value] = naam
        return f"_:{naam}"
    return None


def _genummerd(
    quads: Iterable[pyoxigraph.Quad],
) -> Iterator[tuple[pyoxigraph.Quad, str, str | None]]:
    """De quadstroom met de sleutel van subject en object erbij.

    Subject en object worden altijd in die volgorde opgevraagd, zodat de nummering van
    de blanke knopen in elke ronde over hetzelfde bestand gelijk uitvalt.
    """
    namen: dict[str, str] = {}
    teller = itertools.count()
    for quad in quads:
        onderwerp = _sleutel(quad.subject, namen, teller)
        assert onderwerp is not None  # een subject is nooit een literaal
        yield quad, onderwerp, _sleutel(quad.object, namen, teller)


def _maak_plan(bron: Path, vlakken: tuple[_Vlak, ...], fallback_encoding: str | None) -> _Plan:
    """Leest de bron een keer en bepaalt per blok naar welke vlakken het gaat."""
    plan = _Plan(namen=tuple(vlak.naam for vlak in vlakken))
    ouder_van: dict[str, str] = {}
    randen: list[tuple[str, str]] = []
    verbindingen: list[tuple[str, str]] = []
    literalen: dict[str, list[str]] = {}
    subjecten: set[str] = set()

    for quad, onderwerp, voorwerp in _genummerd(lees_orox(bron, fallback_encoding).quads):
        subjecten.add(onderwerp)
        if voorwerp is not None and voorwerp.startswith("_:"):
            ouder_van.setdefault(voorwerp, onderwerp)
        predicaat = quad.predicate.value
        if voorwerp is not None:
            if predicaat in (HAS_ASPECT, HAS_PART):
                randen.append((onderwerp, voorwerp))
            elif predicaat in (IS_ASPECT_OF, IS_PART_OF):
                randen.append((voorwerp, onderwerp))
            elif predicaat == HAS_CONNECTION:
                verbindingen.append((onderwerp, voorwerp))
        elif (
            predicaat == HAS_VALUE
            and isinstance(quad.object, pyoxigraph.Literal)
            and quad.object.datatype.value == GML_LITERAL
        ):
            literalen.setdefault(onderwerp, []).append(quad.object.value)

    for naam in subjecten:
        if "__knip" in naam and _KNIPSTAART.search(naam):
            raise DatasetError(
                f"{bron}: {naam!r} eindigt op de staart die de clip zelf voor geknipte stukken "
                f"gebruikt; zo'n bron is na de hereniging niet van een geknipte te onderscheiden."
            )

    # De blokken kennen elkaar pas als bekend is welke blanke knoop bij welk blok hoort.
    plan.eigenaar = _eigenaren(ouder_van)
    blokken = {plan.blok(naam) for naam in subjecten}
    ouders = _verwantschap(randen, plan)
    _zaai(plan, literalen, vlakken)
    _omhoog(plan, ouders)
    _omlaag(plan, blokken, ouders, _verbindingsgraaf(verbindingen, plan), len(vlakken))
    _omhoog(plan, ouders)
    _merk_houders(plan, randen)
    return plan


def _eigenaren(ouder_van: dict[str, str]) -> dict[str, str]:
    """Per blanke knoop het benoemde blok waar hij in valt.

    Loopt de keten van houders omhoog tot een benoemd subject. Een blanke knoop waar
    niets naar wijst is zijn eigen blok; een keten die in zichzelf terugloopt (een
    blanke knoop die zijn eigen voorouder is) eindigt bij de knoop waar de lus sluit.
    """
    wortels: dict[str, str] = {}
    for knoop in ouder_van:
        pad: list[str] = []
        huidig = knoop
        while huidig.startswith("_:") and huidig not in wortels:
            if huidig in pad:  # lus: neem de knoop zelf als blok
                break
            pad.append(huidig)
            volgende = ouder_van.get(huidig)
            if volgende is None:
                break
            huidig = volgende
        wortel = wortels.get(huidig, huidig)
        for stap in pad:
            wortels[stap] = wortel
    return wortels


def _verwantschap(randen: list[tuple[str, str]], plan: _Plan) -> dict[str, set[str]]:
    """Per blok de blokken die het als onderdeel of aspect dragen.

    Randen binnen een blok (een blanke knoop aan zijn eigen houder) vallen weg: die
    gaan per definitie samen dezelfde kant op.
    """
    ouders: dict[str, set[str]] = {}
    for houder, onderdeel in randen:
        boven, onder = plan.blok(houder), plan.blok(onderdeel)
        if boven == onder:
            continue
        ouders.setdefault(onder, set()).add(boven)
    return ouders


def _verbindingsgraaf(verbindingen: list[tuple[str, str]], plan: _Plan) -> dict[str, set[str]]:
    """Per blok de blokken waar het via `hasConnection` aan vastzit, beide richtingen op."""
    graaf: dict[str, set[str]] = {}
    for links, rechts in verbindingen:
        een, twee = plan.blok(links), plan.blok(rechts)
        if een == twee:
            continue
        graaf.setdefault(een, set()).add(twee)
        graaf.setdefault(twee, set()).add(een)
    return graaf


def _zaai(plan: _Plan, literalen: dict[str, list[str]], vlakken: tuple[_Vlak, ...]) -> None:
    """Geeft elk blok met een geometrie zijn vlakken, en knipt de lijnen die de grens kruisen."""
    for knoop, waarden in literalen.items():
        masker = 0
        if len(waarden) == 1 and not is_multipart_literal(waarden[0]):
            masker, stukken = _plaats(waarden[0], vlakken)
            if stukken is not None:
                plan.stukken[knoop] = stukken
        else:
            # Een multi-geometrie wordt niet geknipt: hij gaat heel naar elk vlak dat hij
            # raakt. Meer dan een literaal op de knoop telt daarvoor, en een literaal die er
            # zelf meer dan een deel in draagt (`gml:MultiCurve`, of twee posLists naast
            # elkaar) net zo goed -- de tellingen van de literalen alleen lieten die tweede
            # vorm ongemerkt door de knip lopen.
            for waarde in waarden:
                masker |= _plaats(waarde, vlakken, knip=False)[0]
        if masker:
            blok = plan.blok(knoop)
            plan.toewijzing[blok] = plan.toewijzing.get(blok, 0) | masker


def _omhoog(plan: _Plan, ouders: dict[str, set[str]]) -> None:
    """Geeft elke houder de vereniging van de vlakken van zijn afstammelingen."""
    werk = list(plan.toewijzing)
    while werk:
        volgende: list[str] = []
        for knoop in werk:
            masker = plan.toewijzing[knoop]
            for ouder in ouders.get(knoop, ()):
                oud = plan.toewijzing.get(ouder, 0)
                if oud | masker != oud:
                    plan.toewijzing[ouder] = oud | masker
                    volgende.append(ouder)
        werk = volgende


def _omlaag(
    plan: _Plan,
    blokken: set[str],
    ouders: dict[str, set[str]],
    verbindingen: dict[str, set[str]],
    aantal_vlakken: int,
) -> None:
    """Laat wat geen geometrie heeft de vlakken van zijn houder erven.

    Zit die houder aan beide kanten van een knip, dan versmalt het aanhechtingspunt de
    keuze: de `hasConnection` van het onderdeel wijst naar een orientatie die zelf wel
    een vlak heeft. Blijft er dan niets over dat binnen de houder past, dan wint de
    houder -- een onderdeel hoort nooit buiten zijn houder te vallen, want dan zou de
    `hasPart`-rand ertussen nergens meer geschreven kunnen worden.
    """
    alles = (1 << aantal_vlakken) - 1
    onbekend = {knoop for knoop in blokken if knoop not in plan.toewijzing}
    while True:
        # Per ronde wordt eerst alles uitgerekend en pas daarna toegekend. Een blok dat
        # binnen dezelfde ronde van een ander onbekend blok zou erven, wacht zo tot de
        # volgende ronde -- en dat is wat de uitkomst onafhankelijk maakt van de volgorde
        # waarin een verzameling toevallig doorlopen wordt. Zonder dat zou dezelfde bron
        # twee keer geknipt twee verschillende verdelingen kunnen opleveren.
        ronde: dict[str, int] = {}
        for knoop in onbekend:
            masker = 0
            for ouder in ouders.get(knoop, ()):
                masker |= plan.toewijzing.get(ouder, 0)
            if not masker:
                continue
            if masker.bit_count() > 1:
                aanhechting = 0
                for buur in verbindingen.get(knoop, ()):
                    aanhechting |= plan.toewijzing.get(buur, 0)
                if aanhechting & masker:
                    masker &= aanhechting
            ronde[knoop] = masker
        if not ronde:
            break
        plan.toewijzing.update(ronde)
        onbekend.difference_update(ronde)

    # Wat nergens aan hangt -- de ontologiekop -- hoort in elk deel te staan.
    for knoop in onbekend:
        plan.toewijzing[knoop] = alles


def _merk_houders(plan: _Plan, randen: list[tuple[str, str]]) -> None:
    """Onthoudt welke houders van een geknipte geometrie het merk `knip:geknipt` krijgen."""
    for houder, onderdeel in randen:
        if onderdeel in plan.stukken:
            blok = plan.blok(houder)
            masker = plan.toewijzing.get(blok, 0)
            if masker:
                plan.geknipte_houders[blok] = masker


# --------------------------------------------------------------------------------------
# Geometrie: plaatsen en knippen
# --------------------------------------------------------------------------------------


def _plaats(
    literal: str, vlakken: tuple[_Vlak, ...], *, knip: bool = True
) -> tuple[int, tuple[_Stuk, ...] | None]:
    """Het bitmasker van vlakken voor deze GML-literaal, en zo nodig de knipstukken."""
    try:
        meetkunde = parse_gml(literal)
    except GeometryError:
        # Een onleesbare geometrie zaait niets; het blok erft dan van zijn houder. De
        # leeslaag meldt zo'n literaal in `GwswDataset.geometry_errors`; de clip hoeft er
        # niet nog een tweede keer over te vallen.
        return 0, None
    if meetkunde.is_empty:
        return 0, None
    if isinstance(meetkunde, LineString) and len(meetkunde.coords) > 1:
        if knip:
            return _knip_lijn(literal, meetkunde, vlakken)
        # Ongeknipt gaat een lijn heel naar elk vlak dat hij raakt; een representatief punt
        # zou hem in een van beide vlakken laten verdwijnen terwijl hij in allebei ligt.
        return _heel(meetkunde, vlakken), None
    return 1 << _vlak_van(meetkunde.representative_point(), vlakken), None


def _vlak_van(punt: Point, vlakken: tuple[_Vlak, ...]) -> int:
    """Het vlak waarin dit punt valt; anders het dichtstbijzijnde vlak.

    De terugval op het dichtstbijzijnde vlak is er zodat er nooit een object buiten de
    boot valt: een grenslaag dekt zelden precies alles wat een export bevat, en een
    object dat nergens heen kan zou bij de hereniging ontbreken.
    """
    for index, vlak in enumerate(vlakken):
        if vlak.voorbereid.covers(punt):
            return index
    return min(range(len(vlakken)), key=lambda index: vlakken[index].meetkunde.distance(punt))


def _knip_lijn(
    literal: str, lijn: LineString, vlakken: tuple[_Vlak, ...]
) -> tuple[int, tuple[_Stuk, ...] | None]:
    """Verdeelt een lijn over de vlakken; knipt hem als hij de grens kruist."""
    for index, vlak in enumerate(vlakken):
        if vlak.voorbereid.covers(lijn):
            return 1 << index, None

    tokens = _tokens(literal)
    punten = list(lijn.coords)
    dimensie = len(tokens) // len(punten) if punten else 0
    if dimensie not in (2, 3) or dimensie * len(punten) != len(tokens):
        # Zonder een sluitende tokenverdeling valt er geen tekstplakje te knippen; dan gaat
        # de hele lijn naar elk vlak dat hij raakt.
        return _heel(lijn, vlakken), None
    if " ".join(tokens) != _ruwe_coordinaten(literal):
        # De hereniging zet de tokens met een enkele spatie aaneen. Draagt de bron andere
        # scheiders -- dubbele spaties, newlines, randspaties -- dan komen de getallen wel
        # exact terug maar de tekst eromheen niet, en dan is `merge(clip(bron))` niet meer
        # byte-gelijk aan de bron. Zulke tekst wordt niet geknipt maar heel doorgegeven.
        return _heel(lijn, vlakken), None

    lengte = lijn.length
    afstanden = _vertexafstanden(punten)
    snedes = sorted(_snijafstanden(punten, afstanden, vlakken, lengte))
    segmenten = _segmenten(lijn, [0.0, *snedes, lengte], vlakken)
    if len(segmenten) < 2:
        return (1 << segmenten[0][0]) if segmenten else _heel(lijn, vlakken), None

    z_waarden = parse_gml_z(literal)
    stukken: list[_Stuk] = []
    masker = 0
    for volgnummer, (deel, begin, eind) in enumerate(segmenten):
        op_begin = _vertex_op(afstanden, begin)
        op_eind = _vertex_op(afstanden, eind)
        eerste = op_begin if op_begin is not None else _eerste_na(afstanden, begin)
        laatste = op_eind if op_eind is not None else _laatste_voor(afstanden, eind)
        # De uiteinden van de lijn liggen vast: het eerste stuk begint op de eerste vertex
        # en het laatste eindigt op de laatste. Dat is geen vanzelfsprekendheid zolang
        # `_vertex_op` de *eerste* vertex binnen de tolerantie aanwijst: valt het laatste
        # segment van de lijn korter uit dan een micrometer -- een herhaald eindpunt, en
        # dat komt in exports voor -- dan wijst hij naar de een-na-laatste en zou de
        # laatste vertex buiten elk stuk vallen. De hereniging leverde dan een kortere
        # geometrie op zonder ergens te klagen.
        if volgnummer == 0:
            eerste = 0
        if volgnummer == len(segmenten) - 1:
            laatste = len(afstanden) - 1

        rij: list[str] = []
        if volgnummer > 0 and op_begin is None:
            rij.extend(_knippunt(lijn, afstanden, z_waarden, dimensie, begin))
        for index in range(eerste, laatste + 1):
            rij.extend(tokens[index * dimensie : (index + 1) * dimensie])
        ingevoegd = volgnummer < len(segmenten) - 1 and op_eind is None
        if ingevoegd:
            rij.extend(_knippunt(lijn, afstanden, z_waarden, dimensie, eind))

        stukken.append(
            _Stuk(
                deel=deel,
                volgnummer=volgnummer,
                coordinaten=" ".join(rij),
                ingevoegd_einde=ingevoegd,
            )
        )
        masker |= 1 << deel
    return masker, tuple(stukken)


def _heel(lijn: LineString, vlakken: tuple[_Vlak, ...]) -> int:
    """Het masker van alle vlakken die deze lijn raakt; minstens een."""
    masker = 0
    for index, vlak in enumerate(vlakken):
        if vlak.voorbereid.intersects(lijn):
            masker |= 1 << index
    return masker or 1 << _vlak_van(lijn.representative_point(), vlakken)


def _tokens(literal: str) -> list[str]:
    """De losse coordinaatgetallen van de literaal, als tekst en niet als float."""
    return _ruwe_coordinaten(literal).split()


def _ruwe_coordinaten(literal: str) -> str:
    """De inhoud van de gml:pos of gml:posList, letterlijk en met zijn eigen scheiders."""
    treffer = _COORDINATEN.search(literal)
    return treffer[2] if treffer is not None else ""


def _vertexafstanden(punten: Sequence[tuple[float, ...]]) -> list[float]:
    """De afstand langs de lijn tot elke vertex."""
    afstanden = [0.0]
    for vorige, volgende in itertools.pairwise(punten):
        stap = Point(vorige[0], vorige[1]).distance(Point(volgende[0], volgende[1]))
        afstanden.append(afstanden[-1] + stap)
    return afstanden


def _snijafstanden(
    punten: Sequence[tuple[float, ...]],
    afstanden: list[float],
    vlakken: tuple[_Vlak, ...],
    lengte: float,
) -> set[float]:
    """De afstanden langs de lijn waar hij een vlakgrens kruist.

    Segment voor segment, en niet met `LineString.project` op de hele lijn: die geeft
    van een punt de *dichtstbijzijnde* plaats op de lijn, en een leiding die over
    zichzelf terugloopt raakt dezelfde grens dan twee keer op dezelfde plaats. De ene
    kruising zou dan verdwijnen en het stuk ertussen aan de verkeerde kant belanden.
    Binnen een recht segment is `project` wel eenduidig.
    """
    gevonden: set[float] = set()
    for index, (vorige, volgende) in enumerate(itertools.pairwise(punten)):
        segment = LineString([vorige[:2], volgende[:2]])
        if segment.length <= _TOLERANTIE:
            continue
        for vlak in vlakken:
            for punt in _puntjes(segment.intersection(vlak.meetkunde.boundary)):
                afstand = afstanden[index] + segment.project(punt)
                if _TOLERANTIE < afstand < lengte - _TOLERANTIE:
                    gevonden.add(afstand)
    return gevonden


def _puntjes(meetkunde: BaseGeometry) -> Iterator[Point]:
    """De losse punten uit een doorsnede: punten zelf, en de einden van lijnstukken."""
    if meetkunde.is_empty:
        return
    if isinstance(meetkunde, Point):
        yield meetkunde
    elif hasattr(meetkunde, "geoms"):
        for deel in meetkunde.geoms:
            yield from _puntjes(deel)
    elif isinstance(meetkunde, LineString):
        punten = list(meetkunde.coords)
        yield Point(punten[0])
        yield Point(punten[-1])


def _segmenten(
    lijn: LineString, grenzen: list[float], vlakken: tuple[_Vlak, ...]
) -> list[tuple[int, float, float]]:
    """De stukken tussen de kruispunten, elk met zijn vlak; gelijke buren worden samengevoegd."""
    segmenten: list[tuple[int, float, float]] = []
    for begin, eind in itertools.pairwise(grenzen):
        if eind - begin <= _TOLERANTIE:
            continue
        deel = _vlak_van(lijn.interpolate((begin + eind) / 2), vlakken)
        if segmenten and segmenten[-1][0] == deel:
            segmenten[-1] = (deel, segmenten[-1][1], eind)
        else:
            segmenten.append((deel, begin, eind))
    return segmenten


def _vertex_op(afstanden: list[float], afstand: float) -> int | None:
    """De vertex die op deze afstand ligt, als er een binnen de tolerantie ligt."""
    for index, waarde in enumerate(afstanden):
        if abs(waarde - afstand) <= _TOLERANTIE:
            return index
    return None


def _eerste_na(afstanden: list[float], afstand: float) -> int:
    """De eerste vertex voorbij deze afstand."""
    for index, waarde in enumerate(afstanden):
        if waarde > afstand + _TOLERANTIE:
            return index
    return len(afstanden) - 1


def _laatste_voor(afstanden: list[float], afstand: float) -> int:
    """De laatste vertex voor deze afstand."""
    keuze = 0
    for index, waarde in enumerate(afstanden):
        if waarde < afstand - _TOLERANTIE:
            keuze = index
    return keuze


def _knippunt(
    lijn: LineString,
    afstanden: list[float],
    z_waarden: list[float | None],
    dimensie: int,
    afstand: float,
) -> list[str]:
    """Het ingevoegde knippunt als coordinaattokens, met een lineair gewogen z."""
    punt = lijn.interpolate(afstand)
    rij = [f"{punt.x:.{_KNIPPUNT_DECIMALEN}f}", f"{punt.y:.{_KNIPPUNT_DECIMALEN}f}"]
    if dimensie == 3:
        rij.append(f"{_hoogte(afstanden, z_waarden, afstand):.{_KNIPPUNT_DECIMALEN}f}")
    return rij


def _hoogte(afstanden: list[float], z_waarden: list[float | None], afstand: float) -> float:
    """De z op deze afstand, lineair tussen de twee vertices eromheen.

    Beide uitwegen hieronder horen niet bereikbaar te zijn: er wordt alleen om een z
    gevraagd als de literaal drie getallen per punt draagt, en dan geeft `parse_gml_z`
    voor elk punt een getal; en een knippunt ligt per constructie binnen de lijn, dus er
    is altijd een segment met lengte omheen. Gaat een van die aannames toch niet op, dan
    is een verzonnen hoogte het slechtste antwoord: `0.00` leest als NAP-nul en niet als
    "onbekend", en dat staat dan in het geknipte deel alsof het ingewonnen is.
    """
    for index in range(len(afstanden) - 1):
        begin, eind = afstanden[index], afstanden[index + 1]
        if begin - _TOLERANTIE <= afstand <= eind + _TOLERANTIE and eind > begin:
            onder, boven = z_waarden[index], z_waarden[index + 1]
            if onder is None or boven is None:
                raise DatasetError(
                    f"het knippunt op {afstand} m draagt drie getallen per punt maar de "
                    f"literaal geeft geen hoogte voor de vertices eromheen; er valt dan "
                    f"geen z voor het knippunt te bepalen."
                )
            deel = (afstand - begin) / (eind - begin)
            return onder + deel * (boven - onder)
    raise DatasetError(
        f"het knippunt op {afstand} m ligt niet op een segment met lengte; er valt dan "
        f"geen hoogte tussen twee vertices in te wegen."
    )


def _met_coordinaten(literal: str, coordinaten: str) -> str:
    """Dezelfde GML-literaal, met een andere coordinatenlijst erin."""
    return _COORDINATEN.sub(lambda treffer: treffer[1] + coordinaten + treffer[3], literal, count=1)


# --------------------------------------------------------------------------------------
# Schrijven: de stroom per deel
# --------------------------------------------------------------------------------------


def _term(sleutel: str) -> pyoxigraph.NamedNode | pyoxigraph.BlankNode:
    """De term achter een sleutel: een blanke knoop bij `_:`, anders een IRI."""
    if sleutel.startswith("_:"):
        return pyoxigraph.BlankNode(sleutel[2:])
    return pyoxigraph.NamedNode(sleutel)


def _stukterm(sleutel: str, volgnummer: int) -> pyoxigraph.NamedNode | pyoxigraph.BlankNode:
    """De knoop waar het `volgnummer`-de stuk van deze geometrie op komt te staan."""
    return _term(f"{sleutel}__knip{volgnummer}")


def _deelstroom(
    quads: Iterable[pyoxigraph.Quad], plan: _Plan, deel: int
) -> Iterator[pyoxigraph.Triple]:
    """De triples die naar dit deel gaan, uit de quadstroom van de bron."""
    bit = 1 << deel
    for blok, masker in plan.geknipte_houders.items():
        if masker & bit:
            yield pyoxigraph.Triple(_term(blok), _GEKNIPT, _WAAR)

    for quad, onderwerp, voorwerp in _genummerd(quads):
        masker = plan.masker(onderwerp)
        if not masker & bit:
            continue
        predicaat = quad.predicate.value
        if voorwerp is not None and predicaat in (HAS_ASPECT, HAS_PART, IS_ASPECT_OF, IS_PART_OF):
            # De rand tussen houder en onderdeel gaat naar de vlakken van het onderdeel; de
            # houder staat daar altijd ook, dus geen van beide einden komt los te hangen.
            ander = plan.masker(voorwerp)
            if ander and not ander & bit:
                continue

        # Blanke knopen gaan met hun vaste naam de deur uit; zie de moduledocstring.
        subject_uit: pyoxigraph.NamedNode | pyoxigraph.BlankNode = (
            quad.subject if isinstance(quad.subject, pyoxigraph.NamedNode) else _term(onderwerp)
        )
        object_uit = (
            _term(voorwerp)
            if voorwerp is not None and isinstance(quad.object, pyoxigraph.BlankNode)
            else quad.object
        )
        gml = _gml_waarde(quad.object)

        onderwerpen = _stuktermen(plan, onderwerp, deel)
        voorwerpen = _stuktermen(plan, voorwerp, deel) if voorwerp is not None else None
        if onderwerpen == []:
            # Een geknipte geometrieknoop zonder stuk in dit deel. Dat kan: een blok kan in
            # een vlak staan om een andere geometrie (de orientatie draagt naast de lijn ook
            # een punt) terwijl de lijn daar geen stuk heeft. Dan hoort hier niet zijn hele
            # ongeknipte geometrie te staan.
            continue
        if voorwerpen == []:
            if predicaat in (HAS_ASPECT, HAS_PART, IS_ASPECT_OF, IS_PART_OF):
                # Een houder/onderdeel-rand naar een geknipte geometrie zonder stuk hier:
                # niet schrijven, anders zou er een naam in dit deel hangen waar niets bij
                # staat. Kwijt raakt de triple er niet van, want de rand wordt naar de
                # vlakken van het onderdeel geschreven en daar staat wel een stuk.
                continue
            # Elk ander predicaat heeft die tweede thuisbasis niet: deze triple staat alleen
            # hier, en overslaan zou hem uit de hereniging laten verdwijnen. Hij blijft dus
            # staan en wijst naar de ongeknipte naam -- dezelfde keuze als de
            # `hasConnection` die na de knip naar de put aan de overkant blijft wijzen.
            voorwerpen = None
        for subject, stuk in onderwerpen if onderwerpen is not None else ((subject_uit, None),):
            if stuk is not None and predicaat == HAS_VALUE and gml is not None:
                yield from _knipmerken(subject, onderwerp, gml, stuk, plan)
                continue
            for object_, _ in voorwerpen if voorwerpen is not None else ((object_uit, None),):
                yield pyoxigraph.Triple(subject, quad.predicate, object_)


def _gml_waarde(term: object) -> str | None:
    """De tekst van een GML-literaal, of None als deze term er geen is."""
    if isinstance(term, pyoxigraph.Literal) and term.datatype.value == GML_LITERAL:
        return term.value
    return None


def _stuktermen(
    plan: _Plan, sleutel: str, deel: int
) -> list[tuple[pyoxigraph.NamedNode | pyoxigraph.BlankNode, _Stuk]] | None:
    """De knopen die in dit deel voor een geknipte geometrieknoop in de plaats komen."""
    stukken = plan.stukken.get(sleutel)
    if stukken is None:
        return None
    return [(_stukterm(sleutel, stuk.volgnummer), stuk) for stuk in stukken if stuk.deel == deel]


def _knipmerken(
    subject: pyoxigraph.NamedNode | pyoxigraph.BlankNode,
    herkomst: str,
    literal: str,
    stuk: _Stuk,
    plan: _Plan,
) -> Iterator[pyoxigraph.Triple]:
    """De geometrie van een stuk plus de merken waarmee `merge_orox` hem terugvindt."""
    geknipt = pyoxigraph.Literal(_met_coordinaten(literal, stuk.coordinaten), datatype=_GML_TYPE)
    yield pyoxigraph.Triple(subject, _HAS_VALUE_KNOOP, geknipt)
    yield pyoxigraph.Triple(subject, _HERKOMST, pyoxigraph.Literal(herkomst))
    yield pyoxigraph.Triple(
        subject, _VOLGNUMMER, pyoxigraph.Literal(str(stuk.volgnummer), datatype=_INTEGER)
    )
    yield pyoxigraph.Triple(
        subject,
        _AANTAL,
        pyoxigraph.Literal(str(len(plan.stukken[herkomst])), datatype=_INTEGER),
    )
    if stuk.ingevoegd_einde:
        yield pyoxigraph.Triple(subject, _INGEVOEGD_EINDE, _WAAR)


# --------------------------------------------------------------------------------------
# Samenvoegen
# --------------------------------------------------------------------------------------


@dataclass
class _Scan:
    """Wat de eerste ronde over de delen oplevert: de stukken en wat ontdubbeld moet worden."""

    prefixen: dict[str, str] = field(default_factory=dict)
    # Sleutel van een stukknoop -> de herkomst waar hij bij hoort.
    herkomst_van: dict[str, str] = field(default_factory=dict)
    # Herkomst -> volgnummer -> (coordinatentekst, ingevoegd_einde).
    stukken: dict[str, dict[int, tuple[str, bool]]] = field(default_factory=dict)
    # Herkomst -> de GML-literaal van het eerste stuk; die levert het omhulsel.
    sjabloon: dict[str, str] = field(default_factory=dict)
    aantallen: dict[str, set[int]] = field(default_factory=dict)
    # Subjecten waarvan de triples in meer dan een deel kunnen staan.
    ontdubbelen: set[str] = field(default_factory=set)


def _ruwe_sleutel(term: object) -> str | None:
    """De sleutel van een term zoals hij in het deelbestand staat.

    Anders dan bij het knippen worden de blanke knopen hier *niet* hernummerd: de clip
    heeft ze een vaste naam gegeven en die naam is precies de identiteit die de delen
    delen.
    """
    if isinstance(term, pyoxigraph.NamedNode):
        return term.value
    if isinstance(term, pyoxigraph.BlankNode):
        return f"_:{term.value}"
    return None


def _scan_delen(delen: Sequence[Path]) -> _Scan:
    """Eerste ronde over de delen: knipstukken verzamelen en dubbele subjecten aanwijzen."""
    scan = _Scan()
    gezien: set[str] = set()
    merken: dict[str, dict[str, str]] = {}
    verwijzers: dict[str, set[str]] = {}

    for index, pad in enumerate(delen):
        geopend = lees_orox(pad)
        if index == 0:
            scan.prefixen = {
                naam: iri for naam, iri in geopend.prefixen.items() if naam != KNIP_PREFIX
            }
        hier: set[str] = set()
        for quad in geopend.quads:
            onderwerp = _ruwe_sleutel(quad.subject)
            assert onderwerp is not None
            hier.add(onderwerp)
            predicaat = quad.predicate.value
            if predicaat.startswith(KNIP) and isinstance(quad.object, pyoxigraph.Literal):
                merken.setdefault(onderwerp, {})[predicaat] = quad.object.value
            elif predicaat == HAS_VALUE:
                gml = _gml_waarde(quad.object)
                if gml is not None:
                    scan.sjabloon.setdefault(onderwerp, gml)
            voorwerp = _ruwe_sleutel(quad.object)
            if voorwerp is not None and "__knip" in voorwerp:
                verwijzers.setdefault(voorwerp, set()).add(onderwerp)
        for sleutel in hier:
            if sleutel in gezien:
                scan.ontdubbelen.add(sleutel)
            gezien.add(sleutel)

    _verwerk_merken(scan, merken)

    # Een triple die naar een stukknoop wees, wijst na het herschrijven naar de herkomst;
    # zulke triples staan dan in elk deel dat een stuk draagt en moeten ontdubbeld worden.
    scan.ontdubbelen |= set(scan.stukken)
    for stukknoop in scan.herkomst_van:
        scan.ontdubbelen |= verwijzers.get(stukknoop, set())
    return scan


def _verwerk_merken(scan: _Scan, merken: dict[str, dict[str, str]]) -> None:
    """Vertaalt de knipmerken naar de stukkenadministratie en controleert of ze compleet is."""
    for knoop, merk in merken.items():
        herkomst = merk.get(f"{KNIP}herkomst")
        if herkomst is None:
            continue
        try:
            volgnummer = int(merk[f"{KNIP}volgnummer"])
            aantal = int(merk[f"{KNIP}aantal"])
        except (KeyError, ValueError) as fout:
            raise DatasetError(
                f"knipmerk op {knoop!r} is onvolledig of onleesbaar ({fout}); zonder volgnummer "
                f"en aantal is de geknipte geometrie niet terug te leggen."
            ) from fout
        tekst = scan.sjabloon.get(knoop)
        if tekst is None:
            raise DatasetError(
                f"knipstuk {knoop!r} draagt geen GML-geometrie; er valt niets aaneen te naaien."
            )
        scan.herkomst_van[knoop] = herkomst
        scan.aantallen.setdefault(herkomst, set()).add(aantal)
        rij = scan.stukken.setdefault(herkomst, {})
        rij[volgnummer] = (_tokens_tekst(tekst), merk.get(f"{KNIP}ingevoegdEinde") == "true")
        scan.sjabloon.setdefault(herkomst, tekst)

    for herkomst, rij in scan.stukken.items():
        aantallen = scan.aantallen[herkomst]
        if len(aantallen) != 1:
            raise DatasetError(
                f"de stukken van {herkomst!r} noemen verschillende aantallen {sorted(aantallen)}; "
                f"dat zijn stukken uit verschillende knipbeurten."
            )
        aantal = next(iter(aantallen))
        if sorted(rij) != list(range(aantal)):
            ontbreekt = sorted(set(range(aantal)) - set(rij))
            raise DatasetError(
                f"van {herkomst!r} ontbreken de stukken {ontbreekt}; de delen zijn niet compleet "
                f"en de geometrie zou korter terugkomen dan ze was."
            )


def _tokens_tekst(literal: str) -> str:
    """De coordinatentekst uit een GML-literaal, ongewijzigd."""
    treffer = _COORDINATEN.search(literal)
    return treffer[2].strip() if treffer is not None else ""


def _samengevoegd(delen: Sequence[Path], scan: _Scan) -> Iterator[pyoxigraph.Triple]:
    """De triples van alle delen samen: ontdubbeld, ontknipt en zonder knipmerken."""
    gezien: set[tuple[str, str, str]] = set()
    geschreven: set[str] = set()
    for pad in delen:
        for quad in lees_orox(pad).quads:
            predicaat = quad.predicate.value
            if predicaat.startswith(KNIP):
                continue
            onderwerp = _ruwe_sleutel(quad.subject)
            assert onderwerp is not None
            herkomst = scan.herkomst_van.get(onderwerp)
            subject: pyoxigraph.NamedNode | pyoxigraph.BlankNode
            if herkomst is not None:
                if predicaat == HAS_VALUE and _gml_waarde(quad.object) is not None:
                    if herkomst not in geschreven:
                        geschreven.add(herkomst)
                        yield _hersteld(herkomst, scan)
                    continue
                subject = _term(herkomst)
            else:
                subject = _term(onderwerp)

            voorwerp = _ruwe_sleutel(quad.object)
            doel = scan.herkomst_van.get(voorwerp) if voorwerp is not None else None
            object_ = _term(doel) if doel is not None else quad.object

            sleutel = herkomst if herkomst is not None else onderwerp
            if sleutel in scan.ontdubbelen:
                merk = (sleutel, predicaat, _objectsleutel(object_))
                if merk in gezien:
                    continue
                gezien.add(merk)
            yield pyoxigraph.Triple(subject, quad.predicate, object_)


def _objectsleutel(term: object) -> str:
    """Een tekstvorm van een object die twee gelijke objecten gelijk maakt."""
    if isinstance(term, pyoxigraph.Literal):
        return "|".join(("L", term.datatype.value, term.language or "", term.value))
    if isinstance(term, pyoxigraph.BlankNode):
        return f"B{term.value}"
    return f"N{getattr(term, 'value', term)}"


def _hersteld(herkomst: str, scan: _Scan) -> pyoxigraph.Triple:
    """De oorspronkelijke geometrie: de stukken aaneen, het ingevoegde knippunt eruit."""
    sjabloon = scan.sjabloon[herkomst]
    stap = _stapgrootte(sjabloon)
    rij = scan.stukken[herkomst]
    tokens: list[str] = []
    for volgnummer in sorted(rij):
        tekst, ingevoegd_einde = rij[volgnummer]
        punten = tekst.split()
        # Van elk stuk na het eerste vervalt het eerste punt (dat herhaalt het laatste punt
        # van het vorige stuk) en van elk stuk dat op een ingevoegd knippunt eindigt het
        # laatste. Wat overblijft is letterlijk de tokenreeks van de bron.
        if volgnummer > 0:
            punten = punten[stap:]
        if ingevoegd_einde:
            punten = punten[: max(len(punten) - stap, 0)]
        tokens.extend(punten)
    literal = _met_coordinaten(sjabloon, " ".join(tokens))
    return pyoxigraph.Triple(
        _term(herkomst), _HAS_VALUE_KNOOP, pyoxigraph.Literal(literal, datatype=_GML_TYPE)
    )


def _stapgrootte(sjabloon: str) -> int:
    """Het aantal getallen per punt, op dezelfde manier bepaald als bij het knippen.

    Niet uit de `srsDimension` gelezen maar uit de verhouding tussen het aantal tokens en
    het aantal punten dat `parse_gml` erin ziet -- precies zoals `_knip_lijn` het deed.
    Zou de literaal geen srsDimension dragen, dan raden beide kanten tenminste hetzelfde
    en blijft het aaneen naaien sluitend.

    Komt die verhouding niet rond, dan is er niets te raden: het aaneen naaien snoeit per
    punt van de tokenreeks, dus een stap van 2 waar de bron er 3 bedoelde levert een
    geometrie op die niemand ooit geschreven heeft -- en dat stilzwijgend. Een stuk dat de
    clip zelf schreef komt hier nooit; wat hier komt is een deel van elders.
    """
    try:
        punten = len(parse_gml(sjabloon).coords)
    except (GeometryError, NotImplementedError):
        punten = 0
    alle = len(_tokens(sjabloon))
    if punten and alle % punten == 0:
        return alle // punten
    raise DatasetError(
        f"uit {sjabloon!r} is niet af te lezen hoeveel getallen er op een punt gaan "
        f"({alle} coordinaatwaarden op {punten} punten); het aaneen naaien van de stukken "
        f"zou dan op de verkeerde plaats snoeien."
    )


__all__ = ["clip_orox", "merge_orox"]
