#!/usr/bin/env python
"""Meet de checkfase-lus: `is_a` en `of_class` over een hele OroX-export.

`scripts/benchmark.py` meet de vier hete *paden* van de package en daarmee vooral het
laden. Dit script meet wat er ná het laden gebeurt: nlriochecker stelt per run ruim een
miljoen keer de vraag "is dit object van dit type?" -- via `klim_naar_knoop`, dat voor
elke bezochte schakel elke netwerkwortel langsloopt, en via `of_class`, dat per
geconfigureerde rol de hele dataset afgaat. Issue #12 optimaliseert precies die lus
(`GwswDataset.types_of` gememoiseerd, `klassen._afsluiting` zonder eager default), en een
perf-claim hoort gepaard gemeten te worden: hetzelfde script, dezelfde export, de oude en
de nieuwe stand.

De lus die hier nagebootst wordt is bewust simpel en volledig bepaald door de export:

    voor elke wortel:  of_class(wortel)
    voor elke knoop en streng:  voor elke wortel:  is_a(uri, wortel)

De binnenste volgorde (uri buiten, wortel binnen) is die van `klim_naar_knoop`, dat per
bezocht object alle wortels afgaat; dat is de vorm waarin de vraag in de praktijk gesteld
wordt. Het aantal `is_a`-aanroepen staat in de uitvoer, zodat te zien is of de meting
inderdaad boven het miljoen uitkomt.

**De klok loopt alleen om de lus.** Het laden gebeurt ervoor en telt niet mee -- dat is
het pad van `scripts/benchmark.py`. Er wordt drie keer herhaald in hetzelfde proces en
zowel het gemiddelde als het minimum wordt gemeld, plus de losse herhalingen, zodat
uitschieters van een drukke machine te zien zijn in plaats van weggemiddeld.

Wat er gemeten wordt is de lus in *warme* toestand, en dat is geen keuze maar een gevolg
van de vorm: `of_class` raakt bij de eerste wortel al elke knoop en streng aan, dus de
memo van issue #12 is vol vóór de eerste `is_a`-aanroep. Het vullen zelf staat dus in
geen enkele herhaling apart; wie de koude kosten wil zien, moet de eerste `of_class`
afzonderlijk klokken. Het geheugenhoogwatermerk (`ru_maxrss`) staat erbij, maar zegt
alleen of de lus boven de piek van het laden uitkomt -- die piek zet de lader, en de
ruil van een memo is er niet los in te zien.

**Tussen het laden en de klok staat een `gc.collect()`, en die is er voor de eerlijkheid
van de vergelijking.** `load_dataset` leest met de cyclische GC uit (zie zijn docstring),
dus vlak na afloop staat de hele ingelezen graaf nog ongepromoveerd in generatie 0. De
eerste code die daarna netto geheugen vasthoudt betaalt die uitgestelde rekening: zij
lokt de collecties uit die die miljoenen objecten doorlopen. Een memo houdt per definitie
iets vast en een lus zonder memo niets, dus zonder deze stap schrijft de meting een
eenmalige GC-schuld van de *lader* op het conto van de *lus* -- gemeten scheelde dat op de
eerste herhaling meer dan een seconde, terwijl de tweede en derde herhaling het echte
beeld gaven. In een echte run wordt die rekening hoe dan ook betaald, door wat er ook maar
als eerste alloceert. Hier wordt zij vooraf en aan beide kanten gelijk afgerekend.

Gebruik (de nieuwe stand, vanuit de repo-root):

    uv run python scripts/benchmark_is_a.py

en de oude stand, met dit script uit de nieuwe werkboom tegen de venv van de oude:

    uv --directory <oude-worktree> run python <pad>/scripts/benchmark_is_a.py

Ontbreekt de export, dan meldt het script dat en eindigt het met code 0 -- net als de
`zwaar`-tests, die zichzelf overslaan als het bestand niet op de machine staat.
"""

from __future__ import annotations

import argparse
import gc
import resource
import statistics
import sys
import time
from pathlib import Path

from gwsw_orox_helpers.dataset import GwswDataset, load_dataset

# Dezelfde export als `scripts/benchmark.py` en de `zwaar`-tests: De Wolden en Hoogeveen,
# 112 MB, niet getrackt. De BrutIS-export is geen zuivere UTF-8 (cp850-bytes in een
# straatnaam), vandaar de terugval.
BRON = Path("/home/martin/nlriochecker/data/gwsw_orox_ttl/dewoldenhoogeveen_orox.ttl")
FALLBACK_ENCODING = "cp850"

# De standaardwortels van deze meting -- een default van dit script, geen constante van
# de package: welke klassen een afnemer selecteert is zijn configuratie (`CLAUDE.md`,
# Harde regels), en `--wortels` is de plek waar die keuze thuishoort.
#
# Bestaande GWSW-klassen uit de gebundelde ontologie. De eerste tien zijn de
# netwerkwortels zoals nlriochecker ze configureert (dezelfde lijst als in
# `tests/test_dataset.py::test_richting_van_geometrie_ziet_een_omgekeerd_getekende_lijn`):
# dat is precies de lijst die `klim_naar_knoop` per bezocht object afgaat. De veertien
# erna zijn klassen waarop de checks selecteren, van breed (`Leiding`, `Bouwwerk`) tot
# smal (`Overstortdrempel`) en met `Stelsel` erbij, dat buiten knopen en strengen valt en
# dus alleen missers oplevert. Zo bevat de meting beide takken van `_afsluiting` (wortels
# met en zonder subklassen) en beide uitkomsten van `is_a`.
#
# Het aantal is ook de schaal van de meting: de export draagt circa 47.000 knopen en
# strengen, dus met deze 24 wortels komt de lus op ruim 1,1 miljoen `is_a`-aanroepen per
# herhaling -- de orde van grootte die een nlriochecker-run haalt.
WORTELS = (
    "Put",
    "Overnamepunt",
    "Gemaal",
    "Lozingspunt",
    "UitlaatPunt",
    "Lozingsput",
    "Uitlaatconstructie",
    "Bergbezinkbassin",
    "Bergingsbassin",
    "Bezinkbassin",
    "Leiding",
    "Bouwwerk",
    "Stelsel",
    "Knooppunt",
    "Inspectieput",
    "Rioolput",
    "VrijvervalRioolleiding",
    "Persleiding",
    "Drukleiding",
    "Kolk",
    "Putdeksel",
    "Compartiment",
    "Hulpstuk",
    "Overstortdrempel",
)

HERHALINGEN = 3

# `ru_maxrss` telt in KiB op Linux en in bytes op macOS/BSD; dezelfde omrekening als in
# `scripts/benchmark.py`, zodat de twee verslagen dezelfde eenheid dragen.
MAXRSS_DELER = 1024 if sys.platform == "darwin" else 1


def _piek_mib() -> float:
    """Het geheugenhoogwatermerk van dit proces in MiB, uit `ru_maxrss`."""
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) // MAXRSS_DELER / 1024


def checkfase_lus(dataset: GwswDataset, wortels: tuple[str, ...]) -> tuple[int, int]:
    """Bootst de lus van de checkfase na; geeft (aantal `is_a`, aantal treffers) terug.

    De treffers worden geteld omdat een lus zonder uitkomst wegge-optimaliseerd zou
    kunnen worden en omdat het getal tussen de oude en de nieuwe stand gelijk hoort te
    zijn: dat is de goedkoopste controle dat de optimalisatie het antwoord niet
    veranderde.
    """
    treffers = 0
    for wortel in wortels:
        treffers += len(dataset.of_class(wortel))
    aanroepen = 0
    for uri in (*dataset.nodes, *dataset.conduits):
        for wortel in wortels:
            aanroepen += 1
            if dataset.is_a(uri, wortel):
                treffers += 1
    return aanroepen, treffers


def main(argv: list[str] | None = None) -> int:
    ontleder = argparse.ArgumentParser(description=__doc__)
    ontleder.add_argument("--bron", type=Path, default=BRON, help="de OroX-export (TTL)")
    ontleder.add_argument("--herhalingen", type=int, default=HERHALINGEN)
    ontleder.add_argument(
        "--wortels",
        default=",".join(WORTELS),
        help="komma-gescheiden GWSW-klassen; de schaal van de meting hangt eraan",
    )
    argumenten = ontleder.parse_args(argv)

    wortels = tuple(naam.strip() for naam in argumenten.wortels.split(",") if naam.strip())
    bron: Path = argumenten.bron
    if not bron.exists():
        print(f"Export ontbreekt: {bron} -- niets gemeten.")
        return 0

    begin = time.perf_counter()
    dataset = load_dataset(bron, fallback_encoding=FALLBACK_ENCODING)
    laadtijd = time.perf_counter() - begin
    print(f"bron            {bron}")
    print(f"laden           {laadtijd:.1f} s (telt niet mee in de meting)")
    print(f"knopen/strengen {len(dataset.nodes)} / {len(dataset.conduits)}")
    print(f"wortels         {len(wortels)}: {', '.join(wortels)}")
    print(f"piek na laden   {_piek_mib():.0f} MiB")
    # De uitgestelde GC-rekening van de lader afrekenen vóór de klok gaat lopen; waarom,
    # staat in de moduledocstring.
    begin = time.perf_counter()
    verzameld = gc.collect()
    print(f"gc.collect()    {time.perf_counter() - begin:.2f} s ({verzameld} objecten)")

    tijden: list[float] = []
    uitkomsten: set[tuple[int, int]] = set()
    for ronde in range(1, argumenten.herhalingen + 1):
        begin = time.perf_counter()
        uitkomst = checkfase_lus(dataset, wortels)
        duur = time.perf_counter() - begin
        tijden.append(duur)
        uitkomsten.add(uitkomst)
        print(f"herhaling {ronde}     {duur:.2f} s")

    aanroepen, treffers = uitkomsten.pop()
    if uitkomsten:
        raise SystemExit("de herhalingen gaven niet dezelfde uitkomst")
    print(f"is_a-aanroepen  {aanroepen} per herhaling ({treffers} treffers)")
    print(f"gemiddelde      {statistics.fmean(tijden):.2f} s")
    print(f"minimum         {min(tijden):.2f} s")
    print(f"piek totaal     {_piek_mib():.0f} MiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
