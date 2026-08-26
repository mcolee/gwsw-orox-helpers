"""Parseren van de GML-literalen uit een GWSW-OroX-dataset."""

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
    coordinaten = _coordinates(literal)

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
    dimensie = _dimension(literal)
    if dimensie < 3:
        return [None] * len(_coordinates(literal))
    return [waarde[2] for waarde in _raw_tuples(literal, dimensie)]


def _kind(literal: str) -> str:
    """Bepaalt de GML-soort; LinearRing telt als polygoonring."""
    match = GML_SOORT_PATROON.search(literal)
    if match is None:
        raise GeometryError("geen herkenbare GML-soort in de literaal")
    return "Polygon" if match[1] == "LinearRing" else match[1]


def _dimension(literal: str) -> int:
    """Bepaalt het aantal waarden per punt.

    In de GWSW-export draagt `gml:posList` altijd een srsDimension en `gml:pos`
    nooit; bij een los punt is het aantal waarden dus de dimensie. Blijft het
    daarna dubbelzinnig, dan wint 2 boven 3.
    """
    match = SRS_DIMENSIE_PATROON.search(literal)
    if match:
        return int(match[1])

    aantal = len(_values(literal))
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


def _raw_tuples(literal: str, dimensie: int) -> list[tuple[float, ...]]:
    """Splitst de coordinatenlijst in tupels van `dimensie` getallen."""
    getallen = _values(literal)

    if dimensie < 2 or len(getallen) % dimensie != 0 or not getallen:
        raise GeometryError(
            f"{len(getallen)} coordinaatwaarden passen niet op srsDimension {dimensie}"
        )

    return [tuple(getallen[i : i + dimensie]) for i in range(0, len(getallen), dimensie)]


def _coordinates(literal: str) -> list[tuple[float, float]]:
    """De x- en y-waarden van de literaal, zonder z."""
    dimensie = _dimension(literal)
    return [(waarde[0], waarde[1]) for waarde in _raw_tuples(literal, dimensie)]
