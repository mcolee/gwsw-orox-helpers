"""Toegang tot de meegeleverde GWSW-ontologie en vocabulaire-index.

De ontologie reist met de package mee in plaats van bij de afnemer te liggen: zonder
klassenhierarchie herkent de lader knopen en strengen niet aan hun GWSW-type en valt
hij terug op geometrie (zie `GwswDataset.klassenhierarchie_bekend`). Een afnemer die
niets opgeeft hoort dus de goede ontologie te krijgen, niet geen.

Er reizen **twee** gebundelde versies mee, 1.6 en 1.7. `gebundelde_ontologie()` en
`vocabulaire_index_pad()` leveren de **1.6**-bestanden: 1.6 is de default en de leidende
versie. De versiedetectie die 1.7 kiest wanneer de bron dat vraagt, zit sinds deel c van
issue #32 in de leeslaag: `bestand._parse` leidt de basis uit de bron af en zet die op
`GraafIndex.gwsw_basis`, en `load_dataset` kiest daarmee zonder opgegeven ontologie de
gebundelde versie die bij de gedetecteerde basis hoort (met 1.6 als terugval plus een
`logging.warning` bij een onbekende of niet-gebundelde versie). Wie zelf een specifieke
versie wil, gebruikt `gebundelde_ontologie_voor(versie)` / `vocabulaire_index_pad_voor(versie)`;
een onbekende versie geeft daar een kale `ValueError` (`_bekende_versie`), buiten de
`DatasetError`-familie -- zie de docstring van `gwsw_orox_helpers.errors`, "Buiten de hiërarchie".

De GWSW-ontologie is CC0 (https://stichtingrioned.github.io/GWSW_Ontologie_RDF/), dus
aan het meeleveren van beide staat niets in de weg. Welke versies er liggen, staat in
`CLAUDE.md`; upgraden is handwerk van de auteur.

Deze module importeert niets uit `dataset`, zodat `dataset` haar wel kan importeren.
"""

from importlib.resources import files
from pathlib import Path
from typing import Final

GEBUNDELDE_VERSIES: Final = ("1.6", "1.7")
STANDAARD_VERSIE: Final = "1.6"

_ONTOLOGIE_BESTANDEN: Final = {
    "1.6": "data/gwsw_ontologie_totaal_16.ttl",
    "1.7": "data/gwsw_ontologie_totaal_17.ttl",
}
_INDEX_BESTANDEN: Final = {
    "1.6": "data/gwsw-vocabulaire-index-16.json",
    "1.7": "data/gwsw-vocabulaire-index-17.json",
}
# De gebundelde GraafIndex-pickle per versie en het sidecar met zijn versheidshash (issue
# #70). Naast de vocabulaire-index reist per bundel een gepickelde `GraafIndex` mee, zodat de
# lader de 63.614-tripel-ontologie niet elke `load_dataset` opnieuw hoeft te parsen. De
# `.sha256` ernaast draagt de hash over de bundel-TTL + `graaf.py` + de rdflib-versie op het
# moment van genereren; de lader (`laden._gebundelde_graafindex`) laadt de pickle alleen bij
# een treffer op die hash en valt anders terug op de parse. Beide worden door
# `scripts/maak_gwsw_index.py` geschreven en door `test_gwsw_index.py` aan de TTL gebonden.
_GRAAFINDEX_BESTANDEN: Final = {
    "1.6": "data/gwsw-graafindex-16.pickle",
    "1.7": "data/gwsw-graafindex-17.pickle",
}
_GRAAFINDEX_HASH_BESTANDEN: Final = {
    "1.6": "data/gwsw-graafindex-16.sha256",
    "1.7": "data/gwsw-graafindex-17.sha256",
}


def _resource_pad(relatief: str) -> Path:
    return Path(str(files("gwsw_orox_helpers").joinpath(relatief)))


def _bekende_versie(versie: str) -> str:
    if versie not in GEBUNDELDE_VERSIES:
        raise ValueError(
            f"onbekende GWSW-versie {versie!r}; bekend zijn {', '.join(GEBUNDELDE_VERSIES)}"
        )
    return versie


def gebundelde_ontologie() -> Path:
    """Pad naar de meegeleverde GWSW-ontologie (deelmodel Totaal, versie 1.6)."""
    return gebundelde_ontologie_voor(STANDAARD_VERSIE)


def vocabulaire_index_pad() -> Path:
    """Pad naar de meegeleverde vocabulaire-index (JSON, versie 1.6)."""
    return vocabulaire_index_pad_voor(STANDAARD_VERSIE)


def gebundelde_ontologie_voor(versie: str) -> Path:
    """Pad naar de meegeleverde GWSW-ontologie van een gebundelde versie.

    `versie` is een van `GEBUNDELDE_VERSIES`; een onbekende versie geeft `ValueError`.
    """
    return _resource_pad(_ONTOLOGIE_BESTANDEN[_bekende_versie(versie)])


def vocabulaire_index_pad_voor(versie: str) -> Path:
    """Pad naar de meegeleverde vocabulaire-index van een gebundelde versie.

    `versie` is een van `GEBUNDELDE_VERSIES`; een onbekende versie geeft `ValueError`.
    """
    return _resource_pad(_INDEX_BESTANDEN[_bekende_versie(versie)])


def gebundelde_graafindex_pad_voor(versie: str) -> Path:
    """Pad naar de gebundelde GraafIndex-pickle van een gebundelde versie (issue #70).

    `versie` is een van `GEBUNDELDE_VERSIES`; een onbekende versie geeft `ValueError`. Het
    bestand hoeft niet te bestaan: de lader poort er met een hash op vóór hij het laadt en
    valt anders terug op de parse van de TTL ernaast.
    """
    return _resource_pad(_GRAAFINDEX_BESTANDEN[_bekende_versie(versie)])


def gebundelde_graafindex_hash_pad_voor(versie: str) -> Path:
    """Pad naar het sidecar met de versheidshash van de gebundelde GraafIndex-pickle (#70)."""
    return _resource_pad(_GRAAFINDEX_HASH_BESTANDEN[_bekende_versie(versie)])


def versie_van_gebundelde_ontologie(pad: Path) -> str | None:
    """De gebundelde versie waarvan dit precies de meegeleverde ontologie-TTL is, of None.

    Zo weet de lader of een ontologiepad een gebundelde bundel is en dus een GraafIndex-pickle
    ernaast kan hebben. De vergelijking is op padwaarde: `load_dataset` en `lees_ontologie`
    bouwen het pad met `gebundelde_ontologie_voor`, dus het valt samen met wat hier terugkomt.
    Een door de afnemer opgegeven ontologiepad (ook een kopie van de bundel elders) is geen
    gebundelde bundel en geeft None -- dan parseert de lader zoals altijd.
    """
    for versie in GEBUNDELDE_VERSIES:
        if pad == gebundelde_ontologie_voor(versie):
            return versie
    return None
