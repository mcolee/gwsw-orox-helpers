"""Toegang tot de meegeleverde GWSW-ontologie en vocabulaire-index.

De ontologie reist met de package mee in plaats van bij de afnemer te liggen: zonder
klassenhierarchie herkent de lader knopen en strengen niet aan hun GWSW-type en valt
hij terug op geometrie (zie `GwswDataset.klassenhierarchie_bekend`). Een afnemer die
niets opgeeft hoort dus de goede ontologie te krijgen, niet geen.

De GWSW-ontologie is CC0 (https://stichtingrioned.github.io/GWSW_Ontologie_RDF/), dus
aan het meeleveren staat niets in de weg. Welke versie er ligt, staat in `CLAUDE.md`;
upgraden is handwerk van de auteur.

Deze module importeert niets uit `dataset`, zodat `dataset` haar wel kan importeren.
"""

from importlib.resources import files
from pathlib import Path


def gebundelde_ontologie() -> Path:
    """Pad naar de meegeleverde GWSW-ontologie (deelmodel Totaal)."""
    return Path(str(files("gwsw_orox_helpers").joinpath("data/Ontologie_GWSW_Totaal.ttl")))


def vocabulaire_index_pad() -> Path:
    """Pad naar de meegeleverde vocabulaire-index (JSON)."""
    return Path(str(files("gwsw_orox_helpers").joinpath("data/gwsw-vocabulaire-index.json")))
