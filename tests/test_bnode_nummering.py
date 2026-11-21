"""Eén nummering van blanke knopen, op drie plekken uitgeschreven (issue #89).

`clip.plan._genummerd` (de analyseronde), `clip.plan._nummer` (de schrijfpass) en
`schrijven._hernummerd` (`deterministisch=True`) geven elke blanke knoop `b<n>` op eerste
ontmoeting, subject vóór object. De twee hete lussen houden hun kopie bewust inline; deze
test houdt de drie gelijk.
"""

from __future__ import annotations

import itertools
from pathlib import Path

import pyoxigraph
import pytest

from gwsw_orox_helpers.clip.plan import _genummerd, _nummer
from gwsw_orox_helpers.schrijven import _hernummerd, lees_orox

MINI = Path(__file__).parent / "fixtures" / "ttl" / "mini_orox.ttl"


def _eigen() -> list[pyoxigraph.Quad]:
    """Een blanke knoop eerst als object, een lus op zichzelf, en een literaal als object."""
    a, p = pyoxigraph.NamedNode("http://x/a"), pyoxigraph.NamedNode("http://x/p")
    x, y, z = pyoxigraph.BlankNode(), pyoxigraph.BlankNode(), pyoxigraph.BlankNode()
    return [
        pyoxigraph.Quad(a, p, x),
        pyoxigraph.Quad(y, p, x),
        pyoxigraph.Quad(x, p, z),
        pyoxigraph.Quad(z, p, pyoxigraph.Literal("1")),
        pyoxigraph.Quad(y, p, y),
    ]


def _sleutel(term: object, namen: dict[str, str] | None = None) -> str | None:
    if isinstance(term, pyoxigraph.NamedNode):
        return term.value
    if isinstance(term, pyoxigraph.BlankNode):
        return namen[term.value] if namen is not None else f"_:{term.value}"
    return None


@pytest.mark.parametrize("bron", ["mini", "eigen"])
def test_de_drie_nummeringen_geven_dezelfde_namen(bron: str) -> None:
    quads = list(lees_orox(MINI).quads) if bron == "mini" else _eigen()

    analyse = [(onderwerp, voorwerp) for _, onderwerp, voorwerp in _genummerd(quads)]

    namen: dict[str, str] = {}
    teller = itertools.count()
    for quad in quads:
        _nummer(quad, namen, teller)
    schrijfpass = [(_sleutel(q.subject, namen), _sleutel(q.object, namen)) for q in quads]

    deterministisch = [(_sleutel(q.subject), _sleutel(q.object)) for q in _hernummerd(quads)]

    assert analyse == schrijfpass == deterministisch
    assert any(onderwerp == "_:b0" for onderwerp, _ in analyse)
