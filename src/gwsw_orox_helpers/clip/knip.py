"""Geometrie: een GML-literaal op de vlakken plaatsen en zo nodig doorknippen.

De fase die van een geometrie het bitmasker van vlakken maakt, en van een lijn die de grens
kruist de `_Stuk`-en waarin hij uiteenvalt. De stukken zijn tekstplakjes uit de posList van
de bron en geen teruggeschreven shapely-coordinaten -- waarom dat zo is, en wat er
nadrukkelijk *niet* geknipt wordt, staat in de docstring van `gwsw_orox_helpers.clip`.

Het snijden zelf gebeurt met de tekstkant van `geometry` (`coordinaattokens`,
`tokens_per_punt`, `vervang_coordinaten`) en niet met een eigen regex: de knip hoort een
literaal precies zo te lezen als de leeslaag hem leest, anders wordt een GML-vormvariant
hier stil iets anders dan daar. `merge` snijdt met dezelfde drie terug.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Final

from shapely.geometry import LineString, Point
from shapely.geometry.base import BaseGeometry

from gwsw_orox_helpers.clip.grenzen import _Vlak
from gwsw_orox_helpers.errors import DatasetError
from gwsw_orox_helpers.geometry import (
    GeometryError,
    coordinaattokens,
    parse_gml,
    parse_gml_z,
    tokens_per_punt,
    vervang_coordinaten,
)

# Afstandstolerantie langs een lijn, in meters. Valt een kruispunt hierbinnen op een
# bestaande vertex, dan wordt er geen punt ingevoegd; valt het op het begin of het eind
# van de lijn, dan is er niets te knippen. RD-coordinaten liggen rond 2e5 m en float64
# houdt daar zo'n 1e-11 m over, dus 1e-6 m is ruim en nog altijd onzichtbaar klein.
_TOLERANTIE: Final = 1e-6

# Het aantal decimalen waarmee een ingevoegd knippunt geschreven wordt. Alleen zichtbaar in
# de delen: bij de hereniging vervalt het punt, dus het raakt de round-trip niet.
_KNIPPUNT_DECIMALEN: Final = 3


@dataclass(frozen=True)
class _Stuk:
    """Een stuk van een doorgeknipte lijn, klaar om als GML weggeschreven te worden."""

    deel: int
    volgnummer: int
    coordinaten: str
    ingevoegd_einde: bool


def _plaats(
    literal: str, vlakken: tuple[_Vlak, ...], *, knip: bool = True
) -> tuple[int, tuple[_Stuk, ...] | None]:
    """Het bitmasker van vlakken voor deze GML-literaal, en zo nodig de knipstukken."""
    try:
        meetkunde = parse_gml(literal)
    except GeometryError:
        # Een onleesbare geometrie zaait niets; het blok erft dan van zijn houder. De
        # leeslaag meldt zo'n literaal in `GwswDataset.geometry_errors`; de clip hoeft er
        # niet nog een tweede keer over te vallen.
        return 0, None
    if meetkunde.is_empty:
        return 0, None
    if isinstance(meetkunde, LineString) and len(meetkunde.coords) > 1:
        if knip:
            return _knip_lijn(literal, meetkunde, vlakken)
        # Ongeknipt gaat een lijn heel naar elk vlak dat hij raakt; een representatief punt
        # zou hem in een van beide vlakken laten verdwijnen terwijl hij in allebei ligt.
        return _heel(meetkunde, vlakken), None
    return 1 << _vlak_van(meetkunde.representative_point(), vlakken), None


def _vlak_van(punt: Point, vlakken: tuple[_Vlak, ...]) -> int:
    """Het vlak waarin dit punt valt; anders het dichtstbijzijnde vlak.

    De terugval op het dichtstbijzijnde vlak is er zodat er nooit een object buiten de
    boot valt: een grenslaag dekt zelden precies alles wat een export bevat, en een
    object dat nergens heen kan zou bij de hereniging ontbreken.
    """
    for index, vlak in enumerate(vlakken):
        if vlak.voorbereid.covers(punt):
            return index
    return min(range(len(vlakken)), key=lambda index: vlakken[index].meetkunde.distance(punt))


def _knip_lijn(
    literal: str, lijn: LineString, vlakken: tuple[_Vlak, ...]
) -> tuple[int, tuple[_Stuk, ...] | None]:
    """Verdeelt een lijn over de vlakken; knipt hem als hij de grens kruist."""
    for index, vlak in enumerate(vlakken):
        if vlak.voorbereid.covers(lijn):
            return 1 << index, None

    tokens = coordinaattokens(literal)
    punten = list(lijn.coords)
    # `stap` is het aantal getallen per punt: geteld, en met opzet niet uit de srsDimension
    # gelezen (zie `tokens_per_punt`). `merge._stapgrootte` telt straks hetzelfde.
    stap = tokens_per_punt(literal, len(punten))
    if stap is None or stap not in (2, 3):
        # Zonder een sluitende tokenverdeling valt er geen tekstplakje te knippen, en bij
        # een andere verhouding dan 2 of 3 getallen per punt zou het snijden op de
        # verkeerde plaats gebeuren; dan gaat de hele lijn naar elk vlak dat hij raakt.
        return _heel(lijn, vlakken), None
    if vervang_coordinaten(literal, " ".join(tokens)) != literal:
        # De hereniging zet de tokens met een enkele spatie aaneen en legt ze met
        # `vervang_coordinaten` terug -- precies de vergelijking hierboven. Komt daar niet
        # letterlijk de bron uit, dan draagt zij andere scheiders (dubbele spaties,
        # newlines, randspaties) en zouden de getallen wel exact terugkomen maar de tekst
        # eromheen niet; `merge(clip(bron))` is dan niet meer byte-gelijk aan de bron.
        # Zulke tekst wordt niet geknipt maar heel doorgegeven.
        return _heel(lijn, vlakken), None

    lengte = lijn.length
    afstanden = _vertexafstanden(punten)
    snedes = sorted(_snijafstanden(punten, afstanden, vlakken, lengte))
    segmenten = _segmenten(lijn, [0.0, *snedes, lengte], vlakken)
    if len(segmenten) < 2:
        return (1 << segmenten[0][0]) if segmenten else _heel(lijn, vlakken), None

    z_waarden = parse_gml_z(literal)
    stukken: list[_Stuk] = []
    masker = 0
    for volgnummer, (deel, begin, eind) in enumerate(segmenten):
        op_begin = _vertex_op(afstanden, begin)
        op_eind = _vertex_op(afstanden, eind)
        eerste = op_begin if op_begin is not None else _eerste_na(afstanden, begin)
        laatste = op_eind if op_eind is not None else _laatste_voor(afstanden, eind)
        # De uiteinden van de lijn liggen vast: het eerste stuk begint op de eerste vertex
        # en het laatste eindigt op de laatste. Dat is geen vanzelfsprekendheid zolang
        # `_vertex_op` de *eerste* vertex binnen de tolerantie aanwijst: valt het laatste
        # segment van de lijn korter uit dan een micrometer -- een herhaald eindpunt, en
        # dat komt in exports voor -- dan wijst hij naar de een-na-laatste en zou de
        # laatste vertex buiten elk stuk vallen. De hereniging leverde dan een kortere
        # geometrie op zonder ergens te klagen.
        if volgnummer == 0:
            eerste = 0
        if volgnummer == len(segmenten) - 1:
            laatste = len(afstanden) - 1

        rij: list[str] = []
        if volgnummer > 0 and op_begin is None:
            rij.extend(_knippunt(lijn, afstanden, z_waarden, stap, begin))
        for index in range(eerste, laatste + 1):
            rij.extend(tokens[index * stap : (index + 1) * stap])
        ingevoegd = volgnummer < len(segmenten) - 1 and op_eind is None
        if ingevoegd:
            rij.extend(_knippunt(lijn, afstanden, z_waarden, stap, eind))

        stukken.append(
            _Stuk(
                deel=deel,
                volgnummer=volgnummer,
                coordinaten=" ".join(rij),
                ingevoegd_einde=ingevoegd,
            )
        )
        masker |= 1 << deel
    return masker, tuple(stukken)


def _heel(lijn: LineString, vlakken: tuple[_Vlak, ...]) -> int:
    """Het masker van alle vlakken die deze lijn raakt; minstens een."""
    masker = 0
    for index, vlak in enumerate(vlakken):
        if vlak.voorbereid.intersects(lijn):
            masker |= 1 << index
    return masker or 1 << _vlak_van(lijn.representative_point(), vlakken)


def _vertexafstanden(punten: Sequence[tuple[float, ...]]) -> list[float]:
    """De afstand langs de lijn tot elke vertex."""
    afstanden = [0.0]
    for vorige, volgende in itertools.pairwise(punten):
        stap = Point(vorige[0], vorige[1]).distance(Point(volgende[0], volgende[1]))
        afstanden.append(afstanden[-1] + stap)
    return afstanden


def _snijafstanden(
    punten: Sequence[tuple[float, ...]],
    afstanden: list[float],
    vlakken: tuple[_Vlak, ...],
    lengte: float,
) -> set[float]:
    """De afstanden langs de lijn waar hij een vlakgrens kruist.

    Segment voor segment, en niet met `LineString.project` op de hele lijn: die geeft
    van een punt de *dichtstbijzijnde* plaats op de lijn, en een leiding die over
    zichzelf terugloopt raakt dezelfde grens dan twee keer op dezelfde plaats. De ene
    kruising zou dan verdwijnen en het stuk ertussen aan de verkeerde kant belanden.
    Binnen een recht segment is `project` wel eenduidig.
    """
    gevonden: set[float] = set()
    for index, (vorige, volgende) in enumerate(itertools.pairwise(punten)):
        segment = LineString([vorige[:2], volgende[:2]])
        if segment.length <= _TOLERANTIE:
            continue
        for vlak in vlakken:
            for punt in _puntjes(segment.intersection(vlak.meetkunde.boundary)):
                afstand = afstanden[index] + segment.project(punt)
                if _TOLERANTIE < afstand < lengte - _TOLERANTIE:
                    gevonden.add(afstand)
    return gevonden


def _puntjes(meetkunde: BaseGeometry) -> Iterator[Point]:
    """De losse punten uit een doorsnede: punten zelf, en de einden van lijnstukken."""
    if meetkunde.is_empty:
        return
    if isinstance(meetkunde, Point):
        yield meetkunde
    elif hasattr(meetkunde, "geoms"):
        for deel in meetkunde.geoms:
            yield from _puntjes(deel)
    elif isinstance(meetkunde, LineString):
        punten = list(meetkunde.coords)
        yield Point(punten[0])
        yield Point(punten[-1])


def _segmenten(
    lijn: LineString, grenzen: list[float], vlakken: tuple[_Vlak, ...]
) -> list[tuple[int, float, float]]:
    """De stukken tussen de kruispunten, elk met zijn vlak; gelijke buren worden samengevoegd."""
    segmenten: list[tuple[int, float, float]] = []
    for begin, eind in itertools.pairwise(grenzen):
        if eind - begin <= _TOLERANTIE:
            continue
        deel = _vlak_van(lijn.interpolate((begin + eind) / 2), vlakken)
        if segmenten and segmenten[-1][0] == deel:
            segmenten[-1] = (deel, segmenten[-1][1], eind)
        else:
            segmenten.append((deel, begin, eind))
    return segmenten


def _vertex_op(afstanden: list[float], afstand: float) -> int | None:
    """De vertex die op deze afstand ligt, als er een binnen de tolerantie ligt."""
    for index, waarde in enumerate(afstanden):
        if abs(waarde - afstand) <= _TOLERANTIE:
            return index
    return None


def _eerste_na(afstanden: list[float], afstand: float) -> int:
    """De eerste vertex voorbij deze afstand."""
    for index, waarde in enumerate(afstanden):
        if waarde > afstand + _TOLERANTIE:
            return index
    return len(afstanden) - 1


def _laatste_voor(afstanden: list[float], afstand: float) -> int:
    """De laatste vertex voor deze afstand."""
    keuze = 0
    for index, waarde in enumerate(afstanden):
        if waarde < afstand - _TOLERANTIE:
            keuze = index
    return keuze


def _knippunt(
    lijn: LineString,
    afstanden: list[float],
    z_waarden: list[float | None],
    stap: int,
    afstand: float,
) -> list[str]:
    """Het ingevoegde knippunt als coordinaattokens, met een lineair gewogen z.

    `stap` is het aantal getallen per punt van de lijn waarin dit punt komt te staan; het
    knippunt krijgt er evenveel, anders zou het de tokenreeks uit de pas laten lopen.
    """
    punt = lijn.interpolate(afstand)
    rij = [f"{punt.x:.{_KNIPPUNT_DECIMALEN}f}", f"{punt.y:.{_KNIPPUNT_DECIMALEN}f}"]
    if stap == 3:
        rij.append(f"{_hoogte(afstanden, z_waarden, afstand):.{_KNIPPUNT_DECIMALEN}f}")
    return rij


def _hoogte(afstanden: list[float], z_waarden: list[float | None], afstand: float) -> float:
    """De z op deze afstand, lineair tussen de twee vertices eromheen.

    Beide uitwegen hieronder horen niet bereikbaar te zijn: er wordt alleen om een z
    gevraagd als de literaal drie getallen per punt draagt, en dan geeft `parse_gml_z`
    voor elk punt een getal; en een knippunt ligt per constructie binnen de lijn, dus er
    is altijd een segment met lengte omheen. Gaat een van die aannames toch niet op, dan
    is een verzonnen hoogte het slechtste antwoord: `0.00` leest als NAP-nul en niet als
    "onbekend", en dat staat dan in het geknipte deel alsof het ingewonnen is.
    """
    for index in range(len(afstanden) - 1):
        begin, eind = afstanden[index], afstanden[index + 1]
        if begin - _TOLERANTIE <= afstand <= eind + _TOLERANTIE and eind > begin:
            onder, boven = z_waarden[index], z_waarden[index + 1]
            if onder is None or boven is None:
                raise DatasetError(
                    f"het knippunt op {afstand} m draagt drie getallen per punt maar de "
                    f"literaal geeft geen hoogte voor de vertices eromheen; er valt dan "
                    f"geen z voor het knippunt te bepalen."
                )
            deel = (afstand - begin) / (eind - begin)
            return onder + deel * (boven - onder)
    raise DatasetError(
        f"het knippunt op {afstand} m ligt niet op een segment met lengte; er valt dan "
        f"geen hoogte tussen twee vertices in te wegen."
    )
