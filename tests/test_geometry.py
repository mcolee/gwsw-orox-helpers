"""Tests voor de GML-parser."""

from __future__ import annotations

import math

import pytest
from shapely.geometry import LineString, Point, Polygon

from gwsw_orox_helpers.geometry import (
    GeometryError,
    is_multipart_literal,
    parse_gml,
    parse_gml_z,
)

PUNT_3D = '<gml:Point xmlns:gml="g"><gml:pos>168462.01 442691.30 22.45</gml:pos></gml:Point>'
PUNT_2D = '<gml:Point xmlns:gml="g"><gml:pos>168462.51 442691.30</gml:pos></gml:Point>'
LIJN_3D = (
    '<gml:LineString xmlns:gml="g"><gml:posList srsDimension="3">'
    "1 2 30 4 5 60</gml:posList></gml:LineString>"
)
LIJN_2D = (
    '<gml:LineString xmlns:gml="g"><gml:posList srsDimension="2">'
    "1 2 4 5</gml:posList></gml:LineString>"
)
RING = (
    '<gml:Polygon xmlns:gml="g"><gml:exterior><gml:LinearRing><gml:posList srsDimension="2">'
    "0 0 0 1 1 1 0 0</gml:posList></gml:LinearRing></gml:exterior></gml:Polygon>"
)


def test_punt_met_hoogte() -> None:
    assert parse_gml(PUNT_3D) == Point(168462.01, 442691.30)
    assert parse_gml_z(PUNT_3D) == [22.45]


def test_punt_zonder_hoogte() -> None:
    # gml:pos draagt in de GWSW-export nooit een srsDimension; het aantal
    # waarden bepaalt dan de dimensie.
    assert parse_gml(PUNT_2D) == Point(168462.51, 442691.30)
    assert parse_gml_z(PUNT_2D) == [None]


def test_lijn_driedimensionaal() -> None:
    assert parse_gml(LIJN_3D) == LineString([(1, 2), (4, 5)])
    assert parse_gml_z(LIJN_3D) == [30.0, 60.0]


def test_lijn_tweedimensionaal() -> None:
    assert parse_gml(LIJN_2D) == LineString([(1, 2), (4, 5)])
    assert parse_gml_z(LIJN_2D) == [None, None]


def test_polygoon_uit_linearring() -> None:
    vlak = parse_gml(RING)

    assert isinstance(vlak, Polygon)
    assert vlak.area == pytest.approx(0.5)


@pytest.mark.parametrize(
    ("literal", "melding"),
    [
        ("<gml:Kromme>1 2</gml:Kromme>", "GML-soort"),
        ('<gml:Point xmlns:gml="g"></gml:Point>', "gml:pos"),
        ('<gml:Point xmlns:gml="g"><gml:pos>een twee</gml:pos></gml:Point>', "niet-numeriek"),
        (
            '<gml:LineString xmlns:gml="g"><gml:posList srsDimension="3">1 2 3 4'
            "</gml:posList></gml:LineString>",
            "srsDimension",
        ),
    ],
)
def test_onbruikbare_geometrie(literal: str, melding: str) -> None:
    with pytest.raises(GeometryError, match=melding):
        parse_gml(literal)


def test_is_multipart_literal_herkent_beide_vormen() -> None:
    """Een expliciete Multi-verpakking en twee posLists naast elkaar tellen allebei.

    De parser leest alleen het eerste deel, dus zonder deze signalering blijft het
    verschil tussen een streng en een streng met een los tweede stuk onzichtbaar.
    """
    multi = (
        '<gml:MultiCurve xmlns:gml="g"><gml:curveMember><gml:LineString>'
        '<gml:posList srsDimension="2">1 2 4 5</gml:posList></gml:LineString>'
        "</gml:curveMember></gml:MultiCurve>"
    )
    twee_lijsten = (
        '<gml:LineString xmlns:gml="g"><gml:posList srsDimension="2">1 2 4 5</gml:posList>'
        '<gml:posList srsDimension="2">7 8 9 0</gml:posList></gml:LineString>'
    )

    assert is_multipart_literal(multi) is True
    assert is_multipart_literal(twee_lijsten) is True
    assert is_multipart_literal(LIJN_2D) is False


def test_dimensie_valt_terug_op_een_even_aantal_waarden() -> None:
    """`gml:pos` draagt nooit een srsDimension; vier waarden zijn twee 2D-punten."""
    literal = '<gml:LineString xmlns:gml="g"><gml:pos>1 2 4 5</gml:pos></gml:LineString>'

    assert parse_gml_z(literal) == [None, None]


def test_dimensie_valt_terug_op_een_drievoud_waarden() -> None:
    """Negen waarden zijn niet in tweeen te delen maar wel in drieen: drie 3D-punten."""
    literal = '<gml:LineString xmlns:gml="g"><gml:pos>1 2 3 4 5 6 7 8 9</gml:pos></gml:LineString>'

    assert parse_gml_z(literal) == [3.0, 6.0, 9.0]


def test_een_ondeelbaar_aantal_waarden_is_een_leesfout() -> None:
    literal = '<gml:LineString xmlns:gml="g"><gml:pos>1 2 3 4 5</gml:pos></gml:LineString>'

    with pytest.raises(GeometryError, match="niet te duiden"):
        parse_gml_z(literal)


def test_vlak_geeft_zijn_coordinaten_via_de_buitenring() -> None:
    """Een put met een vlak als geometrie moet op eindige coordinaten te toetsen zijn.

    `hasattr(polygon, "coords")` roept de property aan, en die gooit bij shapely een
    NotImplementedError -- geen AttributeError, dus hasattr vangt hem niet op. Een
    afnemer die de coordinaten van een vlak wil, gaat dus via de ringen. Vlakken horen
    niet in een GWSW-export thuis, maar ze komen er wel in voor.
    """
    eindig = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    oneindig = Polygon([(0, 0), (float("inf"), 0), (1, 1), (0, 1)])

    with pytest.raises(NotImplementedError):
        _ = eindig.coords

    assert all(math.isfinite(w) for x, y in eindig.exterior.coords for w in (x, y))
    assert not all(math.isfinite(w) for x, y in oneindig.exterior.coords for w in (x, y))


def test_lijn_met_een_enkel_punt_is_een_leesfout() -> None:
    """GEOS gooit hier zijn eigen fout, en die erft niet van `ValueError`.

    Zonder de expliciete tak brak deze literaal het inlezen van de hele export af.
    Het bedoelde gedrag is dat het object als onleesbaar geteld wordt en de rest
    gewoon doorgaat.
    """
    literal = (
        '<gml:LineString xmlns:gml="g"><gml:posList srsDimension="2">'
        "1000.0 2000.0</gml:posList></gml:LineString>"
    )
    with pytest.raises(GeometryError, match="onbruikbare LineString-geometrie"):
        parse_gml(literal)
