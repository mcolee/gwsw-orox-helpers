"""Tests voor de datasetcache.

De cache mag nooit een ander antwoord geven dan opnieuw inlezen. Het gevaarlijkste
geval is een cache die achterloopt op de lader; daarom zit de broncode van de lader
in de sleutel.
"""

from __future__ import annotations

from pathlib import Path

from gwsw_orox_helpers.bronnen import gebundelde_ontologie
from gwsw_orox_helpers.cache import BESTAND_GRAAF, cachesleutel, laad_met_cache
from gwsw_orox_helpers.dataset import load_dataset

TTL_DIR = Path(__file__).parent / "fixtures" / "ttl"
VOORBEELD = TTL_DIR / "schoon.ttl"


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


def test_de_sleutel_verandert_mee_met_de_broncode_van_de_lader(tmp_path: Path, monkeypatch) -> None:
    """De broncode van de lader hoort net zo goed bij de sleutel als de invoer zelf.

    `test_de_sleutel_verandert_mee_met_de_lader` verzet alleen `LADER_VERSIE`; dat
    bewijst niet dat de broncode-hash van de ladermodules zelf ook echt meetelt --
    een refactor die dat deel van `cachesleutel` laat vallen, zou die test nog
    steeds groen laten. Hier wordt in plaats daarvan `dataset_module.__file__`
    naar een gewijzigde kopie verzet, zoals de bron die `cachesleutel` inleest.
    """
    import gwsw_orox_helpers.cache as cache_module

    origineel = Path(cache_module.dataset_module.__file__)
    kopie = tmp_path / origineel.name
    kopie.write_bytes(origineel.read_bytes() + b"\n# gewijzigd voor de test\n")

    eerste = cachesleutel(VOORBEELD, [])
    monkeypatch.setattr(cache_module.dataset_module, "__file__", str(kopie))

    assert cachesleutel(VOORBEELD, []) != eerste


def test_de_sleutel_verandert_mee_met_de_broncode_van_de_ontologielezer(
    tmp_path: Path, monkeypatch
) -> None:
    """`load_dataset` leidt `kenmerk_property` af met `ontologie.verwachte_property`.

    Die waarde wordt in de structurencache bewaard, dus de broncode van `ontologie.py`
    hoort net als die van de lader bij de sleutel -- anders zou een wijziging aan de
    afleiding een stille, verouderde `kenmerk_property` blijven serveren (ATTR-014).
    """
    import gwsw_orox_helpers.cache as cache_module

    origineel = Path(cache_module.ontologie_module.__file__)
    kopie = tmp_path / origineel.name
    kopie.write_bytes(origineel.read_bytes() + b"\n# gewijzigd voor de test\n")

    eerste = cachesleutel(VOORBEELD, [])
    monkeypatch.setattr(cache_module.ontologie_module, "__file__", str(kopie))

    assert cachesleutel(VOORBEELD, []) != eerste


def test_de_sleutel_verandert_mee_met_de_broncode_van_de_graafindex(
    tmp_path: Path, monkeypatch
) -> None:
    """`graaf.py` draagt de termconversie en de volgordegarantie van de gecachete graaf.

    De graafpickle is een `GraafIndex`; wijzigt de indexmodule, dan is de gepicklede
    graaf van een andere lader en hoort de sleutel te veranderen -- anders serveert de
    cache stil een index met de oude volgorde- of conversieregels.
    """
    import gwsw_orox_helpers.cache as cache_module

    origineel = Path(cache_module.graaf_module.__file__)
    kopie = tmp_path / origineel.name
    kopie.write_bytes(origineel.read_bytes() + b"\n# gewijzigd voor de test\n")

    eerste = cachesleutel(VOORBEELD, [])
    monkeypatch.setattr(cache_module.graaf_module, "__file__", str(kopie))

    assert cachesleutel(VOORBEELD, []) != eerste


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
