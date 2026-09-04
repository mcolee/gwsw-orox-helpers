#!/usr/bin/env python
"""Meet de vier hete paden van deze package op een echte OroX-export.

De vier paden zijn `load_dataset` (de leesweg met index), `schrijf_orox` (de
schrijfweg als stroom), `clip_orox` (de ruimtelijke verdeling) en `merge_orox` (de
hereniging van de delen). Ze staan in `docs/architectuur.md` beschreven; dit script
zegt wat ze kosten, zodat een optimalisatie een voor- en een nameting heeft in plaats
van een gevoel.

**Elke meting draait in een eigen kindproces.** Dat is geen omweg maar de reden dat de
getallen te vergelijken zijn: `resource.getrusage(...).ru_maxrss` is een hoogwatermerk
dat binnen een proces nooit meer zakt, dus zou een tweede pad in hetzelfde proces de
piek van het eerste erven. Een fork per meting geeft elk pad zijn eigen merk, en houdt
bovendien een pad dat het geheugen opeet (of door de OOM-killer geraakt wordt) weg van
de rest van de meting.

**De geheugenmaat is `ru_maxrss` (RUSAGE_SELF) en niet `tracemalloc`.** De
motoren onder deze package -- pyoxigraph (Rust) en shapely (GEOS) -- alloceren buiten
de Python-allocator om, en juist daar zit het gros van het geheugen op een export van
112 MB. `tracemalloc` ziet daar niets van en zou een piek melden die orden van grootte
te laag is. `ru_maxrss` telt de hele resident set en dus ook die twee. De eenheid ervan
verschilt per platform -- KiB op Linux, bytes op macOS/BSD -- en wordt hier naar KiB
omgerekend, zodat een meting op de ene machine naast die op de andere kan.

De tijd is wandkloktijd (`time.perf_counter`) om precies de bibliotheekaanroep heen:
de import van de package en het klaarzetten van paden gebeuren ervoor, en het
opmaken van het verslag (bestandsgroottes, tellingen) erna.

Gebruik:

    uv run python scripts/benchmark.py --json nulmeting.json
    uv run python scripts/benchmark.py --paden load_dataset --herhalingen 3
    uv run python scripts/benchmark.py --profiel-map /tmp/profielen

Ontbreekt de export, dan meldt het script dat en eindigt het met code 0 -- net als de
`zwaar`-tests, die zichzelf overslaan als het bestand niet op de machine staat.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Any, NamedTuple

WORTEL = Path(__file__).resolve().parents[1]

# Dezelfde twee bestanden als de `zwaar`-tests in `tests/test_schrijven.py` en
# `tests/test_clip.py`: de 112 MB-export van De Wolden en Hoogeveen (niet getrackt) en
# de gemeentegrenzen die er in deze repo bij horen. Het exportpad staat standaard onder de
# thuismap en is te overschrijven met GWSW_OROX_FIXTUREPAD (issue #44), net als bij de tests.
_EXPORT_ONDER_HOME = Path("nlriochecker/data/gwsw_orox_ttl/dewoldenhoogeveen_orox.ttl")
BRON = Path(os.environ.get("GWSW_OROX_FIXTUREPAD") or Path.home() / _EXPORT_ONDER_HOME)
GRENZEN = WORTEL / "tests" / "fixtures" / "gis" / "gemeentegrenzen_dewoldenhoogeveen.geojson"
SLEUTEL = "gemeentenaam"
# Deze BrutIS-export is geen zuivere UTF-8 (cp850-bytes in een straatnaam); nlriochecker
# leest hem met deze terugval en de `zwaar`-tests doen dat ook.
FALLBACK_ENCODING = "cp850"

# `ru_maxrss` telt in KiB op Linux en in bytes op macOS/BSD (Darwin). De deler maakt van
# beide dezelfde maat; zonder hem zou dezelfde meting op een Mac er duizend keer groter
# uitzien dan op de Linux-machine waar de nulmeting vandaan komt.
MAXRSS_EENHEID = "bytes" if sys.platform == "darwin" else "KiB"
MAXRSS_DELER = 1024 if sys.platform == "darwin" else 1

PADEN = ("load_dataset", "schrijf_orox", "clip_orox", "merge_orox")
# Waar het profiel het meest te zeggen heeft: de leesweg en de knip. De schrijfweg is
# een deelverzameling van de knip en de hereniging leest de delen met dezelfde lezer.
PROFIELPADEN = ("load_dataset", "clip_orox")

Verslag = dict[str, Any]


class Werk(NamedTuple):
    """Een gemeten aanroep en de manier waarop hij zich achteraf verantwoordt.

    De splitsing houdt de klok strak om `uitvoeren` heen: tellingen en
    bestandsgroottes horen bij het verslag en niet bij de meting.
    """

    uitvoeren: Callable[[], Any]
    verslag: Callable[[Any], Verslag]


@dataclass(frozen=True)
class Instellingen:
    """Wat er gemeten wordt en waarmee."""

    bron: Path
    grenzen: Path
    sleutel: str
    fallback_encoding: str | None
    werkmap: Path


@dataclass
class Run:
    """Een enkele meting: wandkloktijd en het geheugenhoogwatermerk eromheen."""

    seconden: float
    basis_kib: int
    piek_kib: int

    def als_json(self) -> dict[str, float | int]:
        return {
            "seconden": round(self.seconden, 3),
            "basis_kib": self.basis_kib,
            "piek_kib": self.piek_kib,
        }


@dataclass
class Uitkomst:
    """Alle herhalingen van een pad, plus wat de laatste ervan opleverde."""

    naam: str
    runs: list[Run] = field(default_factory=list)
    verslag: Verslag = field(default_factory=dict)
    fout: str | None = None

    @property
    def tijden(self) -> list[float]:
        return sorted(run.seconden for run in self.runs)

    @property
    def piek_mib(self) -> float:
        return max((run.piek_kib for run in self.runs), default=0) / 1024

    @property
    def basis_mib(self) -> float:
        return max((run.basis_kib for run in self.runs), default=0) / 1024

    def als_json(self) -> dict[str, Any]:
        return {
            "runs": [run.als_json() for run in self.runs],
            "verslag": self.verslag,
            "fout": self.fout,
        }


# --------------------------------------------------------------------------------------
# De meting zelf: een fork per aanroep
# --------------------------------------------------------------------------------------


def _kib() -> int:
    """Het geheugenhoogwatermerk van dit proces in KiB, uit `ru_maxrss`.

    De eenheid van `ru_maxrss` is platformafhankelijk (KiB op Linux, bytes op
    macOS/BSD); `MAXRSS_DELER` rekent hem naar KiB om.
    """
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) // MAXRSS_DELER


def _kindwerk(bouw: Callable[[], Werk], pijp: int) -> None:
    """Bouwt het werk, meet de aanroep en schrijft het resultaat als JSON in de pijp.

    Draait uitsluitend in het kindproces en eindigt daar met `os._exit`, zodat de
    buffers en `atexit`-haken van de ouder niet een tweede keer aflopen.
    """
    code = 0
    boodschap: dict[str, Any] = {}
    try:
        werk = bouw()
        basis = _kib()
        begin = time.perf_counter()
        resultaat = werk.uitvoeren()
        seconden = time.perf_counter() - begin
        piek = _kib()
        boodschap = {
            "seconden": seconden,
            "basis_kib": basis,
            "piek_kib": piek,
            "verslag": werk.verslag(resultaat),
        }
    except BaseException as fout:  # noqa: B036 -- de ouder rapporteert wat er misging
        boodschap = {"fout": f"{type(fout).__name__}: {fout}"}
        code = 1
    try:
        with os.fdopen(pijp, "w", encoding="utf-8") as stroom:
            json.dump(boodschap, stroom)
    finally:
        os._exit(code)


def _meet(bouw: Callable[[], Werk]) -> tuple[Run | None, Verslag, str | None]:
    """Draait `bouw()` in een kindproces en levert de meting, het verslag en een fout."""
    lezen, schrijven = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(lezen)
        _kindwerk(bouw, schrijven)
        raise AssertionError("onbereikbaar")  # pragma: no cover
    os.close(schrijven)
    with os.fdopen(lezen, encoding="utf-8") as stroom:
        rauw = stroom.read()
    _, status = os.waitpid(pid, 0)

    if not rauw:
        signaal = os.WTERMSIG(status) if os.WIFSIGNALED(status) else 0
        reden = f"gedood door signaal {signaal}" if signaal else f"eindigde met status {status}"
        return None, {}, f"het kindproces gaf niets terug en {reden}"
    try:
        boodschap = json.loads(rauw)
    except json.JSONDecodeError as fout:
        # Een halve of vervuilde pijp (het kind sneuvelde midden in de dump, of iets
        # schreef mee) hoort dit pad als MISLUKT te melden, net als de lege pijp
        # hierboven -- en niet als een onbehandelde uitzondering dwars door `main`.
        return None, {}, f"het kindproces gaf onleesbare JSON terug ({fout}): {rauw[:200]!r}"
    if "fout" in boodschap:
        return None, {}, str(boodschap["fout"])
    run = Run(
        seconden=float(boodschap["seconden"]),
        basis_kib=int(boodschap["basis_kib"]),
        piek_kib=int(boodschap["piek_kib"]),
    )
    return run, dict(boodschap["verslag"]), None


# --------------------------------------------------------------------------------------
# De vier paden
# --------------------------------------------------------------------------------------


def _bouw_load_dataset(cfg: Instellingen) -> Werk:
    """De leesweg: parsen, indexeren en het domeinmodel opbouwen.

    Met de gebundelde ontologie (`ontology_paths=None`), zoals nlriochecker hem
    aanroept, en zonder cache -- `load_dataset` kent er zelf geen; `cache.laad_met_cache`
    is de gecachete weg en die blijft hier buiten beeld.
    """
    from gwsw_orox_helpers.dataset import load_dataset

    def uitvoeren() -> Any:
        return load_dataset(cfg.bron, fallback_encoding=cfg.fallback_encoding)

    def verslag(dataset: Any) -> Verslag:
        return {
            "triples": len(dataset.graph),
            "knopen": len(dataset.nodes),
            "strengen": len(dataset.conduits),
            "geometriefouten": len(dataset.geometry_errors),
            "klassenhierarchie_bekend": bool(dataset.klassenhierarchie_bekend),
            "terugvalcodering_gebruikt": dataset.decode_fallback is not None,
        }

    return Werk(uitvoeren, verslag)


def _bouw_schrijf_orox(cfg: Instellingen) -> Werk:
    """De schrijfweg: de quadstroom van de parser rechtstreeks naar de serializer."""
    from gwsw_orox_helpers.schrijven import schrijf_orox

    doel = cfg.werkmap / "schrijf" / f"{cfg.bron.stem}__terug.ttl"
    doel.parent.mkdir(parents=True, exist_ok=True)

    def uitvoeren() -> Any:
        schrijf_orox(cfg.bron, doel, fallback_encoding=cfg.fallback_encoding)
        return doel

    def verslag(pad: Any) -> Verslag:
        return {"doel": str(pad), "bytes": Path(pad).stat().st_size}

    return Werk(uitvoeren, verslag)


def _bouw_clip_orox(cfg: Instellingen) -> Werk:
    """De knip: een plan over de hele bron en daarna een gefilterde stroom per vlak."""
    from gwsw_orox_helpers.clip import clip_orox

    uitmap = cfg.werkmap / "delen"

    def uitvoeren() -> Any:
        return clip_orox(
            cfg.bron,
            cfg.grenzen,
            uitmap,
            sleutel=cfg.sleutel,
            fallback_encoding=cfg.fallback_encoding,
        )

    def verslag(delen: Any) -> Verslag:
        paden = [Path(pad) for pad in delen]
        return {
            "delen": [str(pad) for pad in paden],
            "bytes": [pad.stat().st_size for pad in paden],
        }

    return Werk(uitvoeren, verslag)


def _bouw_merge_orox(cfg: Instellingen, delen: Sequence[Path]) -> Werk:
    """De hereniging: de delen van de knip weer tot de bron."""
    from gwsw_orox_helpers.clip import merge_orox

    doel = cfg.werkmap / "samen" / f"{cfg.bron.stem}__samen.ttl"
    doel.parent.mkdir(parents=True, exist_ok=True)
    lijst = [Path(pad) for pad in delen]

    def uitvoeren() -> Any:
        merge_orox(lijst, doel)
        return doel

    def verslag(pad: Any) -> Verslag:
        return {
            "doel": str(pad),
            "bytes": Path(pad).stat().st_size,
            "delen": [str(deel) for deel in lijst],
        }

    return Werk(uitvoeren, verslag)


# --------------------------------------------------------------------------------------
# Profileren
# --------------------------------------------------------------------------------------


def _profielwerk(bouw: Callable[[], Werk], doel: Path, naam: str) -> Callable[[], Werk]:
    """Wikkelt een pad in `cProfile` en schrijft de top-25 naar `doel`.

    Twee sorteringen in hetzelfde bestand: cumulatief (welke deelboom kost de tijd) en
    tottime (welke functie zelf traag is). De tijden onder cProfile zijn hoger dan de
    gemeten tijden -- de profiler telt elke aanroep -- en horen dus niet in de meting
    thuis; ze staan alleen in de kop van het profiel.
    """

    def bouw_geprofileerd() -> Werk:
        import cProfile
        import pstats

        werk = bouw()

        def uitvoeren() -> Any:
            profiler = cProfile.Profile()
            begin = time.perf_counter()
            resultaat = profiler.runcall(werk.uitvoeren)
            duur = time.perf_counter() - begin
            doel.parent.mkdir(parents=True, exist_ok=True)
            with doel.open("w", encoding="utf-8") as stroom:
                stroom.write(
                    f"# {naam} onder cProfile: {duur:.1f} s wandklok "
                    f"(inclusief profileroverhead; de meting staat in de JSON)\n"
                )
                for sortering in ("cumulative", "tottime"):
                    stroom.write(f"\n# ---- top 25 op {sortering} ----\n")
                    stats = pstats.Stats(profiler, stream=stroom)
                    stats.strip_dirs().sort_stats(sortering).print_stats(25)
            return resultaat

        return Werk(uitvoeren, werk.verslag)

    return bouw_geprofileerd


# --------------------------------------------------------------------------------------
# Uitvoer
# --------------------------------------------------------------------------------------


def _tabel(uitkomsten: list[Uitkomst]) -> str:
    """De metingen als uitgelijnde tabel."""
    kop = ("pad", "n", "tijd min (s)", "tijd med (s)", "tijd max (s)", "piek (MiB)", "basis (MiB)")
    regels: list[tuple[str, ...]] = [kop]
    for uitkomst in uitkomsten:
        if uitkomst.fout is not None or not uitkomst.runs:
            regels.append((uitkomst.naam, "0", "-", "-", "-", "-", "-"))
            continue
        tijden = uitkomst.tijden
        # `statistics.median` en niet `tijden[len(tijden) // 2]`: bij een even aantal
        # metingen wees die index de bovenste middelste aan en niet het gemiddelde van
        # de twee middelste -- met twee metingen was de "mediaan" dus de maximumtijd.
        mediaan = statistics.median(tijden)
        regels.append(
            (
                uitkomst.naam,
                str(len(tijden)),
                f"{tijden[0]:.2f}",
                f"{mediaan:.2f}",
                f"{tijden[-1]:.2f}",
                f"{uitkomst.piek_mib:.0f}",
                f"{uitkomst.basis_mib:.0f}",
            )
        )
    breedtes = [max(len(regel[kolom]) for regel in regels) for kolom in range(len(kop))]
    opgemaakt = []
    for nummer, regel in enumerate(regels):
        cellen = [regel[0].ljust(breedtes[0])]
        cellen += [regel[kolom].rjust(breedtes[kolom]) for kolom in range(1, len(kop))]
        opgemaakt.append("  ".join(cellen))
        if nummer == 0:
            opgemaakt.append("-" * len(opgemaakt[0]))
    return "\n".join(opgemaakt)


def _versie(pakket: str) -> str:
    try:
        return metadata.version(pakket)
    except metadata.PackageNotFoundError:  # pragma: no cover -- alleen buiten de venv
        return "onbekend"


def _commit() -> str:
    """De HEAD van deze werkboom, zodat een meting bij een stand hoort."""
    try:
        uit = subprocess.run(
            ["git", "-C", str(WORTEL), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover
        return "onbekend"
    return uit.stdout.strip()


def _meta(cfg: Instellingen, herhalingen: int) -> dict[str, Any]:
    return {
        "tijdstip": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "commit": _commit(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "cpu": platform.processor() or platform.machine(),
        "versies": {naam: _versie(naam) for naam in ("pyoxigraph", "rdflib", "shapely")},
        "bron": {"pad": str(cfg.bron), "bytes": cfg.bron.stat().st_size},
        "grenzen": str(cfg.grenzen),
        "sleutel": cfg.sleutel,
        "fallback_encoding": cfg.fallback_encoding,
        "herhalingen": herhalingen,
        "werkmap": str(cfg.werkmap),
        "tijdmaat": "time.perf_counter om de bibliotheekaanroep heen (wandklok, seconden)",
        "geheugenmaat": (
            f"resource.getrusage(RUSAGE_SELF).ru_maxrss (op dit platform in "
            f"{MAXRSS_EENHEID}), omgerekend naar KiB en gemeten in een eigen kindproces "
            f"per meting; basis = het merk vlak voor de aanroep (na de imports), "
            f"piek = het merk erna"
        ),
    }


# --------------------------------------------------------------------------------------
# Regie
# --------------------------------------------------------------------------------------


def _argumenten(argv: Sequence[str] | None) -> argparse.Namespace:
    ontleder = argparse.ArgumentParser(
        description="Meet de vier hete paden van gwsw-orox-helpers op een OroX-export.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ontleder.add_argument("--ttl", type=Path, default=BRON, help="de te meten OroX-export")
    ontleder.add_argument("--grenzen", type=Path, default=GRENZEN, help="grenslaag voor de clip")
    ontleder.add_argument("--sleutel", default=SLEUTEL, help="property met de vlaknaam")
    ontleder.add_argument(
        "--fallback-encoding",
        default=FALLBACK_ENCODING,
        help="terugvalcodering voor bronnen die geen zuivere UTF-8 zijn ('' = geen)",
    )
    ontleder.add_argument(
        "--paden",
        default=",".join(PADEN),
        help=f"komma-gescheiden selectie uit {', '.join(PADEN)}",
    )
    ontleder.add_argument(
        "--herhalingen", type=int, default=1, help="metingen per pad (de bestanden zijn groot)"
    )
    ontleder.add_argument("--json", type=Path, default=None, help="schrijf de metingen hierheen")
    ontleder.add_argument(
        "--profiel-map",
        type=Path,
        default=None,
        help=f"cProfile-uitvoer voor {', '.join(PROFIELPADEN)} in deze map",
    )
    ontleder.add_argument(
        "--werkmap",
        type=Path,
        default=None,
        help="map voor de uitvoerbestanden (standaard: een tijdelijke map die opgeruimd wordt)",
    )
    return ontleder.parse_args(argv)


def _gekozen_paden(ruw: str) -> list[str]:
    gekozen = [naam.strip() for naam in ruw.split(",") if naam.strip()]
    onbekend = [naam for naam in gekozen if naam not in PADEN]
    if onbekend:
        raise SystemExit(f"onbekend pad: {', '.join(onbekend)}; kies uit {', '.join(PADEN)}")
    return [naam for naam in PADEN if naam in gekozen]


def _delen_op_schijf(cfg: Instellingen) -> list[Path]:
    """De clipdelen die er al liggen, in de volgorde waarin de clip ze schreef."""
    uitmap = cfg.werkmap / "delen"
    return sorted(uitmap.glob("*.ttl")) if uitmap.is_dir() else []


def main(argv: Sequence[str] | None = None) -> int:
    """Meet, schrijft de tabel op stdout en desgevraagd de JSON en de profielen."""
    argumenten = _argumenten(argv)
    bron = Path(argumenten.ttl)
    grenzen = Path(argumenten.grenzen)
    if not bron.exists():
        print(f"{bron} ligt niet op deze machine; er valt niets te meten.")
        return 0
    if not grenzen.exists():
        print(f"{grenzen} ontbreekt; er valt niets te knippen.")
        return 0
    if argumenten.herhalingen < 1:
        raise SystemExit("--herhalingen moet minstens 1 zijn")

    gekozen = _gekozen_paden(argumenten.paden)
    tijdelijk = argumenten.werkmap is None
    werkmap = Path(tempfile.mkdtemp(prefix="orox-benchmark-")) if tijdelijk else argumenten.werkmap
    werkmap.mkdir(parents=True, exist_ok=True)
    cfg = Instellingen(
        bron=bron,
        grenzen=grenzen,
        sleutel=argumenten.sleutel,
        fallback_encoding=argumenten.fallback_encoding or None,
        werkmap=werkmap,
    )

    try:
        uitkomsten, profielen = _draai(cfg, gekozen, argumenten)
    finally:
        if tijdelijk:
            shutil.rmtree(werkmap, ignore_errors=True)

    print()
    print(_tabel(uitkomsten))
    print()
    for uitkomst in uitkomsten:
        if uitkomst.fout is not None:
            print(f"{uitkomst.naam}: MISLUKT -- {uitkomst.fout}")
        elif uitkomst.verslag:
            print(f"{uitkomst.naam}: {json.dumps(uitkomst.verslag, ensure_ascii=False)}")
    for naam, pad in profielen.items():
        print(f"profiel {naam}: {pad}")

    if argumenten.json is not None:
        document = {
            "meta": _meta(cfg, argumenten.herhalingen),
            "paden": {uitkomst.naam: uitkomst.als_json() for uitkomst in uitkomsten},
            "profielen": {naam: str(pad) for naam, pad in profielen.items()},
        }
        doel = Path(argumenten.json)
        doel.parent.mkdir(parents=True, exist_ok=True)
        doel.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"JSON: {doel}")

    return 1 if any(uitkomst.fout is not None for uitkomst in uitkomsten) else 0


def _draai(
    cfg: Instellingen, gekozen: Sequence[str], argumenten: argparse.Namespace
) -> tuple[list[Uitkomst], dict[str, Path]]:
    """De metingen en daarna de profielen; de delen van de clip reizen mee naar de merge."""
    uitkomsten: list[Uitkomst] = []
    delen: list[Path] = []

    for naam in gekozen:
        if naam == "merge_orox" and not delen:
            delen = _delen_op_schijf(cfg)
        if naam == "merge_orox" and not delen:
            print("merge_orox: eerst clip_orox draaien om de delen te maken (niet gemeten)...")
            _, verslag, fout = _meet(lambda: _bouw_clip_orox(cfg))
            if fout is not None:
                uitkomsten.append(Uitkomst(naam, fout=f"voorbereidende clip mislukte: {fout}"))
                continue
            delen = [Path(pad) for pad in verslag["delen"]]

        uitkomst = Uitkomst(naam)
        for nummer in range(argumenten.herhalingen):
            bouw = _bouwer(naam, cfg, delen)
            print(f"{naam}: meting {nummer + 1}/{argumenten.herhalingen}...", flush=True)
            run, verslag, fout = _meet(bouw)
            if run is None:
                uitkomst.fout = fout
                break
            uitkomst.runs.append(run)
            uitkomst.verslag = verslag
            if naam == "clip_orox":
                delen = [Path(pad) for pad in verslag["delen"]]
        uitkomsten.append(uitkomst)

    profielen: dict[str, Path] = {}
    if argumenten.profiel_map is not None:
        for naam in gekozen:
            if naam not in PROFIELPADEN:
                continue
            doel = Path(argumenten.profiel_map) / f"profiel_{naam}.txt"
            print(f"{naam}: profileren...", flush=True)
            bouw = _profielwerk(_bouwer(naam, cfg, delen), doel, naam)
            _, _, fout = _meet(bouw)
            if fout is not None:
                print(f"profiel {naam}: MISLUKT -- {fout}")
                continue
            profielen[naam] = doel
    return uitkomsten, profielen


def _bouwer(naam: str, cfg: Instellingen, delen: Sequence[Path]) -> Callable[[], Werk]:
    """De bouwfunctie van een pad; hij draait pas in het kindproces."""
    if naam == "load_dataset":
        return lambda: _bouw_load_dataset(cfg)
    if naam == "schrijf_orox":
        return lambda: _bouw_schrijf_orox(cfg)
    if naam == "clip_orox":
        return lambda: _bouw_clip_orox(cfg)
    if naam == "merge_orox":
        return lambda: _bouw_merge_orox(cfg, delen)
    raise SystemExit(f"onbekend pad: {naam}")  # pragma: no cover


if __name__ == "__main__":
    sys.exit(main())
