"""De analyseronde: wie hoort waar.

Een lezing van de bron levert het `_Plan`: per blok het bitmasker van vlakken waar het
heen gaat, per blanke knoop het blok waar hij in valt, en per geknipte geometrieknoop zijn
stukken. De vier stappen van de toewijzing (zaaien, omhoog, omlaag, rest) staan uitgeschreven
in de docstring van `gwsw_orox_helpers.clip`.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pyoxigraph

from gwsw_orox_helpers.clip.grenzen import _Vlak
from gwsw_orox_helpers.clip.knip import _plaats, _Stuk
from gwsw_orox_helpers.clip.termen import _KNIPSTAART, KNIP, _Kniptermen
from gwsw_orox_helpers.errors import KnipError
from gwsw_orox_helpers.geometry import is_multipart_literal
from gwsw_orox_helpers.namen import GML_LITERAL
from gwsw_orox_helpers.schrijven import lees_orox

# De predicaten die een houder aan een onderdeel binden staan sinds issue #32 niet meer als
# vaste 1.6-constanten hier maar in `_Kniptermen`, dat `clip_orox` uit de bron afleidt: op
# een 1.7-export vergelijkt de knip tegen de 1.7-predicaten. De verzamelingen worden per
# clip één keer gebouwd (in `_kniptermen`) en niet per quad, net als voorheen.


@dataclass
class _Plan:
    """Wat er per vlak weggeschreven moet worden; de uitkomst van de analyseronde."""

    namen: tuple[str, ...]
    # Blok-sleutel -> bitmasker van vlakken. Een blok is een benoemd subject met de blanke
    # knopen die eraan hangen; `eigenaar` wijst elke blanke knoop naar zijn blok.
    toewijzing: dict[str, int] = field(default_factory=dict)
    eigenaar: dict[str, str] = field(default_factory=dict)
    # Sleutel van een geometrieknoop -> de stukken waarin zijn lijn uiteenvalt.
    stukken: dict[str, tuple[_Stuk, ...]] = field(default_factory=dict)
    # Blok-sleutel van een houder van een geknipte geometrie -> bitmasker; draagt `knip:geknipt`.
    geknipte_houders: dict[str, int] = field(default_factory=dict)
    # Het bitmasker per term, platgeslagen: `toewijzing` na `blok`. `_maak_plan` vult hem
    # met `bouw_maskers` als laatste stap; de schrijfronde leest hem alleen.
    maskers: dict[str, int] = field(default_factory=dict)

    def blok(self, sleutel: str) -> str:
        """Het blok waar deze term in valt: hijzelf, of het blok van zijn blanke knoop."""
        return self.eigenaar.get(sleutel, sleutel)

    def bouw_maskers(self) -> None:
        """Slaat `toewijzing` en `eigenaar` plat tot een tabel per term.

        De schrijfronde stelt die vraag per quad -- op de export van De Wolden en
        Hoogeveen ruim vier miljoen keer per deel -- en per term langs `blok` lopen
        kost er twee opzoekingen in plaats van een. Platgeslagen is het er een.

        `_maak_plan` bouwt de tabel als laatste stap, wanneer `toewijzing` en `eigenaar`
        niet meer veranderen. Dat is bewust geen luie vulling bij de eerste vraag: die zou
        de tabel laten afhangen van *wanneer* er voor het eerst naar gevraagd werd, en een
        latere verzetting stil buiten beeld laten. Wie het plan alsnog verzet, bouwt hem
        opnieuw.
        """
        toewijzing = self.toewijzing
        plat = dict(toewijzing)
        for knoop, blok in self.eigenaar.items():
            plat[knoop] = toewijzing.get(blok, 0)
        self.maskers = plat


def _genummerd(
    quads: Iterable[pyoxigraph.Quad],
) -> Iterator[tuple[pyoxigraph.Quad, str, str | None]]:
    """De quadstroom met de sleutel van subject en object erbij.

    De sleutel van een term is zijn IRI, of `_:b<n>` voor een blanke knoop. Die
    nummering volgt de stroomvolgorde -- subject voor object, altijd in die volgorde --
    en is daarmee bij elke lezing van hetzelfde bestand dezelfde, anders dan de namen
    die pyoxigraph zelf verzint. Een literaal (en een RDF-ster-triple) heeft geen
    sleutel; als object levert dat `None`, als subject kan het niet voorkomen.

    De twee takken staan bewust twee keer uitgeschreven in plaats van in een hulpfunctie
    per term: deze lus draait per quad van de bron en de bron gaat er N+1 keer doorheen,
    dus een aanroep per term is er op de export van De Wolden en Hoogeveen elf miljoen.
    """
    namen: dict[str, str] = {}
    teller = itertools.count()
    named_node = pyoxigraph.NamedNode
    blank_node = pyoxigraph.BlankNode
    for quad in quads:
        subject = quad.subject
        if isinstance(subject, named_node):
            onderwerp: str | None = subject.value
        elif isinstance(subject, blank_node):
            ruw = subject.value
            onderwerp = namen.get(ruw)
            if onderwerp is None:
                onderwerp = namen[ruw] = f"_:b{next(teller)}"
        else:  # pragma: no cover -- een subject is nooit een literaal
            onderwerp = None
        assert onderwerp is not None  # een subject is nooit een literaal

        object_ = quad.object
        if isinstance(object_, named_node):
            voorwerp: str | None = object_.value
        elif isinstance(object_, blank_node):
            ruw = object_.value
            voorwerp = namen.get(ruw)
            if voorwerp is None:
                voorwerp = namen[ruw] = f"_:b{next(teller)}"
        else:
            voorwerp = None
        yield quad, onderwerp, voorwerp


def _maak_plan(
    bron: Path, vlakken: tuple[_Vlak, ...], fallback_encoding: str | None, termen: _Kniptermen
) -> _Plan:
    """Leest de bron een keer en bepaalt per blok naar welke vlakken het gaat."""
    plan = _Plan(namen=tuple(vlak.naam for vlak in vlakken))
    ouder_van: dict[str, str] = {}
    randen: list[tuple[str, str]] = []
    verbindingen: list[tuple[str, str]] = []
    literalen: dict[str, list[str]] = {}
    subjecten: set[str] = set()
    houder_naar_onderdeel = termen.houder_naar_onderdeel
    onderdeel_naar_houder = termen.onderdeel_naar_houder

    for quad, onderwerp, voorwerp in _genummerd(lees_orox(bron, fallback_encoding).quads):
        subjecten.add(onderwerp)
        if voorwerp is not None and voorwerp.startswith("_:"):
            ouder_van.setdefault(voorwerp, onderwerp)
        predicaat = quad.predicate.value
        if predicaat.startswith(KNIP):
            raise KnipError(
                f"{bron}: het predicaat {predicaat!r} zit in de knip-naamruimte die de clip "
                f"zelf voor de knipmerken gebruikt; zo'n bron is na de hereniging niet van een "
                f"geknipte te onderscheiden."
            )
        if voorwerp is not None:
            if predicaat in houder_naar_onderdeel:
                randen.append((onderwerp, voorwerp))
            elif predicaat in onderdeel_naar_houder:
                randen.append((voorwerp, onderwerp))
            elif predicaat == termen.has_connection:
                verbindingen.append((onderwerp, voorwerp))
        elif (
            predicaat == termen.has_value
            and isinstance(quad.object, pyoxigraph.Literal)
            and quad.object.datatype.value == GML_LITERAL
        ):
            literalen.setdefault(onderwerp, []).append(quad.object.value)

    for naam in subjecten:
        if "__knip" in naam and _KNIPSTAART.search(naam):
            raise KnipError(
                f"{bron}: {naam!r} eindigt op de staart die de clip zelf voor geknipte stukken "
                f"gebruikt; zo'n bron is na de hereniging niet van een geknipte te onderscheiden."
            )

    # De blokken kennen elkaar pas als bekend is welke blanke knoop bij welk blok hoort.
    plan.eigenaar = _eigenaren(ouder_van)
    blokken = {plan.blok(naam) for naam in subjecten}
    ouders = _verwantschap(randen, plan)
    _zaai(plan, literalen, vlakken)
    _omhoog(plan, ouders)
    _omlaag(plan, blokken, ouders, _verbindingsgraaf(verbindingen, plan), len(vlakken))
    _omhoog(plan, ouders)
    _merk_houders(plan, randen)
    plan.bouw_maskers()
    return plan


def _eigenaren(ouder_van: dict[str, str]) -> dict[str, str]:
    """Per blanke knoop het benoemde blok waar hij in valt.

    Loopt de keten van houders omhoog tot een benoemd subject. Een blanke knoop waar
    niets naar wijst is zijn eigen blok; een keten die in zichzelf terugloopt (een
    blanke knoop die zijn eigen voorouder is) eindigt bij de knoop waar de lus sluit.
    """
    wortels: dict[str, str] = {}
    for knoop in ouder_van:
        pad: list[str] = []
        huidig = knoop
        while huidig.startswith("_:") and huidig not in wortels:
            if huidig in pad:  # lus: neem de knoop zelf als blok
                break
            pad.append(huidig)
            volgende = ouder_van.get(huidig)
            if volgende is None:
                break
            huidig = volgende
        wortel = wortels.get(huidig, huidig)
        for stap in pad:
            wortels[stap] = wortel
    return wortels


def _verwantschap(randen: list[tuple[str, str]], plan: _Plan) -> dict[str, set[str]]:
    """Per blok de blokken die het als onderdeel of aspect dragen.

    Randen binnen een blok (een blanke knoop aan zijn eigen houder) vallen weg: die
    gaan per definitie samen dezelfde kant op.
    """
    ouders: dict[str, set[str]] = {}
    for houder, onderdeel in randen:
        boven, onder = plan.blok(houder), plan.blok(onderdeel)
        if boven == onder:
            continue
        ouders.setdefault(onder, set()).add(boven)
    return ouders


def _verbindingsgraaf(verbindingen: list[tuple[str, str]], plan: _Plan) -> dict[str, set[str]]:
    """Per blok de blokken waar het via `hasConnection` aan vastzit, beide richtingen op."""
    graaf: dict[str, set[str]] = {}
    for links, rechts in verbindingen:
        een, twee = plan.blok(links), plan.blok(rechts)
        if een == twee:
            continue
        graaf.setdefault(een, set()).add(twee)
        graaf.setdefault(twee, set()).add(een)
    return graaf


def _zaai(plan: _Plan, literalen: dict[str, list[str]], vlakken: tuple[_Vlak, ...]) -> None:
    """Geeft elk blok met een geometrie zijn vlakken, en knipt de lijnen die de grens kruisen."""
    for knoop, waarden in literalen.items():
        masker = 0
        if len(waarden) == 1 and not is_multipart_literal(waarden[0]):
            masker, stukken = _plaats(waarden[0], vlakken)
            if stukken is not None:
                plan.stukken[knoop] = stukken
        else:
            # Een multi-geometrie wordt niet geknipt: hij gaat heel naar elk vlak dat hij
            # raakt. Meer dan een literaal op de knoop telt daarvoor, en een literaal die er
            # zelf meer dan een deel in draagt (`gml:MultiCurve`, of twee posLists naast
            # elkaar) net zo goed -- de tellingen van de literalen alleen lieten die tweede
            # vorm ongemerkt door de knip lopen.
            for waarde in waarden:
                masker |= _plaats(waarde, vlakken, knip=False)[0]
        if masker:
            blok = plan.blok(knoop)
            plan.toewijzing[blok] = plan.toewijzing.get(blok, 0) | masker


def _omhoog(plan: _Plan, ouders: dict[str, set[str]]) -> None:
    """Geeft elke houder de vereniging van de vlakken van zijn afstammelingen."""
    werk = list(plan.toewijzing)
    while werk:
        volgende: list[str] = []
        for knoop in werk:
            masker = plan.toewijzing[knoop]
            for ouder in ouders.get(knoop, ()):
                oud = plan.toewijzing.get(ouder, 0)
                if oud | masker != oud:
                    plan.toewijzing[ouder] = oud | masker
                    volgende.append(ouder)
        werk = volgende


def _omlaag(
    plan: _Plan,
    blokken: set[str],
    ouders: dict[str, set[str]],
    verbindingen: dict[str, set[str]],
    aantal_vlakken: int,
) -> None:
    """Laat wat geen geometrie heeft de vlakken van zijn houder erven.

    Zit die houder aan beide kanten van een knip, dan versmalt het aanhechtingspunt de
    keuze: de `hasConnection` van het onderdeel wijst naar een orientatie die zelf wel
    een vlak heeft. Blijft er dan niets over dat binnen de houder past, dan wint de
    houder -- een onderdeel hoort nooit buiten zijn houder te vallen, want dan zou de
    `hasPart`-rand ertussen nergens meer geschreven kunnen worden.
    """
    alles = (1 << aantal_vlakken) - 1
    onbekend = {knoop for knoop in blokken if knoop not in plan.toewijzing}
    while True:
        # Per ronde wordt eerst alles uitgerekend en pas daarna toegekend. Een blok dat
        # binnen dezelfde ronde van een ander onbekend blok zou erven, wacht zo tot de
        # volgende ronde -- en dat is wat de uitkomst onafhankelijk maakt van de volgorde
        # waarin een verzameling toevallig doorlopen wordt. Zonder dat zou dezelfde bron
        # twee keer geknipt twee verschillende verdelingen kunnen opleveren.
        ronde: dict[str, int] = {}
        for knoop in onbekend:
            masker = 0
            for ouder in ouders.get(knoop, ()):
                masker |= plan.toewijzing.get(ouder, 0)
            if not masker:
                continue
            if masker.bit_count() > 1:
                aanhechting = 0
                for buur in verbindingen.get(knoop, ()):
                    aanhechting |= plan.toewijzing.get(buur, 0)
                if aanhechting & masker:
                    masker &= aanhechting
            ronde[knoop] = masker
        if not ronde:
            break
        plan.toewijzing.update(ronde)
        onbekend.difference_update(ronde)

    # Wat nergens aan hangt -- de ontologiekop -- hoort in elk deel te staan.
    for knoop in onbekend:
        plan.toewijzing[knoop] = alles


def _merk_houders(plan: _Plan, randen: list[tuple[str, str]]) -> None:
    """Onthoudt welke houders van een geknipte geometrie het merk `knip:geknipt` krijgen."""
    for houder, onderdeel in randen:
        if onderdeel in plan.stukken:
            blok = plan.blok(houder)
            masker = plan.toewijzing.get(blok, 0)
            if masker:
                plan.geknipte_houders[blok] = masker
