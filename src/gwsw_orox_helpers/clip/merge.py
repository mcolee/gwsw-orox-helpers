"""Samenvoegen: de delen weer tot de bron.

Twee rondes over de delen. `_scan_delen` verzamelt de knipstukken en wijst aan wat in meer
dan een deel kan staan; `_samengevoegd` levert daarna de triples ontdubbeld, ontknipt en
zonder knipmerken. Waarom de blanke knopen hier hun naam uit de delen houden en niet
opnieuw genummerd worden, staat in de docstring van `gwsw_orox_helpers.clip`.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pyoxigraph

from gwsw_orox_helpers.clip.termen import (
    _GML_TYPE,
    _HAS_VALUE_KNOOP,
    KNIP,
    KNIP_PREFIX,
    _gml_waarde,
    _term,
)
from gwsw_orox_helpers.errors import DatasetError
from gwsw_orox_helpers.geometry import (
    GeometryError,
    coordinaattokens,
    parse_gml,
    tokens_per_punt,
    vervang_coordinaten,
)
from gwsw_orox_helpers.namen import HAS_VALUE
from gwsw_orox_helpers.schrijven import lees_orox


@dataclass
class _Scan:
    """Wat de eerste ronde over de delen oplevert: de stukken en wat ontdubbeld moet worden."""

    prefixen: dict[str, str] = field(default_factory=dict)
    # Sleutel van een stukknoop -> de herkomst waar hij bij hoort.
    herkomst_van: dict[str, str] = field(default_factory=dict)
    # Herkomst -> volgnummer -> (coordinatentekst, ingevoegd_einde).
    stukken: dict[str, dict[int, tuple[str, bool]]] = field(default_factory=dict)
    # Herkomst -> de GML-literaal van het eerste stuk; die levert het omhulsel.
    sjabloon: dict[str, str] = field(default_factory=dict)
    aantallen: dict[str, set[int]] = field(default_factory=dict)
    # Subjecten waarvan de triples in meer dan een deel kunnen staan.
    ontdubbelen: set[str] = field(default_factory=set)


def _scan_delen(delen: Sequence[Path]) -> _Scan:
    """Eerste ronde over de delen: knipstukken verzamelen en dubbele subjecten aanwijzen.

    De sleutel van een term is hier zijn IRI, of `_:<naam>` voor een blanke knoop. Anders
    dan bij het knippen worden die blanke knopen *niet* hernummerd: de clip heeft ze een
    vaste naam gegeven en die naam is precies de identiteit die de delen delen. De twee
    takken staan uitgeschreven en niet in een hulpfunctie per term: deze lus en die van
    `_samengevoegd` stellen de vraag samen vier keer per quad, op de delen van De Wolden
    en Hoogeveen zeven en een half miljoen keer.
    """
    scan = _Scan()
    gezien: set[str] = set()
    merken: dict[str, dict[str, str]] = {}
    verwijzers: dict[str, set[str]] = {}
    named_node = pyoxigraph.NamedNode
    blank_node = pyoxigraph.BlankNode
    literal = pyoxigraph.Literal

    for index, pad in enumerate(delen):
        geopend = lees_orox(pad)
        if index == 0:
            scan.prefixen = {
                naam: iri for naam, iri in geopend.prefixen.items() if naam != KNIP_PREFIX
            }
        hier: set[str] = set()
        for quad in geopend.quads:
            subject_in = quad.subject
            if isinstance(subject_in, named_node):
                onderwerp = subject_in.value
            else:
                assert isinstance(subject_in, blank_node)  # een subject is nooit een literaal
                onderwerp = f"_:{subject_in.value}"
            hier.add(onderwerp)
            predicaat = quad.predicate.value
            object_in = quad.object
            if predicaat.startswith(KNIP) and isinstance(object_in, literal):
                merken.setdefault(onderwerp, {})[predicaat] = object_in.value
            elif predicaat == HAS_VALUE:
                gml = _gml_waarde(object_in)
                if gml is not None:
                    scan.sjabloon.setdefault(onderwerp, gml)
            voorwerp: str | None
            if isinstance(object_in, named_node):
                voorwerp = object_in.value
            elif isinstance(object_in, blank_node):
                voorwerp = f"_:{object_in.value}"
            else:
                voorwerp = None
            if voorwerp is not None and "__knip" in voorwerp:
                verwijzers.setdefault(voorwerp, set()).add(onderwerp)
        for sleutel in hier:
            if sleutel in gezien:
                scan.ontdubbelen.add(sleutel)
            gezien.add(sleutel)

    _verwerk_merken(scan, merken)

    # Een triple die naar een stukknoop wees, wijst na het herschrijven naar de herkomst;
    # zulke triples staan dan in elk deel dat een stuk draagt en moeten ontdubbeld worden.
    scan.ontdubbelen |= set(scan.stukken)
    for stukknoop in scan.herkomst_van:
        scan.ontdubbelen |= verwijzers.get(stukknoop, set())
    return scan


def _verwerk_merken(scan: _Scan, merken: dict[str, dict[str, str]]) -> None:
    """Vertaalt de knipmerken naar de stukkenadministratie en controleert of ze compleet is."""
    for knoop, merk in merken.items():
        herkomst = merk.get(f"{KNIP}herkomst")
        if herkomst is None:
            continue
        try:
            volgnummer = int(merk[f"{KNIP}volgnummer"])
            aantal = int(merk[f"{KNIP}aantal"])
        except (KeyError, ValueError) as fout:
            raise DatasetError(
                f"knipmerk op {knoop!r} is onvolledig of onleesbaar ({fout}); zonder volgnummer "
                f"en aantal is de geknipte geometrie niet terug te leggen."
            ) from fout
        tekst = scan.sjabloon.get(knoop)
        if tekst is None:
            raise DatasetError(
                f"knipstuk {knoop!r} draagt geen GML-geometrie; er valt niets aaneen te naaien."
            )
        scan.herkomst_van[knoop] = herkomst
        scan.aantallen.setdefault(herkomst, set()).add(aantal)
        rij = scan.stukken.setdefault(herkomst, {})
        # De getallen van het stuk blijven de brontekst; alleen de scheiders gaan hier al
        # op een enkele spatie, want `_hersteld` splitst deze tekst toch weer op witruimte.
        rij[volgnummer] = (
            " ".join(coordinaattokens(tekst)),
            merk.get(f"{KNIP}ingevoegdEinde") == "true",
        )
        scan.sjabloon.setdefault(herkomst, tekst)

    for herkomst, rij in scan.stukken.items():
        aantallen = scan.aantallen[herkomst]
        if len(aantallen) != 1:
            raise DatasetError(
                f"de stukken van {herkomst!r} noemen verschillende aantallen {sorted(aantallen)}; "
                f"dat zijn stukken uit verschillende knipbeurten."
            )
        aantal = next(iter(aantallen))
        if sorted(rij) != list(range(aantal)):
            ontbreekt = sorted(set(range(aantal)) - set(rij))
            raise DatasetError(
                f"van {herkomst!r} ontbreken de stukken {ontbreekt}; de delen zijn niet compleet "
                f"en de geometrie zou korter terugkomen dan ze was."
            )


def _samengevoegd(delen: Sequence[Path], scan: _Scan) -> Iterator[pyoxigraph.Triple]:
    """De triples van alle delen samen: ontdubbeld, ontknipt en zonder knipmerken.

    De sleutels worden hier op dezelfde manier gelezen als in `_scan_delen`, en om
    dezelfde reden uitgeschreven.
    """
    gezien: set[tuple[str, str, str]] = set()
    geschreven: set[str] = set()
    # Vaste tabellen en typen als lokale naam; alles hieronder draait per quad van elk deel.
    herkomst_van = scan.herkomst_van
    ontdubbelen = scan.ontdubbelen
    named_node = pyoxigraph.NamedNode
    blank_node = pyoxigraph.BlankNode
    triple = pyoxigraph.Triple
    for pad in delen:
        for quad in lees_orox(pad).quads:
            predicaat = quad.predicate.value
            if predicaat.startswith(KNIP):
                continue
            subject_in = quad.subject
            if isinstance(subject_in, named_node):
                onderwerp = subject_in.value
            else:
                assert isinstance(subject_in, blank_node)  # een subject is nooit een literaal
                onderwerp = f"_:{subject_in.value}"
            herkomst = herkomst_van.get(onderwerp)
            subject: pyoxigraph.NamedNode | pyoxigraph.BlankNode
            if herkomst is not None:
                if predicaat == HAS_VALUE and _gml_waarde(quad.object) is not None:
                    if herkomst not in geschreven:
                        geschreven.add(herkomst)
                        yield _hersteld(herkomst, scan)
                    continue
                subject = _term(herkomst)
            else:
                # De term staat er al: `_term(onderwerp)` zou hem letterlijk opnieuw
                # opbouwen uit de tekst die er zojuist uit kwam.
                subject = subject_in

            object_in = quad.object
            if isinstance(object_in, named_node):
                doel = herkomst_van.get(object_in.value)
            elif isinstance(object_in, blank_node):
                doel = herkomst_van.get(f"_:{object_in.value}")
            else:
                doel = None
            object_ = _term(doel) if doel is not None else object_in

            sleutel = herkomst if herkomst is not None else onderwerp
            if sleutel in ontdubbelen:
                merk = (sleutel, predicaat, _objectsleutel(object_))
                if merk in gezien:
                    continue
                gezien.add(merk)
            yield triple(subject, quad.predicate, object_)


def _objectsleutel(term: object) -> str:
    """Een tekstvorm van een object die twee gelijke objecten gelijk maakt."""
    if isinstance(term, pyoxigraph.Literal):
        return "|".join(("L", term.datatype.value, term.language or "", term.value))
    if isinstance(term, pyoxigraph.BlankNode):
        return f"B{term.value}"
    return f"N{getattr(term, 'value', term)}"


def _hersteld(herkomst: str, scan: _Scan) -> pyoxigraph.Triple:
    """De oorspronkelijke geometrie: de stukken aaneen, het ingevoegde knippunt eruit."""
    sjabloon = scan.sjabloon[herkomst]
    stap = _stapgrootte(sjabloon)
    rij = scan.stukken[herkomst]
    tokens: list[str] = []
    for volgnummer in sorted(rij):
        tekst, ingevoegd_einde = rij[volgnummer]
        punten = tekst.split()
        # Van elk stuk na het eerste vervalt het eerste punt (dat herhaalt het laatste punt
        # van het vorige stuk) en van elk stuk dat op een ingevoegd knippunt eindigt het
        # laatste. Wat overblijft is letterlijk de tokenreeks van de bron.
        if volgnummer > 0:
            punten = punten[stap:]
        if ingevoegd_einde:
            punten = punten[: max(len(punten) - stap, 0)]
        tokens.extend(punten)
    literal = vervang_coordinaten(sjabloon, " ".join(tokens))
    return pyoxigraph.Triple(
        _term(herkomst), _HAS_VALUE_KNOOP, pyoxigraph.Literal(literal, datatype=_GML_TYPE)
    )


def _stapgrootte(sjabloon: str) -> int:
    """Het aantal getallen per punt, op dezelfde manier bepaald als bij het knippen.

    Niet uit de `srsDimension` gelezen maar uit de verhouding tussen het aantal tokens en
    het aantal punten dat `parse_gml` erin ziet -- `geometry.tokens_per_punt`, dezelfde
    functie die `_knip_lijn` de stukken mee verdeelde. Zou de literaal geen srsDimension
    dragen, dan tellen beide kanten en komen ze op hetzelfde uit, en blijft het aaneen
    naaien sluitend.

    Komt die verhouding niet rond, dan is er niets te raden: het aaneen naaien snoeit per
    punt van de tokenreeks, dus een stap van 2 waar de bron er 3 bedoelde levert een
    geometrie op die niemand ooit geschreven heeft -- en dat stilzwijgend. Een stuk dat de
    clip zelf schreef komt hier nooit; wat hier komt is een deel van elders.

    Het puntental komt hier vandaan en niet uit `tokens_per_punt` zelf: een vlak (dat geen
    `.coords` heeft) en een onleesbare literaal horen hier geen fout uit shapely te geven
    maar de melding hieronder, met de getallen erin waarmee de auteur ziet waarom.
    """
    try:
        punten = len(parse_gml(sjabloon).coords)
    except (GeometryError, NotImplementedError):
        punten = 0
    stap = tokens_per_punt(sjabloon, punten)
    if stap is not None:
        return stap
    raise DatasetError(
        f"uit {sjabloon!r} is niet af te lezen hoeveel getallen er op een punt gaan "
        f"({len(coordinaattokens(sjabloon))} coordinaatwaarden op {punten} punten); het "
        f"aaneen naaien van de stukken zou dan op de verkeerde plaats snoeien."
    )
