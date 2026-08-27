"""Lezen en terugschrijven van GWSW-OroX (TTL) rioleringsdatasets."""

from importlib.metadata import version

from gwsw_orox_helpers.clip import clip_orox, merge_orox
from gwsw_orox_helpers.schrijven import lees_orox, schrijf_orox, schrijf_orox_quads

__version__ = version("gwsw-orox-helpers")

# De leeslaag wordt uit haar eigen modules geimporteerd (`gwsw_orox_helpers.dataset`,
# `...cache`, `...geometry`); dat is het oppervlak dat nlriochecker kent en dat blijft
# zo. De schrijflaag en de cliplaag komen er additief bij en staan hier omdat ze elk uit
# één module bestaan.
__all__ = [
    "__version__",
    "clip_orox",
    "lees_orox",
    "merge_orox",
    "schrijf_orox",
    "schrijf_orox_quads",
]
