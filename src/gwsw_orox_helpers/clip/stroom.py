"""Schrijven: de stroom per deel.

De tweede tot en met de N+1-de lezing van de bron loopt hier langs. Sinds issue #64 rekent
deze fase niets meer per quad opnieuw uit: het `_Plan` draagt een positietabel die per
stroompositie het effectieve masker en een herschrijf-vlag bewaart. Staat de vlag uit -- de
overgrote meerderheid, en op een bron zonder blanke knopen alles -- dan gaat de bron-quad
ongewijzigd de deur uit (Turtle kent geen benoemde grafen, dus byte-gelijk aan de gelijke
Triple). Staat hij aan, dan komen waar een geknipte geometrieknoop stond de stukken met hun
knipmerken, en krijgen blanke knopen hun vaste stroomvolgorde-naam. Wat er wel en niet over
de grens mag blijven wijzen, staat in de docstring van `gwsw_orox_helpers.clip`.

Scherp geformuleerd is de lui-belofte van de schrijfweg: **de bron zelf komt nooit in het
geheugen; het plan mag een positietabel van O(1) byte per quad dragen.** De positietabel
hierboven (issue #64) is per constructie conform die belofte -- een masker-byte plus een
vlag per stroompositie, geen quads. Een variant die de hele bron één keer als graaf of als
`str` in het geheugen zou zetten, keert de belofte om en hoort hier dus niet thuis.
"""

from __future__ import annotations

import collections
import itertools
from collections.abc import Iterable, Iterator
from typing import Final

import pyoxigraph

from gwsw_orox_helpers.clip.knip import _Stuk
from gwsw_orox_helpers.clip.plan import _nummer, _Plan
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
from gwsw_orox_helpers.errors import KnipError
from gwsw_orox_helpers.geometry import vervang_coordinaten


def _deelstroom(
    quads: Iterable[pyoxigraph.Quad], plan: _Plan, deel: int, termen: _Kniptermen
) -> Iterator[pyoxigraph.Quad | pyoxigraph.Triple]:
    """De triples die naar dit deel gaan, uit de quadstroom van de bron.

    Eerst het merk `knip:geknipt` op de houders van een geknipte geometrie, dan de bron zoals
    de positietabel van het plan (`posmasker`, `herschrijf`) hem verdeelt (`_reeksen`). Een
    gewone quad gaat ongewijzigd de deur uit: Turtle kent geen benoemde grafen, dus een
    default-graaf-`Quad` schrijft byte-gelijk aan de gelijke `Triple`. Zo levert de fase een
    gemengde Quad/Triple-stroom, die de serializer aanvaardt.
    """
    bit = 1 << deel
    kop = [
        pyoxigraph.Triple(_term(blok), _GEKNIPT, _WAAR)
        for blok, masker in plan.geknipte_houders.items()
        if masker & bit
    ]
    return itertools.chain(
        kop, itertools.chain.from_iterable(_reeksen(iter(quads), plan, deel, termen))
    )


def _reeksen(
    bron: Iterator[pyoxigraph.Quad], plan: _Plan, deel: int, termen: _Kniptermen
) -> Iterator[Iterable[pyoxigraph.Quad | pyoxigraph.Triple]]:
    """De bron in reeksen: een `islice` per doorgeefreeks, een lijst per herschrijfquad.

    Python loopt hier niet per quad (issue #84). `naar_deel` heeft per positie een 1 als de
    quad naar dit deel gaat; de volgende reeksgrens en de volgende herschrijfpositie zoekt
    `bytes.find`, in C. Een doorgeefreeks gaat als `islice` van de bron naar de serializer,
    een overgeslagen reeks loopt in C leeg (`deque` met `maxlen=0`). Alleen een
    herschrijfquad (blanke knoop of geknipte geometrie) gaat door Python: `_nummer` geeft
    zijn blanke knopen hun stroomvolgorde-naam, ook als hij niet naar dit deel gaat, zodat
    die naam niet van het deel afhangt.

    Alle reeksen delen één `bron`-iterator. De afnemer moet een reeks dus helemaal leeglopen
    voordat hij de volgende vraagt; `itertools.chain.from_iterable` in `_deelstroom` doet dat.

    Telt de bron meer quads dan de positietabel, of houdt hij op vóór een herschrijfquad,
    dan is het bestand sinds de analyseronde veranderd: dat is een `KnipError`.
    """
    bit = 1 << deel
    posmasker = plan.posmasker
    if posmasker.typecode == "B":
        tabel = bytes(1 if waarde & bit else 0 for waarde in range(256))
        naar_deel = posmasker.tobytes().translate(tabel)
    else:  # meer dan 8 vlakken: het masker past niet in een byte
        naar_deel = bytes(1 if masker & bit else 0 for masker in posmasker)
    herschrijf = plan.herschrijf
    aantal = len(naar_deel)
    labels: dict[str, str] = {}
    teller = itertools.count()

    positie = 0
    while positie < aantal:
        grens = herschrijf.find(1, positie)
        if grens == -1:
            grens = aantal
        while positie < grens:
            doorgeven = naar_deel[positie]
            einde = naar_deel.find(b"\x00" if doorgeven else b"\x01", positie, grens)
            if einde == -1:
                einde = grens
            reeks = itertools.islice(bron, einde - positie)
            if doorgeven:
                yield reeks
            else:
                collections.deque(reeks, maxlen=0)
            positie = einde
        if positie == aantal:
            break
        quad = next(bron, None)
        if quad is None:
            raise KnipError(_VERANDERD)
        _nummer(quad, labels, teller)
        if naar_deel[positie]:
            yield list(_herschreven(quad, plan, deel, termen, labels))
        positie += 1
    if next(bron, None) is not None:
        raise KnipError(_VERANDERD)


_VERANDERD: Final = (
    "de bron telt een ander aantal quads dan bij de analyseronde van de clip; is het bestand "
    "tussen de lezingen veranderd?"
)


def _herschreven(
    quad: pyoxigraph.Quad,
    plan: _Plan,
    deel: int,
    termen: _Kniptermen,
    labels: dict[str, str],
) -> Iterator[pyoxigraph.Triple]:
    """Het herschrijfpad: blanke knopen krijgen hun vaste naam, geknipte geometrie haar stukken."""
    stukken_van = plan.stukken
    randpredicaten = termen.randpredicaten
    has_value = termen.has_value
    has_value_knoop = termen.has_value_knoop
    named_node = pyoxigraph.NamedNode
    blank_node = pyoxigraph.BlankNode
    triple = pyoxigraph.Triple
    subject = quad.subject
    if isinstance(subject, named_node):
        onderwerp = subject.value
    elif isinstance(subject, blank_node):
        onderwerp = labels[subject.value]
    else:  # pragma: no cover -- een subject is nooit een literaal of RDF-ster-triple
        raise AssertionError("een subject is nooit een literaal of RDF-ster-triple")
    object_ = quad.object
    if isinstance(object_, named_node):
        voorwerp: str | None = object_.value
    elif isinstance(object_, blank_node):
        voorwerp = labels[object_.value]
    else:
        voorwerp = None
    predicaat = quad.predicate.value

    # Blanke knopen gaan met hun vaste naam de deur uit; zie de docstring van het package.
    subject_uit: pyoxigraph.NamedNode | pyoxigraph.BlankNode = (
        subject if isinstance(subject, named_node) else _term(onderwerp)
    )
    object_uit = (
        _term(voorwerp) if voorwerp is not None and isinstance(object_, blank_node) else object_
    )

    eigen_stukken = stukken_van.get(onderwerp)
    andere_stukken = stukken_van.get(voorwerp) if voorwerp is not None else None
    if eigen_stukken is None and andere_stukken is None:
        # Een herschrijf-quad zonder geknipte geometrie: alleen een blanke knoop kreeg
        # een vaste naam. Er komt geen stukknoop in de plaats en er valt niets te merken.
        yield triple(subject_uit, quad.predicate, object_uit)
        return

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
        return
    if voorwerpen == []:
        if predicaat in randpredicaten:
            # Een houder/onderdeel-rand naar een geknipte geometrie zonder stuk hier:
            # niet schrijven, anders zou er een naam in dit deel hangen waar niets bij
            # staat. Kwijt raakt de triple er niet van, want de rand wordt naar de
            # vlakken van het onderdeel geschreven en daar staat wel een stuk.
            return
        # Elk ander predicaat heeft die tweede thuisbasis niet: deze triple staat alleen
        # hier, en overslaan zou hem uit de hereniging laten verdwijnen. Hij blijft dus
        # staan en wijst naar de ongeknipte naam -- dezelfde keuze als de
        # `hasConnection` die na de knip naar de put aan de overkant blijft wijzen.
        voorwerpen = None
    for subject_out, stuk in onderwerpen if onderwerpen is not None else ((subject_uit, None),):
        if stuk is not None and predicaat == has_value:
            # Pas hier naar de GML-tekst vragen: alleen een stuk van een geknipte
            # geometrie doet er iets mee, en dat is een handvol van de miljoenen quads.
            gml = _gml_waarde(quad.object)
            if gml is not None:
                yield from _knipmerken(subject_out, onderwerp, gml, stuk, plan, has_value_knoop)
                continue
        for object_out, _ in voorwerpen if voorwerpen is not None else ((object_uit, None),):
            yield triple(subject_out, quad.predicate, object_out)


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
