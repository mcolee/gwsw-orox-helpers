"""Het gezicht van de leeslaag: her-exporteert het domeinmodel, de lader en de vulwaarden.

`dataset` is sinds issue #67 puur een gezicht en niet meer de bak. De inhoud die hier stond
is in drie modules gesneden, elk met een eigen vraag:

- `model` -- het domeinmodel: `GwswDataset` (de vragen die de checks over een ingelezen
  dataset stellen) en `GwswVersie`;
- `laden` -- de lader: `load_dataset`, `lees_ontologie`, `ontologiepaden` en de
  bundelkeuze eromheen;
- `vulwaarden` -- de transformatie: `markeer_vulwaarden`.

Wat eronder ligt is in zes modules verdeeld (`domein`, `bestand`, `inlezen`, `klassen`,
`codering`, `netwerk`); zie `docs/architectuur.md`. **Het oppervlak blijft hier**: elke
naam die een afnemer uit `gwsw_orox_helpers.dataset` importeert, komt hier ook naar buiten
-- de klassen, de IRI-constanten, de graafhulpen, de lader en de vulwaarden -- met dezelfde
handtekening en hetzelfde gedrag (Harde regel in `CLAUDE.md`; `tests/test_publieke_api.py`
is de scheidsrechter). Elke naam is het identieke object (`is`) als in zijn nieuwe module:
`dataset.load_dataset is laden.load_dataset`, `dataset.GwswDataset is model.GwswDataset`,
`dataset.markeer_vulwaarden is vulwaarden.markeer_vulwaarden`.

De importrichting is een lijn en geen cyclus: `model` weet van de lader niets, `laden`
importeert `model`, en `dataset` importeert alle drie. `__all__` hieronder is dezelfde
lijst als voorheen; de dict `WORTELRANDEN` in `tests/test_publieke_api.py` en de
lagentekening in `docs/architectuur.md` spiegelen die snit.
"""

from __future__ import annotations

from gwsw_orox_helpers.laden import lees_ontologie, load_dataset, ontologiepaden
from gwsw_orox_helpers.model import (
    FANTOOM_STAART,
    GWSW,
    HAS_ASPECT,
    HAS_CONNECTION,
    HAS_PART,
    HAS_REFERENCE,
    HAS_VALUE,
    IS_ASPECT_OF,
    IS_PART_OF,
    ISO_DATUM,
    JAARTAL,
    KLASSE_BEGINPUNT,
    KLASSE_BOB_BEGIN,
    KLASSE_BOB_EIND,
    KLASSE_DATUM_INWINNING,
    KLASSE_EINDPUNT,
    KLASSE_INWINNING,
    KLASSE_LIJN,
    KLASSE_MAAIVELDHOOGTE,
    KLASSE_MAAIVELDORIENTATIE,
    KLASSE_PUNT,
    KLASSE_PUTDEKSELNIVEAU,
    KLASSE_WIJZE_VAN_INWINNING,
    KLASSEN_BEGINPUNT,
    KLASSEN_EINDPUNT,
    WORTEL_HULPSTUK,
    WORTEL_HULPSTUKORIENTATIE,
    WORTEL_KNOOPPUNT,
    WORTEL_VERBINDING,
    WORTELS_VOOR_HERKENNING,
    Aspect,
    Conduit,
    DecodeFallback,
    GeometryError,
    GwswDataset,
    GwswVersie,
    Inwinning,
    Koppelingsherstel,
    Leestermen,
    Node,
    Vulwaarde,
    aspect_holders_of,
    aspects_of,
    is_multipart_literal,
    parse_gml,
    parse_gml_z,
    part_holders_of,
    parts_of,
)
from gwsw_orox_helpers.vulwaarden import markeer_vulwaarden

# De lijst is het oppervlak, niet een keuze van deze module: alles wat ooit uit
# `gwsw_orox_helpers.dataset` te importeren was, staat erin -- ook de namen die na de
# hersnit in `geometry` (`parse_gml`, `parse_gml_z`, `is_multipart_literal`,
# `GeometryError`) of in `domein` (`ISO_DATUM`, `JAARTAL`) terechtkwamen. Ze reizen via
# `model`, `laden` of `vulwaarden` mee en zijn hier niets meer dan een doorgeefluik; wie ze
# uit hun eigen module haalt, krijgt hetzelfde object. Bij twijfel over "is dit publiek?"
# blijft de naam staan: hem weghalen breekt een afnemer stil, hem laten staan kost niets.
__all__ = [
    "FANTOOM_STAART",
    "GWSW",
    "HAS_ASPECT",
    "HAS_CONNECTION",
    "HAS_PART",
    "HAS_REFERENCE",
    "HAS_VALUE",
    "ISO_DATUM",
    "IS_ASPECT_OF",
    "IS_PART_OF",
    "JAARTAL",
    "KLASSEN_BEGINPUNT",
    "KLASSEN_EINDPUNT",
    "KLASSE_BEGINPUNT",
    "KLASSE_BOB_BEGIN",
    "KLASSE_BOB_EIND",
    "KLASSE_DATUM_INWINNING",
    "KLASSE_EINDPUNT",
    "KLASSE_INWINNING",
    "KLASSE_LIJN",
    "KLASSE_MAAIVELDHOOGTE",
    "KLASSE_MAAIVELDORIENTATIE",
    "KLASSE_PUNT",
    "KLASSE_PUTDEKSELNIVEAU",
    "KLASSE_WIJZE_VAN_INWINNING",
    "WORTELS_VOOR_HERKENNING",
    "WORTEL_HULPSTUK",
    "WORTEL_HULPSTUKORIENTATIE",
    "WORTEL_KNOOPPUNT",
    "WORTEL_VERBINDING",
    "Aspect",
    "Conduit",
    "DecodeFallback",
    "GeometryError",
    "GwswDataset",
    "GwswVersie",
    "Inwinning",
    "Koppelingsherstel",
    "Leestermen",
    "Node",
    "Vulwaarde",
    "aspect_holders_of",
    "aspects_of",
    "is_multipart_literal",
    "lees_ontologie",
    "load_dataset",
    "markeer_vulwaarden",
    "ontologiepaden",
    "parse_gml",
    "parse_gml_z",
    "part_holders_of",
    "parts_of",
]
