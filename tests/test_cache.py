"""Tests voor de datasetcache.

De cache mag nooit een ander antwoord geven dan opnieuw inlezen. Het gevaarlijkste
geval is een cache die achterloopt op de lader; daarom zit de broncode van de lader
in de sleutel.
"""

from __future__ import annotations

import inspect
import logging
import os
import pickle
import stat
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest
from rdflib import URIRef

from gwsw_orox_helpers import cache as cache_module
from gwsw_orox_helpers.bronnen import gebundelde_ontologie
from gwsw_orox_helpers.cache import (
    BESTAND_GRAAF,
    BESTAND_STRUCTUREN,
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
    "clip.bereik",
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

    Wat elk van de elf bijdraagt staat bij `cache.LADERMODULES`; de gevoeligste zijn
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


def test_de_sleutel_bij_none_hasht_alle_gebundelde_versies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bij `ontology_paths=None` reageert de sleutel op elke gebundelde ontologie (issue #32).

    `load_dataset` kiest bij `None` de gebundelde ontologie op de gedetecteerde
    dataset-versie, dus ook de 1.7-bundel. Zou de sleutel alleen de 1.6-bundel hashen, dan
    invalideert een data-only upgrade van uitsluitend de 1.7-bundel de 1.7-cache niet. Hier
    verzetten we (via een tmp-kopie) de inhoud van de 1.7-bundel en eisen een andere sleutel.
    """
    origineel = cache_module.gebundelde_ontologie_voor
    kopie17 = tmp_path / "bundel17.ttl"
    kopie17.write_text("A", encoding="utf-8")
    monkeypatch.setattr(
        cache_module,
        "gebundelde_ontologie_voor",
        lambda versie: kopie17 if versie == "1.7" else origineel(versie),
    )

    eerste = cachesleutel(VOORBEELD)
    kopie17.write_text("B", encoding="utf-8")
    assert cachesleutel(VOORBEELD) != eerste

    # Een expliciete 1.6-lijst hangt niet van de 1.7-bundel af.
    zonder_17 = cachesleutel(VOORBEELD, [origineel("1.6")])
    kopie17.write_text("C", encoding="utf-8")
    assert cachesleutel(VOORBEELD, [origineel("1.6")]) == zonder_17


# --- De cache als vertrouwensgrens (issue #45) --------------------------------
#
# De cache leest zijn artefacten met `pickle.load`, en pickle voert bij het laden
# willekeurige code uit (`__reduce__`). De cachemap is daarmee een vertrouwensgrens:
# alleen een map die van ons is en die niet voor groep of anderen schrijfbaar is, mag
# gelezen worden. De tests hieronder plegen niet-root; op POSIX omzeilt uid 0 de
# rechtenbits, dus de gevallen die daarop leunen slaan zichzelf dan over.

MAG_RECHTEN_TOETSEN = os.name == "posix" and os.getuid() != 0


def test_de_cachemap_krijgt_mode_0o700(tmp_path: Path) -> None:
    """De aangemaakte cachemap is privé (0o700), niet groep-/wereldleesbaar."""
    if os.name != "posix":
        pytest.skip("de rechten-mode betekent alleen iets op POSIX")
    _, uitslag = laad_met_cache(VOORBEELD, [], cache_dir=tmp_path)
    map_ = tmp_path / uitslag.sleutel
    assert map_.is_dir()
    assert stat.S_IMODE(map_.stat().st_mode) == 0o700


def test_een_groepschrijfbare_cachemap_wordt_overgeslagen(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Een cachemap waar groep of anderen in mogen schrijven, wordt niet vertrouwd:
    niet gelezen én niet geschreven, de dataset komt uit het bestand terug.
    """
    if not MAG_RECHTEN_TOETSEN:
        pytest.skip("root of niet-POSIX omzeilt de rechtenbits")
    sleutel = cachesleutel(VOORBEELD, [])
    map_ = tmp_path / sleutel
    map_.mkdir()
    os.chmod(map_, 0o770)

    with caplog.at_level(logging.WARNING, logger=cache_module.__name__):
        dataset, uitslag = laad_met_cache(VOORBEELD, [], cache_dir=tmp_path)

    assert dataset.nodes
    assert uitslag.bron == "bestand"
    assert list(map_.glob("*.pickle")) == [], "op een onvertrouwde map wordt niets geschreven"
    assert any("schrijfbaar" in bericht for bericht in caplog.messages)


def test_een_cachemap_van_een_vreemde_eigenaar_wordt_overgeslagen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Een cachemap die niet van de huidige gebruiker is, wordt niet vertrouwd.

    We simuleren de vreemde eigenaar door onze `os.getuid` te laten afwijken van de
    werkelijke eigenaar van de (door ons aangemaakte) map.
    """
    if os.name != "posix":
        pytest.skip("de eigenaarcheck betekent alleen iets op POSIX")
    sleutel = cachesleutel(VOORBEELD, [])
    map_ = tmp_path / sleutel
    map_.mkdir(mode=0o700)
    echte_uid = os.getuid()  # vóór de patch vastleggen, anders recurseert de lambda
    monkeypatch.setattr(cache_module.os, "getuid", lambda: echte_uid + 1)

    with caplog.at_level(logging.WARNING, logger=cache_module.__name__):
        dataset, uitslag = laad_met_cache(VOORBEELD, [], cache_dir=tmp_path)

    assert dataset.nodes
    assert uitslag.bron == "bestand"
    assert list(map_.glob("*.pickle")) == []
    assert any("eigendom van uid" in bericht for bericht in caplog.messages)


def test_een_onvertrouwde_structurenpickle_wordt_niet_geladen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Een structurenpickle met groep-/wereldschrijfrechten wordt niet gedepickled.

    We bewijzen het hard: `pickle.load` mag op dit pad niet aangeroepen worden. In
    plaats daarvan wordt opnieuw uit het bestand ingelezen.
    """
    if not MAG_RECHTEN_TOETSEN:
        pytest.skip("root of niet-POSIX omzeilt de rechtenbits")
    laad_met_cache(VOORBEELD, [], cache_dir=tmp_path)
    sleutel = cachesleutel(VOORBEELD, [])
    pad_structuren = tmp_path / sleutel / BESTAND_STRUCTUREN
    assert pad_structuren.exists()
    os.chmod(pad_structuren, 0o666)

    geroepen: list[bool] = []
    echte_load = pickle.load

    def spion(*args: object, **kwargs: object) -> object:
        geroepen.append(True)
        return echte_load(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(cache_module.pickle, "load", spion)

    dataset, uitslag = laad_met_cache(VOORBEELD, [], cache_dir=tmp_path)

    assert dataset.nodes
    assert uitslag.bron == "bestand"
    assert geroepen == [], "een onvertrouwde pickle mag niet gedepickled worden"


def test_op_niet_posix_wordt_de_rechtencheck_overgeslagen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Op Windows (`os.name != 'posix'`) betekenen uid en de bits niets: de check slaat
    over en een map die op POSIX onvertrouwd zou zijn (0o777) geldt daar als vertrouwd.

    We toetsen de twee helpers rechtstreeks en niet de hele `laad_met_cache`, want
    `monkeypatch.setattr(os, "name", "nt")` zet ook `pathlib` op `WindowsPath`: een nieuw
    `Path(...)` (zoals `cachesleutel` er intern maakt) kan de Linux-bronbestanden dan niet
    meer lezen. De helpers krijgen een bestaande `PosixPath` mee en roepen zelf geen
    `Path(...)` aan, dus die draaien wel onder de gefakete `os.name`.
    """
    map_ = tmp_path / "sleutel"
    map_.mkdir()
    map_.chmod(0o777)  # op POSIX onvertrouwd (wereldschrijfbaar)

    monkeypatch.setattr(os, "name", "nt")
    assert cache_module._cachepad_vertrouwd(map_) is None, "op niet-POSIX is alles vertrouwd"

    nieuwe_map = tmp_path / "vers"
    cache_module._maak_cachemap(nieuwe_map)  # mag niet crashen en slaat de chmod over
    assert nieuwe_map.is_dir()


def test_een_geplante_reduce_payload_draait_niet(tmp_path: Path) -> None:
    """De repro uit issue #45: een pickle met een `__reduce__`-payload, geplant met
    0o666, mag zijn payload niet uitvoeren -- het payloadbestand ontstaat niet.
    """
    if not MAG_RECHTEN_TOETSEN:
        pytest.skip("root of niet-POSIX omzeilt de rechtenbits")
    doelwit = tmp_path / "GEPWNED"

    class Aanval:
        def __reduce__(self) -> tuple[Callable[[str], int], tuple[str]]:
            return (os.system, (f"touch {doelwit}",))

    sleutel = cachesleutel(VOORBEELD, [])
    map_ = tmp_path / sleutel
    map_.mkdir()
    with (map_ / BESTAND_STRUCTUREN).open("wb") as fh:
        pickle.dump(Aanval(), fh)
    with (map_ / BESTAND_GRAAF).open("wb") as fh:
        pickle.dump({}, fh)
    os.chmod(map_ / BESTAND_STRUCTUREN, 0o666)
    os.chmod(map_ / BESTAND_GRAAF, 0o666)

    dataset, uitslag = laad_met_cache(VOORBEELD, [], cache_dir=tmp_path)

    assert dataset.nodes
    assert uitslag.bron == "bestand"
    assert not doelwit.exists(), "de payload mag niet gedraaid hebben"


def test_een_onvertrouwde_graafpickle_wordt_hersteld_zonder_terug_te_schrijven(
    tmp_path: Path,
) -> None:
    """De luie graafpickle wordt vóór het depicklen getoetst; onvertrouwd -> herstel.

    En de keerzijde die de docstring van `LuieGraaf._geladen` vastlegt: staat de pickle
    in een onvertrouwde map, dan schrijft het herstel niet terug (dat zou een verse pickle
    in een map leggen waar een ander bij kan). De originele pickle blijft dus ongewijzigd.
    """
    if not MAG_RECHTEN_TOETSEN:
        pytest.skip("root of niet-POSIX omzeilt de rechtenbits")
    map_ = tmp_path / "sleutel"
    map_.mkdir()
    pad_graaf = map_ / BESTAND_GRAAF
    with pad_graaf.open("wb") as fh:
        pickle.dump(load_dataset(VOORBEELD, []).graph, fh)
    os.chmod(pad_graaf, 0o666)
    os.chmod(map_, 0o770)  # de map is onvertrouwd

    hersteld = load_dataset(VOORBEELD, []).graph
    aanroepen: list[bool] = []

    def herstel() -> GraafIndex:
        aanroepen.append(True)
        return hersteld

    luie = LuieGraaf(pad_graaf, herstel)
    assert len(luie) == len(hersteld)  # bevraagt de graaf, dus laadt/hersteltt hem

    assert aanroepen == [True], "de onvertrouwde pickle is niet gedepickled maar hersteld"
    assert stat.S_IMODE(pad_graaf.stat().st_mode) == 0o666, (
        "naar een onvertrouwde map wordt niet teruggeschreven"
    )
