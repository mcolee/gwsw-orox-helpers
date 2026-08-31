"""Schrijven: de stroom per deel.

De tweede tot en met de N+1-de lezing van de bron loopt hier langs: het `_Plan` zegt per
term of hij in dit deel hoort, en waar een geknipte geometrieknoop stond komen de stukken
met hun knipmerken. Wat er wel en niet over de grens mag blijven wijzen, staat in de
docstring van `gwsw_orox_helpers.clip`.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

import pyoxigraph

from gwsw_orox_helpers.clip.knip import _Stuk
from gwsw_orox_helpers.clip.plan import _genummerd, _Plan
from gwsw_orox_helpers.clip.termen import (
    _AANTAL,
    _GEKNIPT,
    _GML_TYPE,
    _HERKOMST,
    _INGEVOEGD_EINDE,
    _INTEGER,
    _VOLGNUMMER,
    _WAAR,
    _gml_waarde,
    _Kniptermen,
    _stukterm,
    _term,
)
from gwsw_orox_helpers.geometry import vervang_coordinaten


def _deelstroom(
    quads: Iterable[pyoxigraph.Quad], plan: _Plan, deel: int, termen: _Kniptermen
) -> Iterator[pyoxigraph.Triple]:
    """De triples die naar dit deel gaan, uit de quadstroom van de bron."""
    bit = 1 << deel
    for blok, masker in plan.geknipte_houders.items():
        if masker & bit:
            yield pyoxigraph.Triple(_term(blok), _GEKNIPT, _WAAR)

    # De vaste tabellen en typen krijgen een lokale naam: hier onder draait alles per quad
    # van de bron, en dat zijn er op de export van De Wolden en Hoogeveen 1,9 miljoen.
    maskers = plan.maskers
    stukken_van = plan.stukken
    randpredicaten = termen.randpredicaten
    has_value = termen.has_value
    has_value_knoop = termen.has_value_knoop
    named_node = pyoxigraph.NamedNode
    blank_node = pyoxigraph.BlankNode
    triple = pyoxigraph.Triple

    for quad, onderwerp, voorwerp in _genummerd(quads):
        if not maskers.get(onderwerp, 0) & bit:
            continue
        predicaat = quad.predicate.value
        if voorwerp is not None and predicaat in randpredicaten:
            # De rand tussen houder en onderdeel gaat naar de vlakken van het onderdeel; de
            # houder staat daar altijd ook, dus geen van beide einden komt los te hangen.
            ander = maskers.get(voorwerp, 0)
            if ander and not ander & bit:
                continue

        # Blanke knopen gaan met hun vaste naam de deur uit; zie de docstring van het package.
        subject_uit: pyoxigraph.NamedNode | pyoxigraph.BlankNode = (
            quad.subject if isinstance(quad.subject, named_node) else _term(onderwerp)
        )
        object_uit = (
            _term(voorwerp)
            if voorwerp is not None and isinstance(quad.object, blank_node)
            else quad.object
        )

        eigen_stukken = stukken_van.get(onderwerp)
        andere_stukken = stukken_van.get(voorwerp) if voorwerp is not None else None
        if eigen_stukken is None and andere_stukken is None:
            # Verreweg de meeste triples: geen van beide einden is een geknipte
            # geometrieknoop, dus er komt geen stukknoop in de plaats en er valt niets te
            # merken. Alles hieronder zou dan uitkomen op deze ene triple.
            yield triple(subject_uit, quad.predicate, object_uit)
            continue

        onderwerpen = _stuktermen(plan, onderwerp, deel) if eigen_stukken is not None else None
        voorwerpen = (
            _stuktermen(plan, voorwerp, deel)
            if voorwerp is not None and andere_stukken is not None
            else None
        )
        if onderwerpen == []:
            # Een geknipte geometrieknoop zonder stuk in dit deel. Dat kan: een blok kan in
            # een vlak staan om een andere geometrie (de orientatie draagt naast de lijn ook
            # een punt) terwijl de lijn daar geen stuk heeft. Dan hoort hier niet zijn hele
            # ongeknipte geometrie te staan.
            continue
        if voorwerpen == []:
            if predicaat in randpredicaten:
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
            if stuk is not None and predicaat == has_value:
                # Pas hier naar de GML-tekst vragen: alleen een stuk van een geknipte
                # geometrie doet er iets mee, en dat is een handvol van de miljoenen quads.
                gml = _gml_waarde(quad.object)
                if gml is not None:
                    yield from _knipmerken(subject, onderwerp, gml, stuk, plan, has_value_knoop)
                    continue
            for object_, _ in voorwerpen if voorwerpen is not None else ((object_uit, None),):
                yield triple(subject, quad.predicate, object_)


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
    has_value_knoop: pyoxigraph.NamedNode,
) -> Iterator[pyoxigraph.Triple]:
    """De geometrie van een stuk plus de merken waarmee `merge_orox` hem terugvindt."""
    geknipt = pyoxigraph.Literal(vervang_coordinaten(literal, stuk.coordinaten), datatype=_GML_TYPE)
    yield pyoxigraph.Triple(subject, has_value_knoop, geknipt)
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
