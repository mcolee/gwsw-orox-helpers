"""De eigen naamruimte van de clip: de knipmerken, de vaste termen en de stuknamen.

Het blad van het package -- hij importeert geen zuster. Wat hier staat is de spelling die
de knip en de hereniging allebei moeten kennen: de `knip:`-predicaten waarmee een deel zijn
geknipte geometrie draagt, de namen die de clip zelf mint (`<origineel>__knip<k>`) en de
regex waarmee zo'n naam weer te herkennen is. Het volledige verhaal staat in de docstring
van `gwsw_orox_helpers.clip`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

import pyoxigraph

from gwsw_orox_helpers import namen
from gwsw_orox_helpers.namen import GML_LITERAL, XSD

# De eigen naamruimte voor de knipmerken. Ze staan alleen in de geknipte delen; `merge_orox`
# gooit elke triple met een predicaat uit deze naamruimte weg.
KNIP: Final = "https://github.com/mcolee/gwsw-orox-helpers/ns/clip#"
KNIP_PREFIX: Final = "knip"

_GML_TYPE: Final = pyoxigraph.NamedNode(GML_LITERAL)
_HERKOMST: Final = pyoxigraph.NamedNode(f"{KNIP}herkomst")
_VOLGNUMMER: Final = pyoxigraph.NamedNode(f"{KNIP}volgnummer")
_AANTAL: Final = pyoxigraph.NamedNode(f"{KNIP}aantal")
_INGEVOEGD_EINDE: Final = pyoxigraph.NamedNode(f"{KNIP}ingevoegdEinde")
_GEKNIPT: Final = pyoxigraph.NamedNode(f"{KNIP}geknipt")
_INTEGER: Final = pyoxigraph.NamedNode(f"{XSD}integer")
_BOOLEAN: Final = pyoxigraph.NamedNode(f"{XSD}boolean")
_WAAR: Final = pyoxigraph.Literal("true", datatype=_BOOLEAN)

# De namen die de clip zelf mint, hangen deze staart achter de sleutel van de bron. Een bron
# die zulke namen al draagt zou na de hereniging met zichzelf samenvallen; dat wordt geweigerd.
_KNIPSTAART: Final = re.compile(r"__knip\d+\Z")


@dataclass(frozen=True)
class _Kniptermen:
    """De GWSW-predicaten die de clip uit de bron afleidt (issue #32).

    De knipmerken (`knip:`), de GML-typering (`geo:gmlLiteral`) en de stuknamen zijn
    versie-onafhankelijk en staan als vaste constanten hierboven. De GWSW-predicaten
    waarop de knip toewijst -- de hasAspect/hasPart-randen, hasConnection en hasValue --
    dragen wél de versie van de bron: een clip op een 1.7-export vergelijkt tegen
    `.../1.7/totaal/hasValue`, en het herstelde geometrie-triple wordt met datzelfde
    predicaat weer weggeschreven. `clip_orox` en `merge_orox` leiden de basis uit de bron
    af (`namen.basis_uit_prefixen`, met de IRI's als terugval) en bouwen deze verzameling.
    """

    basis: str
    has_value: str
    has_value_knoop: pyoxigraph.NamedNode
    has_connection: str
    houder_naar_onderdeel: frozenset[str]
    onderdeel_naar_houder: frozenset[str]
    randpredicaten: frozenset[str]


def _kniptermen(basis: str) -> _Kniptermen:
    """De knip-predicaten van een bron-basis; 1.6 is de default en terugval."""
    t = namen.termen_voor(basis)
    houder_naar_onderdeel = frozenset({t.has_aspect, t.has_part})
    onderdeel_naar_houder = frozenset({t.is_aspect_of, t.is_part_of})
    return _Kniptermen(
        basis=basis,
        has_value=t.has_value,
        has_value_knoop=pyoxigraph.NamedNode(t.has_value),
        has_connection=t.has_connection,
        houder_naar_onderdeel=houder_naar_onderdeel,
        onderdeel_naar_houder=onderdeel_naar_houder,
        randpredicaten=houder_naar_onderdeel | onderdeel_naar_houder,
    )


def _term(sleutel: str) -> pyoxigraph.NamedNode | pyoxigraph.BlankNode:
    """De term achter een sleutel: een blanke knoop bij `_:`, anders een IRI."""
    if sleutel.startswith("_:"):
        return pyoxigraph.BlankNode(sleutel[2:])
    return pyoxigraph.NamedNode(sleutel)


def _stukterm(sleutel: str, volgnummer: int) -> pyoxigraph.NamedNode | pyoxigraph.BlankNode:
    """De knoop waar het `volgnummer`-de stuk van deze geometrie op komt te staan."""
    return _term(f"{sleutel}__knip{volgnummer}")


def _gml_waarde(term: object) -> str | None:
    """De tekst van een GML-literaal, of None als deze term er geen is."""
    if isinstance(term, pyoxigraph.Literal) and term.datatype.value == GML_LITERAL:
        return term.value
    return None
