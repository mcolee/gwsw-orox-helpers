#!/usr/bin/env python
"""Meet de GML-literaalparsing geïsoleerd: de twee losse lezers tegen de eenpaslezer.

`scripts/benchmark.py` meet de vier hete paden en `scripts/benchmark_is_a.py` de
checkfase-lus; dit script meet de laag daaronder. De leeslaag stelt over elke geometrie
in een export twee vragen -- de meetkunde in het platte vlak en de z-waarde per punt --
en die twee vragen liepen tot issue #13 elk hun eigen regex en float-conversie over
dezelfde tekst. `geometry.parse_gml_met_z` doet ze in een gang. Wat dat scheelt is hier
te zien zonder dat de parse, de index en de objectopbouw van `load_dataset` het beeld
vertroebelen.

**De meting is gepaard van vorm.** Beide manieren draaien op dezelfde corpus in hetzelfde
proces, en per herhaling om en om: eerst de oude weg, dan de nieuwe. Een drukke machine
raakt zo allebei de kanten even hard, terwijl een vergelijking tussen twee runs (of twee
werkbomen) het verschil in de meetruis kan laten verdwijnen. Er is daarom ook geen oude
werkboom nodig: de "oude weg" is `parse_gml` plus `parse_gml_z`, en die twee blijven
bestaan -- de knip en nlriochecker roepen ze rechtstreeks aan.

**De corpus komt bij voorkeur uit een echte export.** De literalen worden met een regex
uit de Turtle-tekst gehaald en niet met de parser: dit is een meetscript en geen lezer,
en wat de klok moet zien is de geometrie-lezing en niet pyoxigraph. De enige
Turtle-ontsnapping die in een `geo:gmlLiteral` van een GWSW-export voorkomt is `\\"`, en
die wordt teruggedraaid; iets ingewikkelders zou een tweede Turtle-parser worden. Beide
manieren krijgen hoe dan ook exact dezelfde tekst, dus de vergelijking staat er los van.
Ontbreekt de export, dan valt het script terug op een synthetische corpus in de vorm die
De Wolden en Hoogeveen laat zien (2D-punten met `srsDimension` op de `gml:Point` en
2D-lijnen met `srsDimension` op de `gml:posList`), zodat het overal iets te zeggen heeft.

Voor de meting begint wordt eenmalig gecontroleerd dat beide manieren over de hele corpus
hetzelfde antwoord geven -- de uitkomst én de foutmelding. Een snellere lezer die iets
anders leest is geen winst, en dat hoort niet pas in de tests op te vallen.

Gebruik (vanuit de repo-root):

    uv run python scripts/benchmark_gml.py
    uv run python scripts/benchmark_gml.py --bron pad/naar/export.ttl --herhalingen 5

Ontbreekt de export, dan meet het script de synthetische corpus en zegt het erbij -- net
als `scripts/benchmark.py`, dat zich meldt en met code 0 eindigt in plaats van te falen.
"""

from __future__ import annotations

import argparse
import re
import statistics
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon

from gwsw_orox_helpers.codering import decodeer
from gwsw_orox_helpers.geometry import GeometryError, parse_gml, parse_gml_met_z, parse_gml_z

# Een lezer is alles wat een GML-literaal in een meetkunde plus een z-lijst omzet; de
# twee kanten van de meting hebben daarom dezelfde vorm en zijn verwisselbaar.
#
# Als `type`-alias (PEP 695) en niet als kale toekenning: shapely levert geen stubs, dus
# `Point | LineString | Polygon` is voor mypy een *waarde* van het type `UnionType` en niet
# een type -- een kale toekenning gaf daardoor "Variable is not valid as a type".
type Meetkunde = Point | LineString | Polygon
type Lezer = Callable[[str], tuple[Meetkunde, list[float | None]]]

# Dezelfde export als `scripts/benchmark.py` en de `zwaar`-tests: De Wolden en Hoogeveen,
# 112 MB, niet getrackt. De BrutIS-export is geen zuivere UTF-8 (cp850-bytes in een
# straatnaam), vandaar de terugval.
BRON = Path("/home/martin/nlriochecker/data/gwsw_orox_ttl/dewoldenhoogeveen_orox.ttl")
FALLBACK_ENCODING = "cp850"

HERHALINGEN = 3

# De literaal zoals hij in de Turtle staat: tussen dubbele quotes en met `^^geo:gmlLiteral`
# erachter. Niet-gulzig, want er staan er meer op een regel dan een.
LITERAAL_PATROON = re.compile(r'"(<gml:.*?)"\^\^geo:gmlLiteral', re.DOTALL)

# De twee vormen die De Wolden en Hoogeveen laat zien, voor de synthetische terugval.
SYNTHETISCH_PUNT = (
    '<gml:Point srsDimension="2" srsName="Netherlands-RD">'
    "<gml:pos>{x:.3f} {y:.3f}</gml:pos></gml:Point>"
)
SYNTHETISCHE_LIJN = (
    '<gml:LineString srsName="Netherlands-RD"><gml:posList srsDimension="2">'
    "{punten}</gml:posList></gml:LineString>"
)


def twee_lezers(literal: str) -> tuple[Meetkunde, list[float | None]]:
    """De twee losse lezers achter elkaar: wat `inlezen._geometry` vroeger deed."""
    return parse_gml(literal), parse_gml_z(literal)


def eenpaslezer(literal: str) -> tuple[Meetkunde, list[float | None]]:
    """De eenpaslezer, in dezelfde vorm als `twee_lezers`, zodat ze verwisselbaar zijn."""
    return parse_gml_met_z(literal)


def over_de_corpus(lezer: Lezer, corpus: Sequence[str]) -> int:
    """Leest de hele corpus met deze lezer; geeft het aantal onleesbare literalen terug."""
    fouten = 0
    for literal in corpus:
        try:
            lezer(literal)
        except GeometryError:
            fouten += 1
    return fouten


def _uitkomst(lezer: Lezer, literal: str) -> object:
    """De volledige waarneembare uitkomst van een literaal langs een van beide lezers.

    Dezelfde vorm als `_uitkomst` in `tests/test_geometry.py`, waar de
    gelijkwaardigheid als test staat; hier staat zij als vangnet onder de meting, want
    een meetscript hoort geen tests te importeren en een test geen script.
    """
    try:
        meetkunde, z = lezer(literal)
    except GeometryError as fout:
        return ("GeometryError", str(fout))
    return ("geometrie", meetkunde.wkt, z)


def verschillen(corpus: Sequence[str]) -> list[str]:
    """De literalen waarop de twee lezers niet hetzelfde antwoorden."""
    return [
        literal
        for literal in corpus
        if _uitkomst(twee_lezers, literal) != _uitkomst(eenpaslezer, literal)
    ]


def _synthetische_corpus(aantal: int) -> list[str]:
    """Een corpus in de vorm van de echte export, voor een machine zonder die export."""
    corpus: list[str] = []
    for nummer in range(aantal):
        x = 234000.0 + nummer % 1000
        y = 527000.0 + nummer % 997
        if nummer % 3 == 2:
            punten = " ".join(
                f"{x + stap * 12.5:.2f} {y + stap * 7.5:.2f}" for stap in range(2 + nummer % 6)
            )
            corpus.append(SYNTHETISCHE_LIJN.format(punten=punten))
        else:
            corpus.append(SYNTHETISCH_PUNT.format(x=x, y=y))
    return corpus


def _corpus_uit_export(bron: Path) -> list[str]:
    """De `geo:gmlLiteral`-teksten uit een OroX-export, in bestandsvolgorde."""
    tekst, _ = decodeer(bron, bron.read_bytes(), FALLBACK_ENCODING)
    return [treffer[1].replace('\\"', '"') for treffer in LITERAAL_PATROON.finditer(tekst)]


def _samenstelling(corpus: Sequence[str]) -> str:
    """Wat er in de corpus zit, zodat een getal bij een vorm hoort."""
    punten = sum(1 for literal in corpus if "<gml:pos>" in literal)
    lijsten = sum(1 for literal in corpus if "<gml:posList" in literal)
    met_srs = sum(1 for literal in corpus if "srsDimension" in literal)
    drie_d = sum(1 for literal in corpus if 'srsDimension="3"' in literal)
    return (
        f"{len(corpus)} literalen: {punten} met gml:pos, {lijsten} met gml:posList, "
        f"{met_srs} met srsDimension (waarvan {drie_d} driedimensionaal)"
    )


def _klok(lezer: Lezer, corpus: Sequence[str]) -> tuple[float, int]:
    """De tijd die deze lezer over de hele corpus doet, en wat hij niet kon lezen."""
    begin = time.perf_counter()
    fouten = over_de_corpus(lezer, corpus)
    return time.perf_counter() - begin, fouten


def main(argv: list[str] | None = None) -> int:
    ontleder = argparse.ArgumentParser(description=__doc__)
    ontleder.add_argument("--bron", type=Path, default=BRON, help="de OroX-export (TTL)")
    ontleder.add_argument("--herhalingen", type=int, default=HERHALINGEN)
    ontleder.add_argument(
        "--synthetisch",
        type=int,
        default=60000,
        help="omvang van de synthetische corpus als de export ontbreekt",
    )
    argumenten = ontleder.parse_args(argv)

    bron: Path = argumenten.bron
    if bron.exists():
        begin = time.perf_counter()
        corpus = _corpus_uit_export(bron)
        print(f"bron            {bron}")
        print(f"oogsten         {time.perf_counter() - begin:.1f} s (telt niet mee)")
    else:
        corpus = _synthetische_corpus(argumenten.synthetisch)
        print(f"bron            {bron} ontbreekt -- synthetische corpus")
    if not corpus:
        print("Geen enkele geo:gmlLiteral gevonden; niets gemeten.")
        return 0
    print(f"corpus          {_samenstelling(corpus)}")

    afwijkend = verschillen(corpus)
    if afwijkend:
        raise SystemExit(
            f"de twee wegen geven op {len(afwijkend)} literalen een ander antwoord, "
            f"bijvoorbeeld: {afwijkend[0][:160]!r}"
        )
    print(f"gelijkwaardig   ja, op alle {len(corpus)} literalen (uitkomst en foutmelding)")

    oud: list[float] = []
    nieuw: list[float] = []
    fouttellingen: set[int] = set()
    for ronde in range(1, argumenten.herhalingen + 1):
        duur_oud, fouten_oud = _klok(twee_lezers, corpus)
        duur_nieuw, fouten_nieuw = _klok(eenpaslezer, corpus)
        oud.append(duur_oud)
        nieuw.append(duur_nieuw)
        fouttellingen.update((fouten_oud, fouten_nieuw))
        print(f"herhaling {ronde}     oud {duur_oud:.3f} s   nieuw {duur_nieuw:.3f} s")

    if len(fouttellingen) > 1:
        raise SystemExit(f"de herhalingen telden verschillende aantallen fouten: {fouttellingen}")
    print(f"onleesbaar      {fouttellingen.pop()} literalen (in elke herhaling gelijk)")

    gem_oud = statistics.fmean(oud)
    gem_nieuw = statistics.fmean(nieuw)
    per_literaal = (gem_oud - gem_nieuw) / len(corpus) * 1e6
    print(f"gemiddelde      oud {gem_oud:.3f} s   nieuw {gem_nieuw:.3f} s")
    print(
        f"mediaan         oud {statistics.median(oud):.3f} s   "
        f"nieuw {statistics.median(nieuw):.3f} s"
    )
    print(f"minimum         oud {min(oud):.3f} s   nieuw {min(nieuw):.3f} s")
    print(
        f"verschil        {(gem_nieuw / gem_oud - 1) * 100:+.1f}% op het gemiddelde "
        f"({per_literaal:.2f} us per literaal)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
