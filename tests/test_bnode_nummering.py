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
    """Twee verse knopen in één quad (subject vóór object), een verse lus op zichzelf, een
    blanke knoop eerst als object, een lus op een al genummerde knoop, en een literaal."""
    a, p = pyoxigraph.NamedNode("http://x/a"), pyoxigraph.NamedNode("http://x/p")
    u, v, w = pyoxigraph.BlankNode(), pyoxigraph.BlankNode(), pyoxigraph.BlankNode()
    x, y, z = pyoxigraph.BlankNode(), pyoxigraph.BlankNode(), pyoxigraph.BlankNode()
    return [
        pyoxigraph.Quad(u, p, v),
        pyoxigraph.Quad(w, p, w),
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

    # Zonder `namen` spelt `_sleutel` zoals `clip.merge` een sleutel uit een deel leest
    # (`_:` plus de naam): zo toetst deze kolom ook dat het sleutelformaat één is.
    deterministisch = [(_sleutel(q.subject), _sleutel(q.object)) for q in _hernummerd(quads)]

    assert analyse == schrijfpass == deterministisch
    if bron == "eigen":
        assert analyse[:2] == [("_:b0", "_:b1"), ("_:b2", "_:b2")]
