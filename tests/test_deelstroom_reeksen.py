"""De schrijfpass in reeksen (issue #84): dezelfde stroom als de weg per quad."""

from __future__ import annotations

import itertools
import random
from array import array
from collections.abc import Iterator
from pathlib import Path

import pyoxigraph
import pytest

from gwsw_orox_helpers.clip.grenzen import _lees_grenzen
from gwsw_orox_helpers.clip.plan import _maak_plan, _nummer, _Plan
from gwsw_orox_helpers.clip.stroom import _deelstroom, _herschreven
from gwsw_orox_helpers.clip.termen import (
    _GEKNIPT,
    _WAAR,
    _bronbasis_en_rest,
    _Kniptermen,
    _kniptermen,
    _term,
)
from gwsw_orox_helpers.errors import KnipError
from gwsw_orox_helpers.schrijven import lees_orox

FIXTURES = Path(__file__).parent / "fixtures"
BRON = FIXTURES / "ttl" / "mini_orox.ttl"
GRENS = FIXTURES / "gis" / "mini_grens.geojson"


def _per_quad(
    quads: Iterator[pyoxigraph.Quad], plan: _Plan, deel: int, termen: _Kniptermen
) -> Iterator[pyoxigraph.Quad | pyoxigraph.Triple]:
    """De weg van vóór issue #84: Python per quad."""
    bit = 1 << deel
    for blok, masker in plan.geknipte_houders.items():
        if masker & bit:
            yield pyoxigraph.Triple(_term(blok), _GEKNIPT, _WAAR)
    labels: dict[str, str] = {}
    teller = itertools.count()
    for positie, quad in enumerate(quads):
        if plan.herschrijf[positie]:
            _nummer(quad, labels, teller)
        if not plan.posmasker[positie] & bit:
            continue
        if not plan.herschrijf[positie]:
            yield quad
            continue
        yield from _herschreven(quad, plan, deel, termen, labels)


def _plan() -> tuple[_Plan, _Kniptermen]:
    geopend = lees_orox(BRON)
    basis, verbruikt = _bronbasis_en_rest(geopend.quads, BRON)
    termen = _kniptermen(basis)
    vlakken = _lees_grenzen(GRENS, "gemeentenaam")
    return _maak_plan(BRON, itertools.chain(verbruikt, geopend.quads), vlakken, termen), termen


@pytest.mark.parametrize("typecode", ["B", "L"])
@pytest.mark.parametrize("zaad", range(20))
def test_de_reeksen_geven_dezelfde_stroom_als_de_weg_per_quad(typecode: str, zaad: int) -> None:
    """Willekeurige maskers en herschrijfvlaggen, ook aan begin en eind van de stroom."""
    plan, termen = _plan()
    aantal = len(plan.herschrijf)
    toeval = random.Random(zaad)
    plan.posmasker = array(typecode, (toeval.choice((0, 1, 2, 3)) for _ in range(aantal)))
    vlaggen = [toeval.random() < 0.2 for _ in range(aantal)]
    vlaggen[0] = vlaggen[-1] = bool(zaad % 2)
    # Een herschrijfvlag op een quad die niet herschreven hoeft, geeft dezelfde triple terug;
    # dat volstaat om de volgorde en de nummering te toetsen.
    plan.herschrijf = bytearray(vlaggen)
    # Eén lezing voor beide wegen: pyoxigraph verzint per lezing andere blanke-knoopnamen.
    quads = list(lees_orox(BRON).quads)
    for deel in (0, 1):
        verwacht = list(_per_quad(iter(quads), plan, deel, termen))
        gekregen = list(_deelstroom(quads, plan, deel, termen))
        assert gekregen == verwacht


def test_een_langere_bron_dan_de_positietabel_is_een_knipfout() -> None:
    """Het bestand veranderde tussen de analyseronde en de schrijfpass: niet stil inkorten."""
    plan, termen = _plan()
    quads = list(lees_orox(BRON).quads)
    with pytest.raises(KnipError, match="ander aantal quads"):
        list(_deelstroom([*quads, quads[0]], plan, 0, termen))


def test_een_bron_die_voor_een_herschrijfquad_ophoudt_is_een_knipfout() -> None:
    plan, termen = _plan()
    quads = list(lees_orox(BRON).quads)
    plan.herschrijf = bytearray(len(quads))
    plan.herschrijf[-1] = 1
    with pytest.raises(KnipError, match="ander aantal quads"):
        list(_deelstroom(quads[:-1], plan, 0, termen))
