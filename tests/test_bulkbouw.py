"""Geometrie in bulk (issue #82): dezelfde geometrie en dezelfde fouten als per object."""

from __future__ import annotations

from pathlib import Path

import pytest

from gwsw_orox_helpers.dataset import load_dataset
from gwsw_orox_helpers.geometry import GeometryError, _Bulkbouw, parse_gml_met_z

FIXTURES = Path(__file__).parent / "fixtures"

LITERALEN = [
    "<gml:Point><gml:pos>233000.00 520000.00</gml:pos></gml:Point>",
    "<gml:Point><gml:pos>1 2 3</gml:pos></gml:Point>",
    '<gml:LineString><gml:posList srsDimension="3">1 2 3 4 5 6</gml:posList></gml:LineString>',
    "<gml:LineString><gml:posList>1 2 3 4 5 6 7 8</gml:posList></gml:LineString>",
    "<gml:Polygon><gml:posList>0 0 1 0 1 1 0 0</gml:posList></gml:Polygon>",
]
KAPOT = [
    "<gml:LineString><gml:posList>1 2</gml:posList></gml:LineString>",
    "<gml:Point><gml:pos>a b</gml:pos></gml:Point>",
    "<gml:Ding><gml:pos>1 2</gml:pos></gml:Ding>",
]


def test_de_bulkbouw_geeft_dezelfde_geometrie_en_z_als_parse_gml_met_z() -> None:
    bouw = _Bulkbouw()
    gelezen = [bouw.lees(literal) for literal in LITERALEN]
    for literal, (waarde, z_waarden) in zip(LITERALEN, gelezen, strict=True):
        verwacht, verwachte_z = parse_gml_met_z(literal)
        geometrie = bouw.geometrie(waarde)
        assert geometrie is not None
        assert geometrie.wkb == verwacht.wkb
        assert z_waarden == verwachte_z


@pytest.mark.parametrize("literal", KAPOT)
def test_de_bulkbouw_faalt_meteen_met_dezelfde_melding(literal: str) -> None:
    with pytest.raises(GeometryError) as verwacht:
        parse_gml_met_z(literal)
    with pytest.raises(GeometryError) as bulk:
        _Bulkbouw().lees(literal)
    assert str(bulk.value) == str(verwacht.value)


def test_elke_fixture_leest_dezelfde_geometrie_als_per_object(monkeypatch) -> None:
    paden = sorted((FIXTURES / "ttl").glob("*.ttl")) + sorted((FIXTURES / "ttl17").glob("*.ttl"))
    bulk = {}
    for pad in paden:
        try:
            bulk[pad] = load_dataset(pad, [])
        except Exception:  # noqa: BLE001 - een fixture die niet laadt doet hier niet mee
            continue
    assert bulk

    monkeypatch.setattr(_Bulkbouw, "lees", lambda self, literal: parse_gml_met_z(literal))
    for pad, ds in bulk.items():
        per_object = load_dataset(pad, [])
        assert ds.geometry_errors == per_object.geometry_errors, pad
        for uri, node in per_object.nodes.items():
            gelezen = ds.nodes[uri].point
            assert (gelezen.wkb if gelezen else None) == (node.point.wkb if node.point else None)
        for uri, conduit in per_object.conduits.items():
            gelezen = ds.conduits[uri].line
            assert (gelezen.wkb if gelezen else None) == (
                conduit.line.wkb if conduit.line else None
            )


def test_de_cache_geeft_dezelfde_geometrie_terug_uit_één_wkb_lijst(tmp_path, monkeypatch) -> None:
    import shapely

    from gwsw_orox_helpers import cache

    bron = FIXTURES / "ttl" / "schoon.ttl"
    koud, _ = cache.laad_met_cache(bron, [], cache_dir=tmp_path)
    aanroepen: list[int] = []
    echte = shapely.from_wkb

    def tel(*args, **kwargs):
        aanroepen.append(1)
        return echte(*args, **kwargs)

    monkeypatch.setattr(shapely, "from_wkb", tel)
    warm, uitslag = cache.laad_met_cache(bron, [], cache_dir=tmp_path)
    assert uitslag.bron == "cache"
    assert len(aanroepen) == 1
    geometrieen = [n.point for n in koud.nodes.values()] + [c.line for c in koud.conduits.values()]
    assert any(g is not None for g in geometrieen)
    for uri, node in koud.nodes.items():
        terug = warm.nodes[uri].point
        assert (terug.wkb if terug else None) == (node.point.wkb if node.point else None)
    for uri, conduit in koud.conduits.items():
        terug = warm.conduits[uri].line
        assert (terug.wkb if terug else None) == (conduit.line.wkb if conduit.line else None)
    structuren = next(tmp_path.rglob(cache.BESTAND_STRUCTUREN)).read_bytes()
    assert b"from_wkb" not in structuren  # geen enkele geometrie op de weg per object


def test_de_bulkbouw_valt_terug_op_de_weg_per_object_als_shapely_in_bulk_faalt(
    monkeypatch,
) -> None:
    import shapely
    from shapely.errors import ShapelyError

    echt = {"points": shapely.points, "linestrings": shapely.linestrings}

    def faal_in_bulk(naam):
        # Alleen de bulkaanroep (een lijst) faalt; `Point(...)`/`LineString(...)` lopen zelf
        # ook via deze functies en moeten blijven werken.
        def aanroep(coords, *args, **kwargs):
            bulk = "indices" in kwargs if naam == "linestrings" else isinstance(coords, list)
            if bulk:
                raise ShapelyError("bulk faalt")
            return echt[naam](coords, *args, **kwargs)

        return aanroep

    monkeypatch.setattr(shapely, "points", faal_in_bulk("points"))
    monkeypatch.setattr(shapely, "linestrings", faal_in_bulk("linestrings"))
    bouw = _Bulkbouw()
    gelezen = [bouw.lees(literal) for literal in LITERALEN]
    for literal, (waarde, _z) in zip(LITERALEN, gelezen, strict=True):
        geometrie = bouw.geometrie(waarde)
        assert geometrie is not None
        assert geometrie.wkb == parse_gml_met_z(literal)[0].wkb
