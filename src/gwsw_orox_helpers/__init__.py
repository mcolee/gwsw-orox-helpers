"""Lezen en terugschrijven van GWSW-OroX (TTL) rioleringsdatasets."""

from importlib.metadata import version

from gwsw_orox_helpers.schrijven import lees_orox, schrijf_orox, schrijf_orox_quads

__version__ = version("gwsw-orox-helpers")

# De leeslaag wordt uit haar eigen modules geimporteerd (`gwsw_orox_helpers.dataset`,
# `...cache`, `...geometry`); dat is het oppervlak dat nlriochecker kent en dat blijft
# zo. De schrijflaag komt er additief bij en staat hier omdat ze uit één module bestaat.
__all__ = ["__version__", "lees_orox", "schrijf_orox", "schrijf_orox_quads"]
