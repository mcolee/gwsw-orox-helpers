"""Ruimtelijke toewijzing in bulk (issue #86): dezelfde uitkomst als `_plaats` per literaal."""

from __future__ import annotations

from shapely.geometry import box
from shapely.prepared import prep

from gwsw_orox_helpers.clip.grenzen import _Vlak
from gwsw_orox_helpers.clip.knip import _plaats, _plaats_alle


def _vlak(naam: str, x0: float, x1: float) -> _Vlak:
    meetkunde = box(x0, 0, x1, 10)
    return _Vlak(naam=naam, meetkunde=meetkunde, voorbereid=prep(meetkunde))


def _punt(x: float, y: float) -> str:
    return f"<gml:Point><gml:pos>{x} {y}</gml:pos></gml:Point>"


def _lijn(*coordinaten: float) -> str:
    tekst = " ".join(str(c) for c in coordinaten)
    return f'<gml:LineString><gml:posList srsDimension="2">{tekst}</gml:posList></gml:LineString>'


LITERALEN = [
    _punt(2, 5),  # binnen a
    _punt(7, 5),  # binnen b
    _punt(5, 5),  # precies op de grens tussen a en b: het eerste vlak dat hem dekt
    _punt(0, 0),  # op de buitenrand van a
    _punt(25, 5),  # buiten alles: terugval op het dichtstbijzijnde vlak
    _lijn(1, 1, 4, 4),  # binnen a
    _lijn(1, 5, 5, 5),  # eindigt op de grens: nog binnen a
    _lijn(1, 5, 9, 5),  # kruist de grens: geknipt
    _lijn(1, 5, 30, 5),  # kruist de grens en loopt naar buiten
    _lijn(20, 1, 30, 1),  # helemaal buiten
    "<gml:Polygon><gml:posList>6 1 8 1 8 3 6 1</gml:posList></gml:Polygon>",
    "<gml:LineString><gml:posList>1 2</gml:posList></gml:LineString>",  # één coordinaat
    "<gml:Point><gml:pos>a b</gml:pos></gml:Point>",  # onleesbaar
    "<gml:Ding><gml:pos>1 2</gml:pos></gml:Ding>",  # geen soort
]


def test_plaats_alle_geeft_per_literaal_hetzelfde_als_plaats() -> None:
    vlakken = (_vlak("a", 0, 5), _vlak("b", 5, 10))

    assert _plaats_alle(LITERALEN, vlakken) == [_plaats(lit, vlakken) for lit in LITERALEN]


def test_plaats_alle_zonder_literalen_is_leeg() -> None:
    assert _plaats_alle([], (_vlak("a", 0, 5),)) == []
