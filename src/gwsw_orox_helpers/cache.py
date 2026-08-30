"""De geparseerde dataset bewaren, zodat een tweede run niet opnieuw hoeft te parsen.

Gemeten op De Wolden en Hoogeveen: de structuren teruglezen kost circa 2 s en de graafindex
uit de pickle teruglezen circa 6 s (91 MB; de rdflib-graaf was circa 30 s). Picklen wint het
van warm herbouwen uit de pyoxigraph-stream, dat circa 20 s kost -- de parse zelf is snel,
maar de indexopbouw met rdflib-termen niet. De graaf wordt bovendien pas ingelezen als een
check hem aanraakt; wie alleen geometrie- en netwerkchecks draait, betaalt hem niet.

Het gevaar van een cache is dat hij achterloopt. De sleutel bevat daarom niet alleen
de inhoud van de invoerbestanden maar ook de broncode van de lader en de versies van
rdflib, shapely en pyoxigraph: wijzigt daar iets, dan is het een andere sleutel en
wordt er opnieuw ingelezen.
"""

from __future__ import annotations

import logging
import os
import pickle
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, fields, replace
from functools import partial
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

import pyoxigraph
import rdflib
import shapely

from gwsw_orox_helpers import codering as codering_module
from gwsw_orox_helpers import dataset as dataset_module
from gwsw_orox_helpers import domein as domein_module
from gwsw_orox_helpers import geometry as geometry_module
from gwsw_orox_helpers import graaf as graaf_module
from gwsw_orox_helpers import inlezen as inlezen_module
from gwsw_orox_helpers import klassen as klassen_module
from gwsw_orox_helpers import namen as namen_module
from gwsw_orox_helpers import ontologie as ontologie_module
from gwsw_orox_helpers import rdfmotor as rdfmotor_module
from gwsw_orox_helpers.dataset import GwswDataset, load_dataset, ontologiepaden
from gwsw_orox_helpers.graaf import GraafIndex
from gwsw_orox_helpers.voortgang import NUL_VOORTGANG, Voortgang

logger = logging.getLogger(__name__)

# Losstaand van de bestandshashes, zodat een test hem kan verzetten.
LADER_VERSIE = "1"

BESTAND_STRUCTUREN = "structuren.pickle"
BESTAND_GRAAF = "graaf.pickle"

# "De lader" is niet één bestand maar de hele leeslaag: `dataset` biedt hem aan,
# `inlezen` leest de graaf uit, `domein` draagt de objecten die gecachet worden,
# `klassen` leidt de afsluitingen af, `codering` bepaalt hoe de bytes tekst worden,
# `geometry` hoe een GML-literaal een shapely-object wordt en `namen` welke IRI's dat
# allemaal opzoekt. `ontologie` staat erbij sinds `load_dataset` er `kenmerk_property`
# uit afleidt (ATTR-014): die waarde wordt mee gecachet, dus een wijziging aan de
# afleiding moet de sleutel veranderen. `graaf` draagt sinds de eigen graafindexen de
# termconversie en de volgordegarantie van de gecachete graaf. `rdfmotor` staat erbij
# omdat `inlezen._parse` zijn quads daarlangs haalt: wie daar de aanroep van de motor
# verandert (een ander formaat, een andere invoervorm, een `lenient`-vlag) verandert wat
# er gelezen wordt, en dus hoort dat een andere sleutel te zijn. Dat de schrijfweg dezelfde
# module gebruikt, betekent dat een wijziging aan alléén `serialiseer_turtle` de leescache
# ook ongeldig maakt; dat is de goede kant om op te vergissen -- te vaak herbouwen kost één
# lezing, te weinig herbouwen geeft stil een verouderd antwoord. Wie hier een module
# vergeet, krijgt geen fout maar een cache
# die na een wijziging aan de lader de oude lezing blijft teruggeven;
# `tests/test_cache.py` parametriseert over deze tuple en bewaakt daarmee elke module erin
# én de lijst zelf.
LADERMODULES = (
    codering_module,
    dataset_module,
    domein_module,
    geometry_module,
    graaf_module,
    inlezen_module,
    klassen_module,
    namen_module,
    ontologie_module,
    rdfmotor_module,
)


@dataclass(frozen=True)
class CacheUitslag:
    """Waar de dataset vandaan kwam en wat dat kostte."""

    bron: str  # 'cache' of 'bestand'
    sleutel: str
    seconden: float
    melding: str = ""


class LuieGraaf:
    """Een graafindex die pas van schijf komt als er iets uit gevraagd wordt.

    De checks gebruiken de graaf voor onderdelen die niet in de structuren zitten
    (hasPart, hasConnection, labels van drempels). Dat is een minderheid van de
    checks, en de graaf teruglezen kost tot een minuut; hem pas laden bij het eerste
    gebruik scheelt die tijd in alle andere runs.

    Blijkt de graafcache zelf beschadigd (de structurencache was dat niet, anders
    was er nooit een `LuieGraaf` gemaakt), dan is dat geen fout: `_herstel` leest
    de graaf alsnog uit de brondata en de cache wordt opnieuw weggeschreven, zodat
    de volgende aanraking weer de snelle weg neemt. `cache.py` stelt die functie
    samen; deze klasse kent zelf geen paden naar de brondata en geen `load_dataset`.
    """

    def __init__(self, pad: Path, herstel: Callable[[], GraafIndex]) -> None:
        self._pad = pad
        self._herstel = herstel
        self._graaf: GraafIndex | None = None

    def _geladen(self) -> GraafIndex:
        """Leest de graaf de eerste keer dat er iets uit gevraagd wordt."""
        if self._graaf is None:
            begin = time.perf_counter()
            try:
                with self._pad.open("rb") as bestand:
                    self._graaf = pickle.load(bestand)
            except (pickle.UnpicklingError, EOFError, TypeError, AttributeError, OSError) as fout:
                logger.warning(
                    "De graafcache in %s is onbruikbaar (%s); graaf opnieuw "
                    "ingelezen uit de brondata.",
                    self._pad,
                    fout,
                )
                self._graaf = self._herstel()
                _schrijf_atomair(self._pad, self._graaf)
            logger.info(
                "Graaf van schijf gelezen in %.1f s (%d triples).",
                time.perf_counter() - begin,
                len(self._graaf),
            )
        return self._graaf

    def __getattr__(self, naam: str) -> object:
        """Alles wat een graaf kan, kan deze plaatsvervanger ook."""
        return getattr(self._geladen(), naam)

    def __len__(self) -> int:
        """Het aantal triples."""
        return len(self._geladen())

    def __contains__(self, triple: Any) -> bool:
        """Of een triple in de graaf staat."""
        return triple in self._geladen()


def cachesleutel(
    dataset_path: Path,
    ontology_paths: list[Path] | None = None,
    fallback_encoding: str | None = None,
) -> str:
    """De sleutel van deze combinatie van invoer, lader, terugvalcodering en bibliotheken.

    `ontology_paths` gaat door dezelfde `ontologiepaden` als `load_dataset`: wat de
    lezing gebruikt is wat de sleutel hasht. Zonder die stap zou een aanroep zonder
    ontologieopgave een sleutel krijgen waar de gebundelde ontologie niet in zit, en
    dan geeft de cache na het vervangen van die ontologie de oude lezing terug.

    De terugvalcodering telt mee: ze bepaalt hoe niet-UTF-8-bytes gelezen worden
    (zie `codering.py`), en een dataset die met een andere codering ingelezen is,
    is een andere dataset. Zonder haar in de sleutel zou de cache bij een andere
    encoding-keuze een met de verkeerde codering ingelezen dataset teruggeven.
    `None` -- geen terugval -- is zo'n keuze en krijgt dus een eigen sleutel.
    """
    haas = sha256()
    haas.update(LADER_VERSIE.encode("utf-8"))
    haas.update(
        f"rdflib{rdflib.__version__}shapely{shapely.__version__}"
        f"pyoxigraph{pyoxigraph.__version__}".encode()
    )
    haas.update(str(fallback_encoding).encode("utf-8"))
    # De broncode van de hele leeslaag; welke modules dat zijn en waarom, staat bij
    # `LADERMODULES`.
    for module in LADERMODULES:
        # `__file__` is alleen None bij een namespace-pakket; dit zijn gewone modules.
        haas.update(Path(cast(str, module.__file__)).read_bytes())
    for pad in [Path(dataset_path), *sorted(ontologiepaden(ontology_paths))]:
        haas.update(pad.name.encode("utf-8"))
        haas.update(_bestandshash(pad).encode("utf-8"))
    return haas.hexdigest()[:32]


def _bestandshash(pad: Path) -> str:
    """De sha256 van een bestand, in blokken gelezen."""
    haas = sha256()
    with pad.open("rb") as bestand:
        for blok in iter(lambda: bestand.read(1 << 20), b""):
            haas.update(blok)
    return haas.hexdigest()


def standaard_cachemap() -> Path:
    """De cachemap volgens de XDG-conventie."""
    basis = os.environ.get("XDG_CACHE_HOME")
    return Path(basis or Path.home() / ".cache") / "gwsw-orox-helpers"


def laad_met_cache(
    dataset_path: Path,
    ontology_paths: list[Path] | None = None,
    cache_dir: Path | None = None,
    gebruik_cache: bool = True,
    fallback_encoding: str | None = None,
    *,
    voortgang: Voortgang = NUL_VOORTGANG,
) -> tuple[GwswDataset, CacheUitslag]:
    """Leest de dataset uit de cache, of leest hem in en legt hem weg.

    `ontology_paths` betekent hier hetzelfde als in `load_dataset` (zie
    `ontologiepaden`) en wordt hier één keer ingevuld, zodat de sleutel, de lezing en
    het herstel van een beschadigde graafcache alle drie dezelfde bestanden zien.

    Bij een cachetreffer wordt er niets geparseerd en start er dus geen laadfase:
    een balk die in nul seconden vol schiet zou suggereren dat het inlezen snel was
    in plaats van overgeslagen. De laadfase komt uit `load_dataset` zelf.
    """
    begin = time.perf_counter()
    ontology_paths = ontologiepaden(ontology_paths)
    if not gebruik_cache:
        dataset = load_dataset(dataset_path, ontology_paths, fallback_encoding, voortgang=voortgang)
        return dataset, CacheUitslag("bestand", "", time.perf_counter() - begin)

    sleutel = cachesleutel(dataset_path, ontology_paths, fallback_encoding)
    map_ = (cache_dir or standaard_cachemap()) / sleutel
    melding = ""
    pad_structuren = map_ / BESTAND_STRUCTUREN
    pad_graaf = map_ / BESTAND_GRAAF
    if pad_structuren.exists() and pad_graaf.exists():
        try:
            with pad_structuren.open("rb") as bestand:
                velden = pickle.load(bestand)
        except (pickle.UnpicklingError, EOFError, TypeError, AttributeError) as fout:
            melding = f"De cache in {map_} is onbruikbaar ({fout}); opnieuw ingelezen."
        else:
            # De structurencache is geldig; de graafcache wordt niet hier al
            # gelezen (dat kost tot een minuut) maar pas als een check hem
            # aanraakt. Is die dan beschadigd, dan herstelt LuieGraaf zichzelf
            # via deze functie in plaats van de hele run te laten crashen.
            herstel = partial(_herlees_graaf, dataset_path, ontology_paths, fallback_encoding)
            # `LuieGraaf` is geen GraafIndex-subklasse maar een plaatsvervanger die
            # alles doorgeeft; het veld verwacht een GraafIndex en krijgt hier zijn gedrag.
            luie = cast(GraafIndex, LuieGraaf(pad_graaf, herstel))
            dataset = replace(GwswDataset(graph=GraafIndex(), **velden), graph=luie)
            return dataset, CacheUitslag("cache", sleutel, time.perf_counter() - begin)

    dataset = load_dataset(dataset_path, ontology_paths, fallback_encoding, voortgang=voortgang)
    _schrijf(map_, dataset)
    return dataset, CacheUitslag("bestand", sleutel, time.perf_counter() - begin, melding)


def _herlees_graaf(
    dataset_path: Path, ontology_paths: list[Path], fallback_encoding: str | None
) -> GraafIndex:
    """Leest de graafindex opnieuw uit de brondata; herstelweg voor `LuieGraaf`.

    Alleen `cache.py` kent paden en `load_dataset`; `LuieGraaf` krijgt enkel deze
    kant-en-klare functie mee en hoeft van beide dus niets te weten.
    """
    return load_dataset(dataset_path, ontology_paths, fallback_encoding).graph


def _schrijf(map_: Path, dataset: GwswDataset) -> None:
    """Legt structuren en graaf weg, elk via een tijdelijk bestand.

    De niet-init-velden (de memo's `_resolved_nodes` en `_types_memo`) blijven buiten de
    pickle:
    `GwswDataset(**velden)` zou erop stuklopen, en zo'n memo hoort elke instantie
    vers op te bouwen. De lijst is afgeleid uit de dataclass zelf, zodat een volgend
    niet-init-veld niet stil het cacheleespad breekt.
    """
    overslaan = {"graph"} | {f.name for f in fields(GwswDataset) if not f.init}
    velden = {naam: waarde for naam, waarde in vars(dataset).items() if naam not in overslaan}
    _schrijf_atomair(map_ / BESTAND_STRUCTUREN, velden)
    _schrijf_atomair(map_ / BESTAND_GRAAF, dataset.graph)


def _schrijf_atomair(pad: Path, inhoud: object) -> None:
    """Schrijft eerst naar een tijdelijk bestand en hernoemt dan atomisch.

    Zonder die omweg laat een afgebroken schrijfactie een half bestand achter dat
    een volgende lezer als geldige cache zou lezen. Zowel het wegschrijven van een
    verse dataset als het zelfherstel van een beschadigde `LuieGraaf` lopen via
    deze functie, dus de garantie geldt voor beide schrijfmomenten.

    De naam van het tijdelijke bestand bevat het proces-ID: twee gelijktijdige
    runs op dezelfde sleutel (dezelfde invoer, dezelfde lader) schreven anders
    door elkaar heen naar dezelfde tijdelijke naam en het laatste `replace()` kon
    het half geschreven bestand van de ander overnemen.
    """
    pad.parent.mkdir(parents=True, exist_ok=True)
    beschrijving, tijdelijk_pad = tempfile.mkstemp(
        prefix=f"{pad.name}.{os.getpid()}.", suffix=".tijdelijk", dir=pad.parent
    )
    tijdelijk = Path(tijdelijk_pad)
    try:
        with os.fdopen(beschrijving, "wb") as bestand:
            pickle.dump(inhoud, bestand, protocol=5)
        tijdelijk.replace(pad)
    except BaseException:
        tijdelijk.unlink(missing_ok=True)
        raise
