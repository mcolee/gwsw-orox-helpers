"""Tests voor de datasetcache.

De cache mag nooit een ander antwoord geven dan opnieuw inlezen. Het gevaarlijkste
geval is een cache die achterloopt op de lader; daarom zit de broncode van de lader
in de sleutel.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest
from rdflib import URIRef

from gwsw_orox_helpers import cache as cache_module
from gwsw_orox_helpers.bronnen import gebundelde_ontologie
from gwsw_orox_helpers.cache import (
    BESTAND_GRAAF,
    LADERMODULES,
    LuieGraaf,
    cachesleutel,
    laad_met_cache,
)
from gwsw_orox_helpers.dataset import load_dataset
from gwsw_orox_helpers.graaf import GraafIndex
from gwsw_orox_helpers.namen import GWSW, RDF, RDFS

TTL_DIR = Path(__file__).parent / "fixtures" / "ttl"
VOORBEELD = TTL_DIR / "schoon.ttl"

# Termen uit `schoon.ttl`: de minimale klassenhierarchie bovenin en de eerste put.
SUBCLASS_OF = URIRef(RDFS + "subClassOf")
TYPE = URIRef(RDF + "type")
INSPECTIEPUT = URIRef(GWSW + "Inspectieput")
PUT = URIRef(GWSW + "Put")
PUT_A = URIRef("http://example.org/toets#PutA")
ONBEKEND = URIRef("http://example.org/toets#BestaatNiet")

# Het volledige leescontract van `GraafIndex` (zie de moduledocstring van `graaf`) als
# vijf aanroepen, elk op termen die in `schoon.ttl` voorkomen. De drie iteratorlevende
# bewerkingen worden tot een lijst uitgeput, zodat ook de volgordegarantie meevergeleken
# wordt; `__len__` en `__contains__` staan er niet bij omdat
# `test_de_graaf_werkt_ook_uit_de_cache` en het herstelpad die al aanraken.
LEESCONTRACT: dict[str, Callable[[GraafIndex], object]] = {
    "objects": lambda graaf: list(graaf.objects(INSPECTIEPUT, SUBCLASS_OF)),
    "subjects": lambda graaf: list(graaf.subjects(SUBCLASS_OF, PUT)),
    "value": lambda graaf: graaf.value(PUT_A, TYPE),
    "subject_objects": lambda graaf: list(graaf.subject_objects(SUBCLASS_OF)),
    "heeft_subject": lambda graaf: (graaf.heeft_subject(PUT_A), graaf.heeft_subject(ONBEKEND)),
}

# De modules van de package die bewust buiten de cachesleutel blijven, elk met de reden.
# Deze verzameling is de tegenhanger van `cache.LADERMODULES`: samen horen ze precies de
# package te zijn, zodat een nieuwe module niet stilzwijgend ongehasht kan blijven.
BUITEN_DE_SLEUTEL = {
    "__init__",  # alleen re-exports, geen leeslogica
    "bronnen",  # levert paden; de inhoud van die bestanden wordt zelf al gehasht
    "cache",  # de sleutel zelf; `LADER_VERSIE` is hier de knop om aan te draaien
    # Het hele `clip`-package: eigen pad naast de leeslaag, raakt de gecachete lezing niet.
    # Per submodule opgesomd en niet als voorvoegsel afgevangen -- `rglob` ziet elke module
    # in een submap, en een nieuwe fase hoort zich hier net zo goed te melden als een
    # nieuwe module in de wortel.
    "clip.__init__",
    "clip.grenzen",
    "clip.knip",
    "clip.merge",
    "clip.orkest",
    "clip.plan",
    "clip.stroom",
    "clip.termen",
    "errors",  # uitzonderingstypen; er wordt niets van gecachet
    "schrijven",  # idem als clip
    "voortgang",  # meldt alleen voortgang; de lezing verandert er niet van
}


def test_de_cache_geeft_dezelfde_dataset_terug(tmp_path: Path) -> None:
    koud, eerste = laad_met_cache(VOORBEELD, [], cache_dir=tmp_path)
    warm, tweede = laad_met_cache(VOORBEELD, [], cache_dir=tmp_path)

    assert eerste.bron == "bestand"
    assert tweede.bron == "cache"
    assert set(warm.nodes) == set(koud.nodes)
    assert set(warm.conduits) == set(koud.conduits)
    assert warm.subclasses == koud.subclasses
    assert warm.source == koud.source


def test_de_graaf_werkt_ook_uit_de_cache(tmp_path: Path) -> None:
    """De graaf wordt lui geladen; hij moet zich als een graaf blijven gedragen."""
    laad_met_cache(VOORBEELD, [], cache_dir=tmp_path)
    warm, _ = laad_met_cache(VOORBEELD, [], cache_dir=tmp_path)
    vers = load_dataset(VOORBEELD, [])

    assert len(warm.graph) == len(vers.graph)
    uri = next(iter(warm.nodes))
    assert set(warm.subjects_of_class("Put")) == set(vers.subjects_of_class("Put"))
    assert warm.beheerobjecttype(uri) == vers.beheerobjecttype(uri)


def _graafleesregels(caplog: pytest.LogCaptureFixture) -> int:
    """Hoe vaak `LuieGraaf._geladen` de graaf werkelijk van schijf heeft gehaald."""
    return sum("Graaf van schijf gelezen" in bericht for bericht in caplog.messages)


@pytest.mark.parametrize("naam", sorted(LEESCONTRACT))
def test_de_luie_graaf_geeft_per_leesbewerking_hetzelfde_als_een_echte_graafindex(
    naam: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Het leescontract expliciet, en het laadmoment ongewijzigd (issue #34).

    Twee dingen per bewerking, want ze kunnen los stukgaan. Ten eerste het *antwoord*:
    de plaatsvervanger uit de cache hoort exact te geven wat een verse `GraafIndex` op
    dezelfde termen geeft, volgorde inbegrepen. Ten tweede het *moment*: een cachetreffer
    mag de graafpickle (op een gemeentebrede export tientallen seconden en honderden MB)
    niet aanraken, de eerste aanroep wél, en een tweede aanroep niet opnieuw. Dat moment
    is aan de logregel van `_geladen` af te lezen en niet aan een privéveld.

    De naam staat er ook als sleutel bij: sinds issue #34 draagt `LuieGraaf` deze vijf
    methoden *expliciet* en komen ze niet meer uit `__getattr__`. Dat is geen smaak maar
    het verschil tussen mypy die er een term uit ziet komen en mypy die er `object` uit
    ziet komen; het typebewijs staat in `tests/typecheck/graaflezer.py`, en deze regel
    houdt de lijst hier aan die van de klasse gelijk.
    """
    vraag = LEESCONTRACT[naam]
    assert naam in vars(LuieGraaf), "het leescontract hoort expliciet op de klasse te staan"
    # En met exact dezelfde handtekening. `__getattr__` volgde die vanzelf; vijf
    # overgeschreven `def`-regels doen dat niet, en een aanroeper mag ze op naam aanroepen
    # (`graaf.subjects(predicate=..., object_=...)`). Zonder deze regel zou een hernoemde
    # of verschoven parameter op `GraafIndex` hier stil uiteenlopen -- de doorgifte in de
    # body blijft immers werken zolang ze positioneel gebeurt.
    assert inspect.signature(getattr(LuieGraaf, naam)) == inspect.signature(
        getattr(GraafIndex, naam)
    )

    verwacht = vraag(load_dataset(VOORBEELD, []).graph)
    laad_met_cache(VOORBEELD, [], cache_dir=tmp_path)
    with caplog.at_level(logging.INFO, logger=cache_module.__name__):
        warm, uitslag = laad_met_cache(VOORBEELD, [], cache_dir=tmp_path)
        assert uitslag.bron == "cache"
        assert isinstance(warm.graph, LuieGraaf)
        assert _graafleesregels(caplog) == 0, "een cachetreffer mag de graaf niet inlezen"

        assert vraag(warm.graph) == verwacht
        assert _graafleesregels(caplog) == 1, "de eerste aanraking leest hem van schijf"

        assert vraag(warm.graph) == verwacht
        assert _graafleesregels(caplog) == 1, "en een tweede aanraking leest niet opnieuw"


def test_de_sleutel_verandert_mee_met_de_lader(tmp_path: Path, monkeypatch) -> None:
    eerste = cachesleutel(VOORBEELD, [])
    monkeypatch.setattr("gwsw_orox_helpers.cache.LADER_VERSIE", "gewijzigd")

    assert cachesleutel(VOORBEELD, []) != eerste


def test_de_sleutel_verandert_mee_met_de_inhoud_van_de_dataset(tmp_path: Path) -> None:
    """De inhoudshash is de kern van de cachegarantie; monkeypatchen van
    `LADER_VERSIE` alleen bewijst niet dat de bestandshash zelf ook echt meetelt.
    """
    kopie = tmp_path / "dataset.ttl"
    kopie.write_bytes(VOORBEELD.read_bytes())
    eerste = cachesleutel(kopie, [])

    inhoud = bytearray(kopie.read_bytes())
    inhoud[0] ^= 0xFF
    kopie.write_bytes(bytes(inhoud))

    assert cachesleutel(kopie, []) != eerste


def test_de_sleutel_verandert_mee_met_de_inhoud_van_de_ontologie(tmp_path: Path) -> None:
    ontologie = gebundelde_ontologie()
    kopie = tmp_path / "ontologie.ttl"
    kopie.write_bytes(ontologie.read_bytes())
    eerste = cachesleutel(VOORBEELD, [kopie])

    inhoud = bytearray(kopie.read_bytes())
    inhoud[0] ^= 0xFF
    kopie.write_bytes(bytes(inhoud))

    assert cachesleutel(VOORBEELD, [kopie]) != eerste


def test_de_sleutel_verandert_mee_met_de_terugvalcodering() -> None:
    """Zonder dit zou de cache op een dag dat de codering doorgegeven wordt een met
    de verkeerde codering ingelezen dataset kunnen teruggeven.
    """
    assert cachesleutel(VOORBEELD, [], fallback_encoding="cp850") != cachesleutel(
        VOORBEELD, [], fallback_encoding="latin-1"
    )


@pytest.mark.parametrize(
    "module", LADERMODULES, ids=lambda module: module.__name__.rsplit(".", 1)[-1]
)
def test_de_sleutel_verandert_mee_met_de_broncode_van_elke_ladermodule(
    module: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """De broncode van de lader hoort net zo goed bij de sleutel als de invoer zelf.

    `test_de_sleutel_verandert_mee_met_de_lader` verzet alleen `LADER_VERSIE`; dat
    bewijst niet dat de broncode-hash van de ladermodules zelf ook echt meetelt -- een
    refactor die dat deel van `cachesleutel` laat vallen, zou die test nog steeds groen
    laten. Hier wordt in plaats daarvan het `__file__` van de module naar een gewijzigde
    kopie verzet, zoals de bron die `cachesleutel` inleest.

    De lus loopt over `cache.LADERMODULES` zelf en niet over een handmatige greep uit die
    lijst: eerder bewaakten drie losse tests alleen `dataset`, `ontologie` en `graaf`,
    terwijl de vijf andere gehashte modules (`inlezen`, `klassen`, `codering`, `domein`,
    `namen`) ongetoetst bleven. Elke module die aan de lijst wordt toegevoegd, krijgt hier
    dus vanzelf zijn geval erbij; wie een module uit de lijst haalt, verliest een geval en
    struikelt over `test_de_ladermodulelijst_dekt_de_hele_leeslaag`.

    Wat elk van de tien bijdraagt staat bij `cache.LADERMODULES`; de gevoeligste zijn
    `ontologie` (de `kenmerk_property` die `load_dataset` eruit afleidt en die mee gecachet
    wordt, ATTR-014) en `graaf` (de termconversie en volgordegarantie van de gepicklede
    `GraafIndex`).
    """
    origineel = Path(module.__file__ or "")
    kopie = tmp_path / origineel.name
    kopie.write_bytes(origineel.read_bytes() + b"\n# gewijzigd voor de test\n")

    eerste = cachesleutel(VOORBEELD, [])
    monkeypatch.setattr(module, "__file__", str(kopie))

    assert cachesleutel(VOORBEELD, []) != eerste


def test_de_ladermodulelijst_dekt_de_hele_leeslaag() -> None:
    """De lijst bewaakt zichzelf: elke module van de package is gehasht of uitgezonderd.

    De test hierboven toetst wat *in* `LADERMODULES` staat; die lijst kan alleen te kort
    zijn, en een vergeten module levert geen fout op maar een cache die na een wijziging
    aan de lader de oude lezing blijft teruggeven. Daarom staat hier de andere helft: de
    modulebestanden van de package min `BUITEN_DE_SLEUTEL` moeten precies de gehashte
    modules zijn. Een nieuwe module in de leeslaag laat deze test omvallen tot iemand
    hem in `cache.LADERMODULES` zet -- of hem met een reden in `BUITEN_DE_SLEUTEL`
    verantwoordt.
    """
    pakket = Path(cache_module.__file__ or "").parent
    # `rglob`, niet `glob`: ook een module in een toekomstige submap moet zich melden.
    aanwezig = {
        ".".join(pad.relative_to(pakket).with_suffix("").parts)
        for pad in pakket.rglob("*.py")
        if "__pycache__" not in pad.parts
    }
    gehasht = {module.__name__.removeprefix("gwsw_orox_helpers.") for module in LADERMODULES}

    assert gehasht == aanwezig - BUITEN_DE_SLEUTEL
    assert BUITEN_DE_SLEUTEL <= aanwezig  # geen verdwenen module als stille uitzondering


def test_een_beschadigde_cache_leidt_tot_opnieuw_inlezen(tmp_path: Path) -> None:
    laad_met_cache(VOORBEELD, [], cache_dir=tmp_path)
    for bestand in tmp_path.rglob("*.pickle"):
        bestand.write_bytes(b"dit is geen pickle")

    dataset, uitslag = laad_met_cache(VOORBEELD, [], cache_dir=tmp_path)

    assert dataset.nodes
    assert uitslag.bron == "bestand"
    assert "cache" in uitslag.melding.lower()


def test_een_beschadigde_graafcache_herstelt_zichzelf_bij_gebruik(tmp_path: Path) -> None:
    """Alleen de graafcache is corrupt; de structurencache blijft geldig.

    Dat is het gevaarlijke geval: `laad_met_cache` meldt een schone treffer (de
    structurencache is immers prima), en pas een check die `dataset.graph`
    aanraakt -- ADM-007 t/m ADM-009, NET-007, de RVZ-checks -- zou zonder herstel
    een kale `UnpicklingError` krijgen in plaats van een nette terugval. De test
    die beide bestanden bederft, dekt dat pad niet: daar faalt de structurencache
    het eerst en komt de graaf nooit aan bod.
    """
    laad_met_cache(VOORBEELD, [], cache_dir=tmp_path)
    graafbestanden = list(tmp_path.rglob(BESTAND_GRAAF))
    assert graafbestanden, "de graafcache had al moeten bestaan"
    graafbestanden[0].write_bytes(b"dit is geen pickle")

    dataset, uitslag = laad_met_cache(VOORBEELD, [], cache_dir=tmp_path)
    assert uitslag.bron == "cache"  # de structurencache was intact

    vers = load_dataset(VOORBEELD, [])
    assert len(dataset.graph) == len(vers.graph)  # geen crash, en de juiste graaf

    # de graafcache is zelf ook hersteld: een volgende aanraking gaat weer soepel
    dataset_opnieuw, _ = laad_met_cache(VOORBEELD, [], cache_dir=tmp_path)
    assert len(dataset_opnieuw.graph) == len(vers.graph)


def test_laad_met_cache_geeft_de_terugvalcodering_door(tmp_path: Path) -> None:
    """De sleutel die `laad_met_cache` gebruikt, moet dezelfde zijn als
    `cachesleutel` met dezelfde codering zou geven -- anders wordt er met de ene
    codering weggeschreven en met de andere teruggelezen.
    """
    _, uitslag = laad_met_cache(VOORBEELD, [], cache_dir=tmp_path, fallback_encoding="latin-1")

    assert uitslag.sleutel == cachesleutel(VOORBEELD, [], fallback_encoding="latin-1")
    assert uitslag.sleutel != cachesleutel(VOORBEELD, [])


def test_zonder_cache_wordt_er_niets_weggeschreven(tmp_path: Path) -> None:
    laad_met_cache(VOORBEELD, [], cache_dir=tmp_path, gebruik_cache=False)

    assert list(tmp_path.rglob("*.pickle")) == []
