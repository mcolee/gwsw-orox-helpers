"""Lezen en terugleggen van de GML-literalen uit een GWSW-OroX-dataset.

Twee kanten van dezelfde literaal, en met opzet in een module. De **lezerskant**
(`parse_gml`, `parse_gml_z`, `parse_gml_met_z`, `is_multipart_literal`) maakt er
shapely-geometrie van; dat is wat de leeslaag nodig heeft. De **tekstkant**
(`coordinaattokens`, `vervang_coordinaten`, `tokens_per_punt`) laat de coordinatenlijst
juist tekst blijven en legt haar letterlijk terug; dat is wat de knip nodig heeft, want
`233000.00` hoort na een knip en een hereniging weer als `233000.00` op zijn plaats te
staan.

Ze delen `COORDINATEN_PATROON`, en dat is de reden dat ze naast elkaar staan: wie de
lijst knipt moet dezelfde lijst zien als wie hem leest. Een tweede exemplaar van dat
patroon (de cliplaag droeg er een) valt pas op als de twee kanten dezelfde bron
verschillend lezen, en dan is het te laat.

**Drie lezers en niet twee.** `parse_gml` en `parse_gml_z` zijn de losse vragen -- de
knip stelt er precies een van, en beide staan gepind in `tests/test_publieke_api.py`.
Wie ze allebei op dezelfde literaal stelt (de leeslaag doet dat voor elke geometrie in
de export) betaalt de regex en de float-conversie twee tot vijf keer; `parse_gml_met_z`
stelt ze in een gang en geeft allebei de antwoorden terug. De drie delen dezelfde
private stappen (`_kind`, `_values`, `_dimensie_van`, `_tupels`, `_bouw`), zodat er geen
tweede exemplaar van de dimensieregel of van de shapely-tak kan ontstaan --
`test_parse_gml_met_z_is_gelijkwaardig_aan_de_twee_losse_lezers` toetst dat de uitkomst
en elke foutmelding gelijk blijven.
"""

from __future__ import annotations

import re

from shapely.errors import ShapelyError
from shapely.geometry import LineString, Point, Polygon

GML_SOORT_PATROON = re.compile(r"<gml:(Point|LineString|Polygon|LinearRing)\b")
SRS_DIMENSIE_PATROON = re.compile(r'srsDimension="(\d+)"')
COORDINATEN_PATROON = re.compile(r"<gml:(?:pos|posList)[^>]*>([^<]*)</gml:(?:pos|posList)>")
# Multi-geometrieen uit GML 3 en de oudere GML 2-namen; TOP-015 vraagt ernaar.
MULTI_PATROON = re.compile(r"<gml:(Multi(?:Point|Curve|Surface|LineString|Polygon|Geometry))\b")


class GeometryError(ValueError):
    """De GML-literaal kon niet als geometrie gelezen worden."""


def parse_gml(literal: str) -> Point | LineString | Polygon:
    """Leest een GML-literaal als shapely-geometrie in het horizontale vlak.

    De z-waarden worden hier weggelaten; die haalt `parse_gml_z` apart op, omdat
    de topologiechecks in het platte vlak werken en de hoogtechecks niet.
    """
    soort = _kind(literal)
    return _bouw(soort, _coordinates(literal))


def is_multipart_literal(literal: str) -> bool:
    """Geeft aan of de GML-literaal een multi-geometrie of meerdere delen bevat.

    Twee vormen tellen mee: een expliciete `gml:Multi*`-verpakking, en meerdere
    `gml:pos`- of `gml:posList`-elementen naast elkaar. De parser leest alleen het
    eerste deel, dus zonder deze signalering zou het verschil onzichtbaar blijven.
    """
    if MULTI_PATROON.search(literal) is not None:
        return True
    return len(COORDINATEN_PATROON.findall(literal)) > 1


def parse_gml_z(literal: str) -> list[float | None]:
    """Geeft de z-waarde per punt; `None` waar de geometrie tweedimensionaal is."""
    dimensie = _dimensie_van(literal, None)
    if dimensie < 3:
        return [None] * len(_coordinates(literal))
    return [waarde[2] for waarde in _tupels(_values(literal), dimensie)]


def parse_gml_met_z(literal: str) -> tuple[Point | LineString | Polygon, list[float | None]]:
    """De geometrie in het platte vlak én de z-waarde per punt, uit een lezing.

    Precies `(parse_gml(literal), parse_gml_z(literal))`, tot en met de foutmeldingen,
    maar met een enkele regex over de coordinatenlijst en een enkele float-conversie in
    plaats van twee tot vijf. Dat verschil is de reden dat deze functie bestaat: de
    leeslaag stelt beide vragen over elke geometrie in de export, en dat zijn er op een
    gemeentelijke OroX-export honderdduizenden.

    De volgorde van de stappen is die van de twee losse lezers achter elkaar, want de
    fout die een onleesbare literaal oplevert hoort dezelfde te zijn: eerst de GML-soort
    (`parse_gml` begint daar), dan de getallen, dan de dimensie, dan de verdeling in
    punten en pas daarna shapely. Dat `_values` hier vóór de `srsDimension` gelezen wordt
    maakt geen verschil: het zoeken van de srsDimension kan zelf niet mislukken, en waar
    de oude weg hem las kwam `_values` er direct achter, met dezelfde melding. Het geval
    dat die herordening raakt -- srsDimension aanwezig, `gml:pos` afwezig -- staat als
    `fout-srsdimension-zonder-lijst` in de gelijkwaardigheidstest.

    Waarom dan niet `parse_gml` en `parse_gml_z` hierop laten wachten? Omdat ze niet
    dezelfde vraag stellen. De knip vraagt alleen de meetkunde en alleen de z-lijst, en
    `parse_gml_z` kijkt bewust niet naar de GML-soort -- een literaal zonder herkenbare
    soort geeft daar z-waarden en hier een fout. Ze delegeren daarom niet aan elkaar
    maar aan dezelfde private stappen.
    """
    soort = _kind(literal)
    getallen = _values(literal)
    dimensie = _dimensie_van(literal, getallen)
    tupels = _tupels(getallen, dimensie)

    meetkunde = _bouw(soort, [(waarde[0], waarde[1]) for waarde in tupels])
    if dimensie < 3:
        return meetkunde, [None] * len(tupels)
    return meetkunde, [waarde[2] for waarde in tupels]


def coordinaattokens(literal: str) -> list[str]:
    """De losse coordinaatgetallen van de eerste gml:pos of gml:posList, als tekst.

    De tekstkant van dezelfde lijst die `parse_gml` als getallen leest, en met opzet
    ongeoordeeld: geen `gml:pos`, een lege lijst of onleesbare inhoud levert hier geen
    fout maar een lege lijst, want de afnemer (de knip) beslist zelf wat hij met zo'n
    literaal doet -- hij laat hem heel. Wie de getallen als getallen wil, neemt
    `parse_gml`; die klaagt wel.

    De tokens zijn de brontekst en geen floats. Dat is geen detail maar de reden dat
    deze functie bestaat: `233000.00` hoort na een knip en een hereniging weer als
    `233000.00` op zijn plaats te staan en niet als `233000.0`.
    """
    treffer = COORDINATEN_PATROON.search(literal)
    return treffer[1].split() if treffer is not None else []


def vervang_coordinaten(literal: str, coordinaten: str) -> str:
    """Dezelfde GML-literaal, met een andere coordinatenlijst erin.

    Alleen de inhoud van de eerste `gml:pos` of `gml:posList` gaat eruit; al het andere
    (srsName, srsDimension, de soort geometrie, een tweede lijst ernaast) blijft
    letterlijk staan. Valt er niets te vervangen, dan komt de literaal ongewijzigd terug.
    """
    treffer = COORDINATEN_PATROON.search(literal)
    if treffer is None:
        return literal
    begin, eind = treffer.span(1)
    return literal[:begin] + coordinaten + literal[eind:]


def tokens_per_punt(literal: str, punten: int) -> int | None:
    """Hoeveel coordinaatgetallen er op een punt gaan; `None` als dat niet rondkomt.

    Uit de verhouding tussen het aantal tokens en het aantal punten dat de lezer in de
    literaal ziet, en **niet** uit de `srsDimension`. Dat is een opzettelijke keuze en de
    grond onder de knip en zijn omkering: tellen beide kanten over dezelfde tokenreeks,
    dan komen ze op hetzelfde uit -- ook met een srsDimension die niet klopt met wat erin
    staat. Zou de een tellen en de ander de srsDimension lezen, dan zou de hereniging per
    punt op de verkeerde plaats snoeien en stilzwijgend een geometrie opleveren die niemand
    ooit geschreven heeft.

    **De uitzondering, en waarom de knip haar zelf afvangt.** Bij een literaal *zonder*
    srsDimension leunt het puntental op `_dimensie_van`, en die kiest bij twijfel 2 boven 3
    (`aantal % 2 == 0`). Een stuk van een 3D-lijn zonder srsDimension kan een even tokental
    dragen (vier punten -> twaalf tokens) en dan als 2D gelezen worden, terwijl de hele bron
    (vijftien tokens, oneven) als 3D leest: op de bron telt deze functie 3, op zo'n stuk 2.
    Dan lopen de knip en de hereniging wél uiteen. Daarom knipt `clip.knip._knip_lijn` een
    3D-lijn zonder srsDimension niet maar geeft hem heel door (issue #46), zodat er nooit
    een stuk van bestaat waarover deze telling kan omslaan.

    `punten` is het aantal punten dat de aanroeper al kent (`len(lijn.coords)`); deze
    functie parseert de literaal niet nog eens. Komt de verhouding niet rond -- geen
    punten, geen getallen, of een rest -- dan is er niets te raden en is het antwoord
    `None`; wat de aanroeper daarmee doet (heel doorgeven, of een fout) is aan hem.
    """
    alle = len(coordinaattokens(literal))
    if punten <= 0 or alle == 0 or alle % punten != 0:
        return None
    return alle // punten


def heeft_srsdimension(literal: str) -> bool:
    """Of de GML-literaal een `srsDimension` op zijn coordinatenlijst declareert.

    De tekstkant van de dimensievraag, naast `tokens_per_punt`. `_dimensie_van` valt zonder
    srsDimension bij een even tokental terug op 2, dus wie 3D-zonder-srsDimension van 2D wil
    onderscheiden kan niet op de *gelezen* dimensie afgaan maar hoort naar de declaratie zelf
    te kijken. De knip gebruikt dat om een 3D-lijn zonder srsDimension heel door te geven
    (issue #46): een stuk ervan kan een even tokental hebben en zou bij de hereniging als 2D
    gesnoeid worden.
    """
    return SRS_DIMENSIE_PATROON.search(literal) is not None


def _kind(literal: str) -> str:
    """Bepaalt de GML-soort; LinearRing telt als polygoonring."""
    match = GML_SOORT_PATROON.search(literal)
    if match is None:
        raise GeometryError("geen herkenbare GML-soort in de literaal")
    return "Polygon" if match[1] == "LinearRing" else match[1]


def _bouw(soort: str, coordinaten: list[tuple[float, float]]) -> Point | LineString | Polygon:
    """Maakt er de shapely-geometrie van, of een `GeometryError`.

    De enige plek waar deze package shapely aanroept om een geometrie te bouwen; zowel
    `parse_gml` als `parse_gml_met_z` komen hierlangs, zodat de fouttak er een blijft.
    """
    try:
        if soort == "Point":
            return Point(coordinaten[0])
        if soort == "LineString":
            return LineString(coordinaten)
        return Polygon(coordinaten)
    except (IndexError, ValueError, ShapelyError) as error:
        # `ShapelyError` hoort er expliciet bij en volgt niet uit `ValueError`: een
        # lijn met precies een coordinaat laat GEOS zelf struikelen, en die fout erft
        # niet van ValueError. Zonder deze tak vluchtte hij ongevangen naar buiten en
        # brak het inlezen van de hele export af op een enkel onleesbaar object --
        # terwijl het bedoelde gedrag is dat het object in `geometry_errors` belandt
        # en het rapport erover meldt.
        raise GeometryError(f"onbruikbare {soort}-geometrie: {error}") from error


def _dimensie_van(literal: str, getallen: list[float] | None) -> int:
    """Bepaalt het aantal waarden per punt; de enige plek waar die regel staat.

    In de GWSW-export draagt `gml:posList` altijd een srsDimension en `gml:pos`
    nooit; bij een los punt is het aantal waarden dus de dimensie. Blijft het
    daarna dubbelzinnig, dan wint 2 boven 3.

    `getallen` zijn de coordinaatwaarden die de aanroeper al gelezen heeft, of `None`
    als hij ze nog niet heeft. Dat onderscheid is er voor de kosten en niet voor het
    gedrag: een literaal met een srsDimension hoeft er niet voor langs `_values`, dus
    een aanroeper die de getallen nog niet nodig had, leest ze ook nu niet.
    """
    match = SRS_DIMENSIE_PATROON.search(literal)
    if match:
        return int(match[1])

    aantal = len(_values(literal) if getallen is None else getallen)
    if aantal in (2, 3):
        return aantal
    if aantal % 2 == 0:
        return 2
    if aantal % 3 == 0:
        return 3
    raise GeometryError(f"{aantal} coordinaatwaarden zonder srsDimension zijn niet te duiden")


def _values(literal: str) -> list[float]:
    """De losse getallen uit de gml:pos- of gml:posList-inhoud."""
    match = COORDINATEN_PATROON.search(literal)
    if match is None:
        raise GeometryError("geen gml:pos of gml:posList gevonden")

    try:
        return [float(deel) for deel in match[1].split()]
    except ValueError as error:
        raise GeometryError(f"niet-numerieke coordinaat: {error}") from error


def _tupels(getallen: list[float], dimensie: int) -> list[tuple[float, ...]]:
    """Verdeelt al gelezen getallen in tupels van `dimensie` groot."""
    if dimensie < 2 or len(getallen) % dimensie != 0 or not getallen:
        raise GeometryError(
            f"{len(getallen)} coordinaatwaarden passen niet op srsDimension {dimensie}"
        )

    return [tuple(getallen[i : i + dimensie]) for i in range(0, len(getallen), dimensie)]


def _coordinates(literal: str) -> list[tuple[float, float]]:
    """De x- en y-waarden van de literaal, zonder z."""
    dimensie = _dimensie_van(literal, None)
    return [(waarde[0], waarde[1]) for waarde in _tupels(_values(literal), dimensie)]
