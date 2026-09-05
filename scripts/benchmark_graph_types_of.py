#!/usr/bin/env python
"""Meet de termconstructie van `GwswDataset.graph_types_of`, oud tegen nieuw.

`scripts/benchmark.py` meet het laden en `scripts/benchmark_is_a.py` de checkfase-lus.
Dit script meet het derde hete stuk: de vraag "welke typen draagt deze URI?", die de
checks ook stellen voor onderdelen die nooit een knoop worden (een overstortdrempel, een
ledigingsvoorziening). Issue #23 verving daar twee wegwerptermen per aanroep -- een
`URIRef` mét rdflib's validatieregex over een tekst die al een geldige graafsleutel is, en
een `RDF.type`-lezing op rdflib's `DefinedNamespace` (geen attribuut maar een
`__getattr__`) -- door `graaf._uriref_snel` en een eenmalig gelezen `_RDF_TYPE`.

**De twee wegen staan hier allebei uitgeschreven**, als even diepe functies in deze
module, en niet als "de oude stand in een worktree tegen de nieuwe hier". Dat is met
opzet: het verschil dat gemeten wordt is de termconstructie en niet de aanroepvorm, en zo
blijft de meting herhaalbaar als de oude regel allang uit `dataset.py` weg is. Wie de
volledige methode wil meten (inclusief de memo van `types_of`), heeft die memo in beide
takken even warm -- de opwarmronde vult hem vóór de klok gaat lopen.

**Oud en nieuw wisselen elkaar per ronde af.** Een drukke machine raakt zo beide kanten
even hard, in plaats van de ene helft van de meting te vertragen; het gemiddelde én de
mediaan staan in de uitvoer, zodat een uitschieter zichtbaar blijft in plaats van
weggemiddeld. De uitkomsten worden vooraf een voor een vergeleken: geven de twee wegen
ergens een ander antwoord, dan stopt het script en is er niets te meten.

Tussen het laden en de klok staat een `gc.collect()`, om dezelfde reden als in
`scripts/benchmark_is_a.py`: `load_dataset` leest met de cyclische GC uit, en die
uitgestelde rekening hoort niet op het conto van de eerste ronde.

Gebruik (vanuit de repo-root):

    uv run python scripts/benchmark_graph_types_of.py

Ontbreekt de export, dan meldt het script dat en eindigt het met code 0 -- net als de
`zwaar`-tests, die zichzelf overslaan als het bestand niet op de machine staat.
"""

from __future__ import annotations

import argparse
import gc
import os
import statistics
import time
from collections.abc import Callable
from pathlib import Path

from rdflib import RDF, URIRef

from gwsw_orox_helpers.dataset import GwswDataset, load_dataset
from gwsw_orox_helpers.graaf import _uriref_snel

# Dezelfde export als de andere twee benchmarkscripts en de `zwaar`-tests: De Wolden en
# Hoogeveen, 112 MB, niet getrackt. Standaard onder de thuismap, te overschrijven met
# GWSW_OROX_FIXTUREPAD (issue #44). De BrutIS-export is geen zuivere UTF-8 (cp850-bytes in
# een straatnaam), vandaar de terugval.
_EXPORT_ONDER_HOME = Path("Development/nlriochecker/data/gwsw_orox_ttl/dewoldenhoogeveen_orox.ttl")
BRON = Path(os.environ.get("GWSW_OROX_FIXTUREPAD") or Path.home() / _EXPORT_ONDER_HOME)
FALLBACK_ENCODING = "cp850"

HERHALINGEN = 5

# De eenmalige lezing die `inlezen` (en via hem `dataset`) draagt; hier nagebootst zodat
# de nieuwe tak meet wat de package doet.
_RDF_TYPE = RDF.type


def oud(dataset: GwswDataset, uri: str) -> frozenset[str]:
    """De stand vóór issue #23: een verse `URIRef` en een verse `RDF.type` per aanroep."""
    uit_graaf = {str(soort) for soort in dataset.graph.objects(URIRef(uri), RDF.type)}
    return dataset.types_of(uri) | uit_graaf


def nieuw(dataset: GwswDataset, uri: str) -> frozenset[str]:
    """De stand ná issue #23: het snelpad en de eenmalig gelezen term."""
    uit_graaf = {str(soort) for soort in dataset.graph.objects(_uriref_snel(uri), _RDF_TYPE)}
    return dataset.types_of(uri) | uit_graaf


def _ronde(dataset: GwswDataset, uris: list[str], functie: Callable[..., object]) -> float:
    """Eén gang over alle URI's, geklokt."""
    begin = time.perf_counter()
    for uri in uris:
        functie(dataset, uri)
    return time.perf_counter() - begin


def main(argv: list[str] | None = None) -> int:
    ontleder = argparse.ArgumentParser(description=__doc__)
    ontleder.add_argument("--bron", type=Path, default=BRON, help="de OroX-export (TTL)")
    ontleder.add_argument("--herhalingen", type=int, default=HERHALINGEN)
    argumenten = ontleder.parse_args(argv)

    bron: Path = argumenten.bron
    if not bron.exists():
        print(f"Export ontbreekt: {bron} -- niets gemeten.")
        return 0

    begin = time.perf_counter()
    dataset = load_dataset(bron, fallback_encoding=FALLBACK_ENCODING)
    print(f"bron            {bron}")
    print(f"laden           {time.perf_counter() - begin:.1f} s (telt niet mee in de meting)")

    uris = [*dataset.nodes, *dataset.conduits]
    print(f"uris            {len(uris)} (knopen en strengen)")

    # De opwarmronde doet twee dingen tegelijk: zij bewijst dat de twee wegen hetzelfde
    # antwoord geven, en zij vult de typenmemo van `types_of` voor allebei.
    for uri in uris:
        if oud(dataset, uri) != nieuw(dataset, uri):
            raise SystemExit(f"de twee wegen geven een ander antwoord voor {uri}")
    begin = time.perf_counter()
    verzameld = gc.collect()
    print(f"gc.collect()    {time.perf_counter() - begin:.2f} s ({verzameld} objecten)")

    tijden: dict[str, list[float]] = {"oud": [], "nieuw": []}
    for ronde in range(1, argumenten.herhalingen + 1):
        for naam, functie in (("oud", oud), ("nieuw", nieuw)):
            duur = _ronde(dataset, uris, functie)
            tijden[naam].append(duur)
            print(f"ronde {ronde} {naam:5s}   {duur:.3f} s")

    for naam in ("oud", "nieuw"):
        reeks = tijden[naam]
        print(
            f"{naam:5s}           gemiddelde {statistics.fmean(reeks):.3f} s  "
            f"mediaan {statistics.median(reeks):.3f} s  min {min(reeks):.3f} s"
        )
    gemiddeld = statistics.fmean(tijden["oud"]) - statistics.fmean(tijden["nieuw"])
    print(
        f"verschil        {-gemiddeld / statistics.fmean(tijden['oud']) * 100:+.1f}% op het "
        f"gemiddelde; {gemiddeld / len(uris) * 1e9:.0f} ns per aanroep bespaard"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
