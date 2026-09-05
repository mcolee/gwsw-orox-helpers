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

import copyreg
import logging
import os
import pickle
import re
import tempfile
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, fields, replace
from functools import partial
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

import pyoxigraph
import rdflib
import shapely
from rdflib import BNode, Literal, URIRef
from rdflib.term import Node as RdfNode

from gwsw_orox_helpers import bestand as bestand_module
from gwsw_orox_helpers import codering as codering_module
from gwsw_orox_helpers import dataset as dataset_module
from gwsw_orox_helpers import domein as domein_module
from gwsw_orox_helpers import geometry as geometry_module
from gwsw_orox_helpers import graaf as graaf_module
from gwsw_orox_helpers import inlezen as inlezen_module
from gwsw_orox_helpers import klassen as klassen_module
from gwsw_orox_helpers import namen as namen_module
from gwsw_orox_helpers import netwerk as netwerk_module
from gwsw_orox_helpers import ontologie as ontologie_module
from gwsw_orox_helpers import rdfmotor as rdfmotor_module
from gwsw_orox_helpers.bronnen import GEBUNDELDE_VERSIES, gebundelde_ontologie_voor
from gwsw_orox_helpers.dataset import GwswDataset, load_dataset, ontologiepaden
from gwsw_orox_helpers.errors import BestandError
from gwsw_orox_helpers.graaf import (
    GraafIndex,
    _literal_snel,
    _literal_string_snel,
    _uriref_snel,
)
from gwsw_orox_helpers.voortgang import NUL_VOORTGANG, Voortgang

logger = logging.getLogger(__name__)

# Losstaand van de bestandshashes, zodat een test hem kan verzetten. Bij "2" sinds
# issue #45: de cache is een vertrouwensgrens geworden (rechtencheck vóór elke
# `pickle.load`), dus bestaande caches uit vóór die verharding vervallen één keer.
# Bij "3" sinds issue #63: de schrijfweg pickelt de rdflib-termen via een `dispatch_table`
# (`_SnellePickler`) naar de snelpaden van `graaf`, wat de picklevorm verandert. `cache.py`
# staat niet in `LADERMODULES` (het staat in `BUITEN_DE_SLEUTEL`), dus die vormwijziging
# invalideert de sleutel niet vanzelf; deze bump doet dat wel. Bestaande caches worden zo
# één keer herbouwd -- bedoelde mechaniek.
LADER_VERSIE = "3"

BESTAND_STRUCTUREN = "structuren.pickle"
BESTAND_GRAAF = "graaf.pickle"

# Eén foutbeleid rond beide `pickle.load`-plekken (issue #48). `pickle.load` is in feite een
# bytecode-interpreter: een onbruikbare pickle kan bij het laden vrijwel elke uitzondering
# gooien. De fuzz uit #48 vond naast `UnpicklingError` ook `ValueError` (een vreemd
# protocolbyte), `UnicodeDecodeError` en `OSError`; een opgesomde tuple is daarmee per
# definitie incompleet en zou vals vertrouwen geven. "Onbruikbaar" betekent gewoon: het
# laden gaf geen bruikbaar object, hoe dan ook -- en dan is herinlezen het juiste antwoord.
# Daarom vangen we breed op `Exception` (nooit `BaseException`: `KeyboardInterrupt` en
# `SystemExit` horen door te lopen). De rechtencheck vóór het laden (`_cachepad_vertrouwd`,
# issue #45) blijft de bewaker tegen kwaadaardige `__reduce__`-payloads; dit beleid gaat
# alleen over welk fouttype "onbruikbaar" dekt.
_PICKLE_FOUTEN: type[Exception] = Exception

# "De lader" is niet één bestand maar de hele leeslaag: `dataset` biedt hem aan,
# `bestand` maakt van een TTL-bestand een gevulde index, `inlezen` leest die index uit,
# `domein` draagt de objecten die gecachet worden, `netwerk` beantwoordt de netwerkvragen
# die de checks daarna over die objecten stellen,
# `klassen` leidt de afsluitingen af, `codering` bepaalt hoe de bytes tekst worden,
# `geometry` hoe een GML-literaal een shapely-object wordt en `namen` welke IRI's dat
# allemaal opzoekt. `ontologie` staat erbij sinds `load_dataset` er `kenmerk_property`
# uit afleidt (ATTR-014): die waarde wordt mee gecachet, dus een wijziging aan de
# afleiding moet de sleutel veranderen. `graaf` draagt sinds de eigen graafindexen de
# termconversie en de volgordegarantie van de gecachete graaf. `rdfmotor` staat erbij
# omdat `bestand._parse` zijn quads daarlangs haalt: wie daar de aanroep van de motor
# verandert (een ander formaat, een andere invoervorm, een `lenient`-vlag) verandert wat
# er gelezen wordt, en dus hoort dat een andere sleutel te zijn. Dat de schrijfweg dezelfde
# module gebruikt, betekent dat een wijziging aan alléén `serialiseer_turtle` de leescache
# ook ongeldig maakt; dat is de goede kant om op te vergissen -- te vaak herbouwen kost één
# lezing, te weinig herbouwen geeft stil een verouderd antwoord. Wie hier een module
# vergeet, krijgt geen fout maar een cache
# die na een wijziging aan de lader de oude lezing blijft teruggeven;
# `tests/test_cache.py` parametriseert over deze tuple en bewaakt daarmee elke module erin
# én de lijst zelf.
#
# `bestand` kwam er bij issue #26 bij, toen het parseerpad uit `inlezen` verhuisde, en
# `netwerk` bij issue #27, toen de wandeling omhoog uit `dataset` verhuisde. Dat is allebei
# verplaatste en niet gewijzigde code, maar de sleutel hasht *bestanden* en niet functies:
# de hersnit verandert hem dus één keer en bestaande caches worden één keer opnieuw
# opgebouwd. Dat is de bedoelde werking (zie `docs/architectuur.md`, "De cache leest mee
# met de lader") en geen gedragswijziging -- de tweede run is weer een treffer.
#
# `netwerk` draait weliswaar ná het laden -- van zijn uitkomst wordt niets gepickeld -- maar
# hij hoort hier toch, en wel om de sterkste reden die deze lijst kent: tot #27 stond die
# code ín `dataset.py` en telde zij dus al mee. Hem er nu buiten laten zou de garantie
# stilzwijgend versmallen op het moment dat de code alleen van bestand wisselt. Te vaak
# herbouwen kost één lezing; te weinig herbouwen geeft stil een verouderd antwoord.
LADERMODULES = (
    bestand_module,
    codering_module,
    dataset_module,
    domein_module,
    geometry_module,
    graaf_module,
    inlezen_module,
    klassen_module,
    namen_module,
    netwerk_module,
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

    **Het leescontract staat er expliciet op** (issue #34): de vijf bewerkingen uit de
    moduledocstring van `graaf` -- `objects`, `subjects`, `value`, `subject_objects` en
    `heeft_subject` -- plus `__len__` en `__contains__`, elk met dezelfde handtekening
    als op `GraafIndex` en elk niets anders doend dan doorgeven. Dat is geen dienst aan
    de aanroeper (die kreeg via `__getattr__` hetzelfde antwoord) maar aan mypy, en de
    winst valt in twee helften uiteen:

    - **nu al** wordt de doorgifte zelf gecontroleerd. `self._geladen()` is een
      `GraafIndex`, dus mypy leest hier vijf echte aanroepen op dat type; hernoemt of
      verschuift `GraafIndex` een parameter, dan wordt *dit bestand* rood. Onder
      `__getattr__` gebeurde dat niet: die forwardde blind en de fout viel pas als
      `AttributeError` op de leesweg. `tests/test_cache.py` vergelijkt de vijf
      handtekeningen bovendien met `inspect.signature`, want de body doet de doorgifte
      positioneel en zou een hernoemde parameternaam overleven.
    - **pas na stap 2** ziet de aanroeper er iets van. `laad_met_cache` cast het geheel
      meteen naar `GraafIndex` (zie daar), dus binnen deze package houdt nog niemand een
      `LuieGraaf`-getypeerde verwijzing vast. Zolang die cast er staat, is dat deel van de
      winst geboekt maar niet geïnd.

    Met de methoden erop vervult `LuieGraaf` `graaf.GraafLezer` structureel;
    `tests/typecheck/graaflezer.py` is daar het bewijs van en
    `tests/test_cache.py::test_de_luie_graaf_geeft_per_leesbewerking_hetzelfde_als_een_echte_graafindex`
    houdt antwoord én laadmoment per bewerking gelijk aan een verse `GraafIndex`.

    Eén nuance bij "gedrag ongewijzigd", en ze gaat de goede kant op: het laden hangt nu
    aan de *aanroep* en niet meer aan de attribuuttoegang. `getattr(luie, "objects")` of
    `hasattr(luie, "value")` liep vroeger via `__getattr__` en las daarmee de pickle;
    nu vindt Python de methode op de klasse en gebeurt er niets tot je haar aanroept.
    Strikt luier dus, nooit gretiger -- en dat is precies waar deze klasse voor bestaat.
    """

    def __init__(self, pad: Path, herstel: Callable[[], GraafIndex]) -> None:
        self._pad = pad
        self._herstel = herstel
        self._graaf: GraafIndex | None = None

    def _geladen(self) -> GraafIndex:
        """Leest de graaf de eerste keer dat er iets uit gevraagd wordt.

        De graafpickle wordt vóór het depicklen getoetst (issue #45): pickle voert bij
        het laden code uit, dus een pickle van een vreemde eigenaar of schrijfbaar voor
        groep of anderen wordt niet geladen maar als "onbruikbaar" behandeld en uit de
        brondata hersteld -- hetzelfde pad als bij een beschadigde pickle.

        **Terugschrijven alleen naar een vertrouwde map.** Na herstel wordt de graaf
        teruggeschreven, maar alleen als de map eromheen te vertrouwen is
        (`_schrijf_indien_vertrouwd`). Was de pickle onvertrouwd, dan is de map eromheen
        verdacht en zou terugschrijven een verse pickle leggen in een map waar een ander
        bij kan; dan schrijven we niet en leest de volgende run opnieuw in. Bij een louter
        beschadigde pickle in een eigen, private map (mode 0o700) is terugschrijven wél
        veilig en herstelt het de snelle weg -- daar heelt het meteen ook de rechten van
        het bestand, want `_schrijf_atomair` maakt via `mkstemp` een vers bestand (0o600).

        **Procesbreed neveneffect: de cyclische GC ligt stil tijdens het depicklen**
        (issue #59). Om `pickle.load` heen legt deze methode de GC neer met
        `bestand._gc_uit` -- de graafpickle bouwt bovenop de al aanwezige structurenheap
        miljoenen rdflib-termen en dicts, en de cyclische GC loopt daar telkens opnieuw
        doorheen zonder dat er een kringetje kan ontstaan (de heropgebouwde objecten
        wijzen alleen naar beneden). Anders dan bij `load_dataset` gaat dit neveneffect
        lui vanuit de eerste leesbewerking van een check af, niet vanuit een expliciete
        productie-ingang; een afnemer hoort dat expliciet te weten. De oude GC-stand komt
        in `_gc_uit`'s eigen `finally` terug, ook als het laden halverwege afbreekt, en een
        aanroeper die de GC zelf al uit had houdt hem uit. Het antwoord van de graaf blijft
        identiek; alleen de laadtijd zakt (gemeten op het warme pad circa 7,8 s -> 3,5 s;
        de 2,75 s uit het issue was de meting in een leeg proces).
        """
        if self._graaf is None:
            begin = time.perf_counter()
            onvertrouwd = _cachepad_vertrouwd(self._pad)
            if onvertrouwd is not None:
                logger.warning(
                    "De graafcache in %s is onbruikbaar (%s); graaf opnieuw "
                    "ingelezen uit de brondata.",
                    self._pad,
                    onvertrouwd,
                )
                self._graaf = self._herstel()
                self._schrijf_indien_vertrouwd()
            else:
                try:
                    with self._pad.open("rb") as bestand, bestand_module._gc_uit():
                        self._graaf = pickle.load(bestand)
                except _PICKLE_FOUTEN as fout:
                    logger.warning(
                        "De graafcache in %s is onbruikbaar (%s); graaf opnieuw "
                        "ingelezen uit de brondata.",
                        self._pad,
                        fout,
                    )
                    self._graaf = self._herstel()
                    self._schrijf_indien_vertrouwd()
            logger.info(
                "Graaf van schijf gelezen in %.1f s (%d triples).",
                time.perf_counter() - begin,
                len(self._graaf),
            )
        return self._graaf

    def _schrijf_indien_vertrouwd(self) -> None:
        """Schrijft de herstelde graaf terug, maar alleen naar een vertrouwde map.

        De afweging staat in de docstring van `_geladen`: naar een onvertrouwde map
        (vreemde eigenaar of groep-/wereldschrijfbaar) schrijven we niet terug.
        """
        assert self._graaf is not None
        if _cachepad_vertrouwd(self._pad.parent) is None:
            # De graaf is al hersteld en in het geheugen; lukt het terugschrijven niet (een
            # read-only mount, een volle schijf), dan is dat een gemiste versnelling en geen
            # fout (issue #48, deel b). Zonder dit vangnet zou die `OSError` kaal uit
            # `_geladen` ontsnappen op het moment dat een check de graaf voor het eerst
            # aanraakt -- precies het pad dat `LuieGraaf` juist zonder crash moet afhandelen.
            try:
                _schrijf_atomair(self._pad, self._graaf)
            except OSError as fout:
                logger.warning(
                    "De herstelde graafcache kon niet naar %s weggeschreven worden (%s); "
                    "de volgende run leest hem opnieuw in.",
                    self._pad,
                    fout,
                )

    def objects(self, subject: RdfNode, predicate: RdfNode) -> Iterator[RdfNode]:
        """De objecten van (subject, predicate), in eerste-toevoegvolgorde."""
        return self._geladen().objects(subject, predicate)

    def subjects(self, predicate: RdfNode, object_: RdfNode) -> Iterator[RdfNode]:
        """De subjecten van (predicate, object), in eerste-toevoegvolgorde."""
        return self._geladen().subjects(predicate, object_)

    def value(self, subject: RdfNode, predicate: RdfNode) -> RdfNode | None:
        """Het eerste object van (subject, predicate), of None."""
        return self._geladen().value(subject, predicate)

    def subject_objects(self, predicate: RdfNode) -> Iterator[tuple[RdfNode, RdfNode]]:
        """Alle (subject, object)-paren van dit predicaat, in pos-groepering."""
        return self._geladen().subject_objects(predicate)

    def heeft_subject(self, term: RdfNode) -> bool:
        """Of deze term als subject in de graaf voorkomt."""
        return self._geladen().heeft_subject(term)

    def __getattr__(self, naam: str) -> object:
        """Vangnet voor alles buiten het leescontract hierboven.

        Sinds issue #34 gaan de vijf leesbewerkingen niet meer hierlangs (`__len__` en
        `__contains__` deden dat al niet: dunders worden op het type opgezocht, niet via
        `__getattr__`). Wat overblijft is de rest -- een `__getstate__`-achtige aanraking,
        `voeg_toe` of `vul_uit` van een afnemer die de plaatsvervanger als volwaardige
        index gebruikt, en elk lid dat `GraafIndex` er in de toekomst bij krijgt. Die
        blijven doorgegeven, en dus getypeerd als `object`.
        """
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

    **Bij `None` hasht de sleutel de bundel van de gedetecteerde versie** (issue #52), niet
    langer álle bundels: `cachesleutel` leest de `gwsw:`-prefix uit de kop van de dataset (een
    goedkope scan van de eerste paar KB, geen volledige parse) en hasht de bundel die
    `load_dataset._gebundelde_paden_voor_basis` dan kiest. Zo invalideert een toekomstige
    1.8-bundel een 1.6-cache niet meer. Levert de prefix-scan geen gebundelde versie op (geen
    `gwsw:`-prefix, of een niet-gebundelde versie), dan valt de sleutel terug op álle bundels
    -- de veilige kant: te vaak herbouwen kost één lezing, te weinig herbouwen geeft stil een
    verouderd antwoord.

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
    ontologiehash = _te_hashen_ontologiepaden(ontology_paths, Path(dataset_path))
    for pad in [Path(dataset_path), *sorted(ontologiehash)]:
        haas.update(pad.name.encode("utf-8"))
        haas.update(_bestandshash(pad).encode("utf-8"))
    return haas.hexdigest()[:32]


# De @prefix-regels staan bovenaan een OroX-export; deze grootte dekt ze ruim zonder het
# hele bestand te lezen. Op bytes en niet op tekst, zodat een niet-UTF-8-bron (cp850) geen
# decode van het hele bestand vergt -- de prefixregel zelf is ASCII. Zowel de Turtle-vorm
# (`@prefix gwsw: <...>`) als de SPARQL-vorm (`PREFIX gwsw: <...>`).
_KOP_BYTES = 1 << 13
_GWSW_PREFIX_PATROON = re.compile(rb"(?im)^[ \t]*(?:@prefix|prefix)[ \t]+gwsw:[ \t]*<([^>]*)>")


def _dataset_basis_uit_kop(dataset_path: Path) -> str | None:
    """De GWSW-basis uit de `gwsw:`-prefix in de kop van het datasetbestand, of None (#52).

    Een goedkope prefix-scan van de eerste paar KB -- de `@prefix`-regels staan bovenaan --
    zonder het bestand volledig te parsen of te decoderen. Levert de basis alleen op als de
    `gwsw:`-prefix binnen het totaal-patroon valt (via `namen.basis_uit_prefixen`); een bron
    zonder herkenbare `gwsw:`-prefix geeft None, en dan valt `cachesleutel` terug op alle
    gebundelde bundels. Een leesfout hier is geen fout maar dezelfde terugval -- de eigenlijke
    `BestandError` volgt straks uit `_bestandshash` op hetzelfde ontbrekende bestand.
    """
    try:
        with Path(dataset_path).open("rb") as bestand:
            kop = bestand.read(_KOP_BYTES)
    except OSError:
        return None
    match = _GWSW_PREFIX_PATROON.search(kop)
    if match is None:
        return None
    return namen_module.basis_uit_prefixen({"gwsw": match.group(1).decode("ascii", "replace")})


def _te_hashen_ontologiepaden(ontology_paths: list[Path] | None, dataset_path: Path) -> list[Path]:
    """De ontologiebestanden die in de sleutel gehasht worden.

    Bij een opgegeven lijst: precies die (via `ontologiepaden`). Bij `None`: de gebundelde
    ontologie op de versie die een goedkope prefix-scan van de dataset detecteert -- dezelfde
    bundel die `load_dataset._gebundelde_paden_voor_basis` dan kiest (issue #52), zodat een
    toekomstige 1.8-bundel een 1.6-cache niet meer invalideert. Levert de prefix-scan geen
    gebundelde versie op (geen `gwsw:`-prefix, of een niet-gebundelde versie), dan valt de
    sleutel terug op álle gebundelde bundels -- de veilige kant.
    """
    if ontology_paths is not None:
        return ontologiepaden(ontology_paths)
    basis = _dataset_basis_uit_kop(dataset_path)
    if basis is not None:
        versie = namen_module.versie_van_basis(basis)
        if versie in GEBUNDELDE_VERSIES:
            return [gebundelde_ontologie_voor(versie)]
    return [gebundelde_ontologie_voor(versie) for versie in GEBUNDELDE_VERSIES]


def _bestandshash(pad: Path) -> str:
    """De sha256 van een bestand, in blokken gelezen.

    Komt het bestand niet door het besturingssysteem (het bestaat niet, de rechten
    ontbreken, een leesfout), dan gooit dit een `BestandError` met precies dezelfde tekst
    als `bestand._parse` (issue #48, deel c). `cachesleutel` -- en dus `laad_met_cache` --
    berekent de hash vóór de eigenlijke lezing; zonder deze vertaling gooide een ontbrekend
    bestand mét `gebruik_cache=True` een rauwe `OSError` (`FileNotFoundError`), terwijl
    dezelfde aanroep zónder cache al langs `load_dataset` een `BestandError` gaf. Nu is het
    contract gelijk, ongeacht `gebruik_cache`. `BestandError` is een `DatasetError` en geen
    `OSError`-subtype -- de door de auteur goedgekeurde fouttype-verschuiving (CHANGELOG).
    """
    haas = sha256()
    try:
        with pad.open("rb") as bestand:
            for blok in iter(lambda: bestand.read(1 << 20), b""):
                haas.update(blok)
    except OSError as error:
        raise BestandError(f"{pad}: bestand kan niet gelezen worden ({error}).") from error
    return haas.hexdigest()


def standaard_cachemap() -> Path:
    """De cachemap volgens de XDG-conventie."""
    basis = os.environ.get("XDG_CACHE_HOME")
    return Path(basis or Path.home() / ".cache") / "gwsw-orox-helpers"


def _cachepad_vertrouwd(pad: Path) -> str | None:
    """Geeft `None` als `pad` te vertrouwen is, anders een korte reden waarom niet.

    De cache leest zijn artefacten met `pickle.load`, en pickle voert bij het laden
    willekeurige code uit (`__reduce__`). De cachemap en haar bestanden zijn daarmee een
    vertrouwensgrens: een pad is onvertrouwd als het niet van de huidige gebruiker is
    (`st_uid != os.getuid()`) of als groep of anderen erin mogen schrijven
    (`st_mode & 0o022`) -- dan kan een ander de bytes hebben neergelegd of vervangen.

    **Alleen POSIX.** Op niet-POSIX (`os.name != "posix"`, bv. Windows) bestaan `st_uid`
    en de POSIX-rechtenbits niet in deze vorm; daar is alles vertrouwd en hoort de cache
    in het gebruikersprofiel te staan (zie de docstring van `laad_met_cache`). Een pad dat
    nog niet bestaat is vertrouwd: het wordt straks vers met 0o700 aangemaakt.
    """
    if os.name != "posix":
        return None
    try:
        status = os.stat(pad)
    except FileNotFoundError:
        return None
    if status.st_uid != os.getuid():
        return f"{pad} is eigendom van uid {status.st_uid}, niet van de huidige gebruiker"
    if status.st_mode & 0o022:
        return f"{pad} is schrijfbaar voor groep of anderen (mode {status.st_mode & 0o777:o})"
    return None


def _maak_cachemap(map_: Path) -> None:
    """Maakt de cachemap privé (0o700) aan en zet die mode deterministisch.

    `mkdir(mode=...)` past de mode alleen toe op de laatste component en alleen bij
    aanmaken; een `os.chmod` erachteraan maakt de mode deterministisch, ook als de map al
    bestond. Die chmod draait alleen op POSIX en alleen als de map van ons is -- op een
    vreemde map zou hij op een `PermissionError` stuklopen, en dat is dan precies de
    situatie die `_cachepad_vertrouwd` eerder al had moeten afvangen (géén schrijven in
    een onvertrouwde map).
    """
    map_.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "posix" and map_.stat().st_uid == os.getuid():
        os.chmod(map_, 0o700)


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

    `ontology_paths` betekent hier hetzelfde als in `load_dataset` (zie `ontologiepaden`).
    Sinds issue #32 wordt het hier **niet** meer vooraf naar de gebundelde 1.6-ontologie
    ingevuld: bij `None` moet `load_dataset` de gebundelde ontologie op de gedetecteerde
    dataset-versie kunnen kiezen, en dat kan alleen als het `None` ook echt ziet. `None`
    reist daarom ongewijzigd door naar de lezing (`load_dataset`) en het herstel
    (`_herlees_graaf`) -- die twee zien zo dezelfde bestanden. De `cachesleutel` vult `None`
    zelf in tot de gebundelde 1.6-bundel voor de hash: de sleutel is per dataset uniek langs
    de bytes van het dataset-bestand (die per versie verschillen), dus dat de hash de
    1.6-bundel noemt waar de lezing de 1.7-bundel kiest, maakt hem niet dubbelzinnig.

    Bij een cachetreffer wordt er niets geparseerd en start er dus geen laadfase:
    een balk die in nul seconden vol schiet zou suggereren dat het inlezen snel was
    in plaats van overgeslagen. De laadfase komt uit `load_dataset` zelf.

    **De cachemap is een vertrouwensgrens** (issue #45). Omdat `pickle.load` bij het laden
    willekeurige code kan uitvoeren, moet de cachemap een privé, niet-gedeelde map zijn.
    Vóór het eerste cachecontact toetst deze functie de map met `_cachepad_vertrouwd`: is
    die van een ander of schrijfbaar voor groep of anderen, dan wordt er niets gelezen en
    niets geschreven en komt de dataset uit het bestand terug (met een `logging.warning`).
    Elk pickle-bestand wordt daarnaast apart getoetst vóór het depicklen. Op niet-POSIX
    (Windows) draait die check niet -- daar hoort de cachemap in het gebruikersprofiel
    (`%LOCALAPPDATA%`), waar alleen de gebruiker bij kan.

    **Procesbreed neveneffect: de cyclische GC ligt stil tijdens de structurenlading**
    (issue #59). Om de `pickle.load` van de structurencache heen legt deze functie de GC
    neer met `bestand._gc_uit` -- net als op de koude leesweg (`load_dataset`) en om
    dezelfde reden: de pickle bouwt veel containers die alleen naar beneden wijzen, dus de
    cyclische GC is er zuivere verspilling. De graafpickle die pas lui van schijf komt,
    doet dat neveneffect op haar beurt (zie `LuieGraaf._geladen`). De oude GC-stand komt in
    `_gc_uit`'s eigen `finally` terug, ook bij een afgebroken lading; een aanroeper die de
    GC zelf al uit had houdt hem uit. Het cacheformaat en het antwoord blijven ongewijzigd,
    alleen de laadtijd zakt.
    """
    begin = time.perf_counter()
    if not gebruik_cache:
        dataset = load_dataset(dataset_path, ontology_paths, fallback_encoding, voortgang=voortgang)
        return dataset, CacheUitslag("bestand", "", time.perf_counter() - begin)

    sleutel = cachesleutel(dataset_path, ontology_paths, fallback_encoding)
    map_ = (cache_dir or standaard_cachemap()) / sleutel
    melding = ""
    onvertrouwde_map = _cachepad_vertrouwd(map_)
    if onvertrouwde_map is not None:
        logger.warning(
            "Cachemap overgeslagen: %s. Niet gelezen en niet geschreven; uit het "
            "bestand ingelezen.",
            onvertrouwde_map,
        )
        dataset = load_dataset(dataset_path, ontology_paths, fallback_encoding, voortgang=voortgang)
        return dataset, CacheUitslag(
            "bestand", sleutel, time.perf_counter() - begin, onvertrouwde_map
        )
    pad_structuren = map_ / BESTAND_STRUCTUREN
    pad_graaf = map_ / BESTAND_GRAAF
    if pad_structuren.exists() and pad_graaf.exists():
        onvertrouwd = _cachepad_vertrouwd(pad_structuren)
        if onvertrouwd is not None:
            # De structurenpickle is van een ander of schrijfbaar voor derden: niet
            # depicklen (pickle voert bij het laden code uit), maar opnieuw inlezen.
            melding = f"De cache in {map_} is onbruikbaar ({onvertrouwd}); opnieuw ingelezen."
        else:
            try:
                with pad_structuren.open("rb") as bestand, bestand_module._gc_uit():
                    velden = pickle.load(bestand)
                # Onder hetzelfde foutbeleid (issue #48): een pickle die wél laadt maar geen
                # bruikbare velden geeft -- een niet-mapping, of verkeerde/ontbrekende sleutels
                # na een bitflip die de pickle structureel heel liet -- is even onbruikbaar
                # als een die `pickle.load` al liet struikelen. De `**velden`-heropbouw van de
                # dataset staat daarom binnen deze `try`; anders zou zo'n pickle een `TypeError`
                # buiten het vangnet gooien (de fuzz vond dat: 7/300 op de structurenpickle).
                gecachet = GwswDataset(graph=GraafIndex(), **velden)
            except _PICKLE_FOUTEN as fout:
                melding = f"De cache in {map_} is onbruikbaar ({fout}); opnieuw ingelezen."
            else:
                # De structurencache is geldig; de graafcache wordt niet hier al
                # gelezen (dat kost tot een minuut) maar pas als een check hem
                # aanraakt. Is die dan beschadigd, dan herstelt LuieGraaf zichzelf
                # via deze functie in plaats van de hele run te laten crashen.
                herstel = partial(_herlees_graaf, dataset_path, ontology_paths, fallback_encoding)
                # `LuieGraaf` is geen GraafIndex-subklasse maar een plaatsvervanger die
                # alles doorgeeft; het veld verwacht een GraafIndex en krijgt hier zijn gedrag.
                # Sinds issue #34 draagt hij het leescontract expliciet en vervult hij
                # `graaf.GraafLezer` structureel, maar dat protocol is niet wat hier gevraagd
                # wordt: `GwswDataset.graph` staat gepind op de concrete `GraafIndex`
                # (`tests/test_publieke_api.py`), en dat veld verbreden naar een protocol is
                # een auteursbeslissing (`CLAUDE.md`, Harde regels; apart geparkeerd). Deze
                # cast blijft dus staan tot die stap gezet is.
                luie = cast(GraafIndex, LuieGraaf(pad_graaf, herstel))
                # `source` (en bij een expliciete ontologieopgave ook `ontologies`) komt uit
                # de pickle van de éérste lezing. De sleutel hasht alleen `pad.name`, dus een
                # gelijknamig, inhoudsgelijk bestand uit een andere map treft dezelfde cache;
                # zonder deze correctie zou `ds.source` naar het pad van die eerste lezing
                # wijzen (issue #48, deel d). We zetten het terug op het gevraagde pad, zoals
                # `load_dataset` op een misser doet.
                dataset = replace(gecachet, graph=luie, source=Path(dataset_path))
                if ontology_paths is not None:
                    dataset = replace(dataset, ontologies=tuple(ontologiepaden(ontology_paths)))
                return dataset, CacheUitslag("cache", sleutel, time.perf_counter() - begin)

    dataset = load_dataset(dataset_path, ontology_paths, fallback_encoding, voortgang=voortgang)
    # De lezing is al geslaagd; kan de cache niet weggeschreven worden (een read-only
    # cachemap, een volle schijf), dan is dat geen fout maar een gemiste versnelling voor de
    # volgende run (issue #48, deel b). Melden en doorgaan i.p.v. de hele run laten crashen
    # ná een geslaagde lezing.
    try:
        _schrijf(map_, dataset)
    except OSError as fout:
        logger.warning(
            "De cache in %s kon niet weggeschreven worden (%s); de volgende run leest opnieuw in.",
            map_,
            fout,
        )
        schrijffout = f"De cache in {map_} kon niet weggeschreven worden ({fout})."
        melding = f"{melding} {schrijffout}".strip() if melding else schrijffout
    return dataset, CacheUitslag("bestand", sleutel, time.perf_counter() - begin, melding)


def _herlees_graaf(
    dataset_path: Path, ontology_paths: list[Path] | None, fallback_encoding: str | None
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


def _reduce_uriref(term: URIRef) -> tuple[Callable[[str], URIRef], tuple[str]]:
    """Pickelt een `URIRef` als `_uriref_snel(str)` in plaats van `URIRef(str)` (issue #63).

    `URIRef.__reduce__` levert `(URIRef, (str,))`, wat bij het teruglezen `URIRef.__new__` met
    zijn IRI-validatieregex draait -- dubbel werk, want pyoxigraph heeft de IRI bij het inlezen
    al gecontroleerd. `_uriref_snel` neemt het `str.__new__`-pad rechtstreeks; pickle noemt de
    functie bij naam, dus het laden kiest haar vanzelf.
    """
    return (_uriref_snel, (str(term),))


def _reduce_bnode(term: BNode) -> tuple[type[BNode], tuple[str]]:
    """Pickelt een `BNode` via zijn gewone constructor -- er is geen snelpad nodig.

    `BNode(str)` doet geen validatie die de moeite van omzeilen waard is; dit reduce houdt de
    `BNode` alleen expliciet in de `dispatch_table` zodat de vier termvormen op één plek staan.
    """
    return (BNode, (str(term),))


def _reduce_literal(
    term: Literal,
) -> tuple[Callable[..., Literal], tuple[Any, ...]]:
    """Pickelt een `Literal` via het passende snelpad in plaats van `Literal(str, lang, dt)`.

    `Literal.__reduce__` levert `(Literal, (str, language, datatype))` en laat de vier interne
    velden bij het teruglezen door `Literal.__new__` herberekenen (`_castLexicalToPython` en de
    well-formed-check). Een kale `xsd:string`-literaal gaat via `_literal_string_snel` (die vier
    velden zijn dan voorspelbaar); elke taal- of getypeerde literaal via `_literal_snel`, dat de
    al berekende Python-`value` en de `ill_typed`-vlag meekrijgt. Beide worden uit de publieke
    eigenschappen van de literaal gehaald, zodat de schrijfweg zelf niet naar rdflib-interne
    velden reikt -- alleen `_literal_snel` doet dat, met zijn eigen bewaker in `tests/test_graaf`.
    """
    if term.language is None and term.datatype is None:
        return (_literal_string_snel, (str(term),))
    return (
        _literal_snel,
        (str(term), term.language, term.datatype, term.value, term.ill_typed),
    )


class _SnellePickler(pickle.Pickler):
    """Een `Pickler` die de rdflib-termen via de snelpaden van `graaf` reduceert (issue #63).

    De `dispatch_table` bepaalt hoe een object van een bepaald type gepickeld wordt; voor de
    drie rdflib-termtypen wijst hij naar de reduce-functies hierboven. De `copyreg`-tabel gaat
    eronder mee, want een eigen `dispatch_table` vervangt (niet: vult aan) de `copyreg`-tabel
    die de standaardpickler zou raadplegen; die tabel is standaard leeg, maar een afnemer of
    bibliotheek die er iets in registreert hoort hier hetzelfde antwoord te krijgen als bij
    de kale pickler. Types die er niet in staan (ook de `datetime`- en `Decimal`-waarden van
    getypeerde literalen) vallen op de gewone `__reduce_ex__`-weg terug, dus de containers
    (`GraafIndex`, de dicts, de tuples) picklen ongewijzigd.
    """

    dispatch_table = {
        **copyreg.dispatch_table,
        URIRef: _reduce_uriref,
        BNode: _reduce_bnode,
        Literal: _reduce_literal,
    }


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

    De pickle loopt via `_SnellePickler` (issue #63): de rdflib-termen worden naar de snelle
    constructors van `graaf` gereduceerd, zodat het teruglezen `URIRef.__new__`/`Literal.__new__`
    en hun validatie overslaat. De handtekening en de atomaire garantie blijven ongewijzigd; het
    is enkel de pickler die wisselt.
    """
    _maak_cachemap(pad.parent)
    beschrijving, tijdelijk_pad = tempfile.mkstemp(
        prefix=f"{pad.name}.{os.getpid()}.", suffix=".tijdelijk", dir=pad.parent
    )
    tijdelijk = Path(tijdelijk_pad)
    try:
        with os.fdopen(beschrijving, "wb") as bestand:
            _SnellePickler(bestand, protocol=5).dump(inhoud)
        tijdelijk.replace(pad)
    except BaseException:
        tijdelijk.unlink(missing_ok=True)
        raise
