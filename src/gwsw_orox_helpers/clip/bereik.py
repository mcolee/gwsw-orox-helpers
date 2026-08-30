"""De bereikcontrole: liggen de grenslaag en de bron in hetzelfde getallenbereik?

Een fase die naast de andere staat in plaats van ertussen: de knip vraagt hem niets en zijn
uitkomst verandert geen enkele toewijzing. Hij kent `grenzen` (voor `_Vlak`), `termen` (dat
een GML-literaal herkent, net als `plan` en `merge` dat er laten doen), de GML-lezers uit
`geometry`, de IRI's uit `namen` en `schrijven.lees_orox`.

`clip_orox` neemt aan dat de grenslaag in EPSG:28992 staat, net als de GML-literalen van de
bron, en valideert dat niet (zie zijn docstring). Staat de grenslaag in een ander stelsel --
WGS84-graden is de gewone vergissing -- dan valt geen enkel punt van de bron in een vlak en
schuift `knip._vlak_van` ze allemaal naar hetzelfde dichtstbijzijnde vlak. Er komt dan een
deel uit dat de hele bron draagt en N-1 delen met alleen de ontologiekop, en de hereniging
klopt nog steeds: de clip heeft geen enkele reden om te klagen. Dat is de gemeenste
gebruikersfout van de clip, want er is geen fout te zien.

Deze module is die reden, en alleen op verzoek: `clip_orox(..., bereikcontrole=True)` legt de
omhullende van de grenslaag naast die van de bron en schrijft een `logging`-waarschuwing als
ze niet bij elkaar kunnen horen. Een **waarschuwing en geen fout**, om twee redenen. De
terugval op het dichtstbijzijnde vlak is een *belofte* en geen vergissing -- een grenslaag
dekt zelden precies alles wat een export bevat -- dus een bereik dat niet past is een sterk
vermoeden en geen bewijs; een heuristiek hoort geen knip af te breken. En weigeren wat
vandaag geknipt wordt, verandert het gedrag van de bevroren `clip_orox`; dat is een
auteursbeslissing (`CLAUDE.md`, Harde regels) en niet wat issue #28 vroeg.

De waarschuwing gaat langs `logging` en niet langs `warnings`: de afnemer van deze package
is een controleprogramma dat zijn eigen logging al inricht, en `cache` meldt een onbruikbare
cache op dezelfde manier. Een `warnings.warn` zou daarnaast per plek maar één keer klinken.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Final

from gwsw_orox_helpers.clip.grenzen import _Vlak
from gwsw_orox_helpers.clip.termen import _gml_waarde
from gwsw_orox_helpers.geometry import GeometryError, parse_gml
from gwsw_orox_helpers.namen import HAS_VALUE
from gwsw_orox_helpers.schrijven import lees_orox

logger = logging.getLogger(__name__)

# Een omhullende als (minx, miny, maxx, maxy) -- de volgorde van shapely's `bounds`.
_Bereik = tuple[float, float, float, float]

# Hoeveel GML-literalen er hoogstens bekeken worden om het bereik van de bron te schatten.
# Een omhullende hoeft niet exact te zijn om een stelselverschil te zien: dat scheelt ordes
# van grootte en geen procenten. De klem houdt de controle bij een *prefix* van de parse in
# plaats van een tweede volledige lezing -- op de export van De Wolden en Hoogeveen (112 MB,
# cp850) gepaard gemeten 0,8 s tegen 9,8 s, en de geschatte omhullende is daar
# x 229158..236186 waar de volledige x 211074..238947 geeft. Dat scheelt tientallen
# procenten en niets aan het oordeel, want een ander stelsel scheelt ordes. Een bron met
# minder literalen wordt wel helemaal gelezen -- die is dan ook klein (Juinen: 7 ms).
_MONSTERGROOTTE: Final = 1000

# Vanaf welke factor tussen de coordinaatgroottes van de twee omhullenden er "ordes uiteen"
# staat. RD-meters liggen rond 2e5 en graden onder 1e2, dus daar is de factor duizenden.
_ORDEGRENS: Final = 1000.0


def _meld_bereikverschil(
    bron: Path, grenzen: Path, vlakken: tuple[_Vlak, ...], fallback_encoding: str | None
) -> None:
    """Waarschuwt als de grenslaag en de geometrie van de bron niet bij elkaar kunnen horen.

    Zwijgt als de bron geen enkele leesbare geometrie draagt: dan valt er niets naast te
    leggen en zou elke uitspraak erover verzonnen zijn.
    """
    bronbereik = _bereik_van_bron(bron, fallback_encoding)
    if bronbereik is None:
        return
    grensbereik = _bereik_van_vlakken(vlakken)
    redenen = _redenen(grensbereik, bronbereik)
    if not redenen:
        return
    logger.warning(
        "%s: de grenslaag en de geometrie van %s liggen niet in hetzelfde bereik (%s). "
        "Grenslaag: %s. Bron: %s. De clip neemt voor allebei EPSG:28992 aan en rekent niet "
        "om. Staan ze inderdaad in verschillende stelsels -- WGS84-graden tegen RD-meters is "
        "de gewone vergissing -- dan valt elk object via de terugval op het dichtstbijzijnde "
        "vlak in hetzelfde deel en is de verdeling onbruikbaar. Klopt het stelsel wel, dan "
        "dekt deze grenslaag deze bron eenvoudigweg niet.",
        grenzen,
        bron,
        " en ".join(redenen),
        _toon(grensbereik),
        _toon(bronbereik),
    )


def _bereik_van_vlakken(vlakken: tuple[_Vlak, ...]) -> _Bereik:
    """De omhullende van alle vlakken samen.

    `_lees_grenzen` levert er minstens een en geen ervan is leeg, dus er valt hier altijd
    wat te omvatten.
    """
    gevonden: _Bereik | None = None
    for vlak in vlakken:
        gevonden = _omvat(gevonden, vlak.meetkunde.bounds)
    assert gevonden is not None  # `_lees_grenzen` levert minstens een vlak
    return gevonden


def _bereik_van_bron(
    bron: Path, fallback_encoding: str | None, monstergrootte: int = _MONSTERGROOTTE
) -> _Bereik | None:
    """De omhullende van de eerste `monstergrootte` GML-literalen; `None` als die er niet zijn.

    Een onleesbare literaal telt wel mee voor de klem maar niet voor de omhullende: hij
    zegt niets over het bereik, en de leeslaag meldt hem al in `geometry_errors`.

    De quadstroom wordt bij de klem losgelaten in plaats van uitgeput; wat pyoxigraph
    eronder open heeft, gaat met de laatste verwijzing ernaar dicht.
    """
    gevonden: _Bereik | None = None
    gezien = 0
    for quad in lees_orox(bron, fallback_encoding).quads:
        if quad.predicate.value != HAS_VALUE:
            continue
        gml = _gml_waarde(quad.object)
        if gml is None:
            continue
        gezien += 1
        try:
            meetkunde = parse_gml(gml)
        except GeometryError:
            meetkunde = None
        if meetkunde is not None and not meetkunde.is_empty:
            gevonden = _omvat(gevonden, meetkunde.bounds)
        if gezien >= monstergrootte:
            break
    return gevonden


def _omvat(bereik: _Bereik | None, rand: _Bereik) -> _Bereik:
    """De omhullende die `bereik` en `rand` allebei omvat."""
    if bereik is None:
        return (rand[0], rand[1], rand[2], rand[3])
    return (
        min(bereik[0], rand[0]),
        min(bereik[1], rand[1]),
        max(bereik[2], rand[2]),
        max(bereik[3], rand[3]),
    )


def _redenen(grensbereik: _Bereik, bronbereik: _Bereik) -> tuple[str, ...]:
    """Waarom deze twee omhullenden niet bij elkaar kunnen horen; leeg als ze passen."""
    redenen: list[str] = []
    if _disjunct(grensbereik, bronbereik):
        redenen.append("ze overlappen elkaar niet")
    factor = _schaalverschil(grensbereik, bronbereik)
    if factor >= _ORDEGRENS:
        redenen.append(f"hun coordinaten schelen een factor {factor:.0f}")
    return tuple(redenen)


def _disjunct(een: _Bereik, twee: _Bereik) -> bool:
    """Of deze twee omhullenden elkaar nergens raken."""
    return een[2] < twee[0] or twee[2] < een[0] or een[3] < twee[1] or twee[3] < een[1]


def _schaalverschil(een: _Bereik, twee: _Bereik) -> float:
    """De factor tussen de grootste coordinaat van de een en die van de ander.

    Op de coordinaten zelf en niet op de *span* van de omhullenden: een grenslaag van een
    enkele straat uit een provinciebrede export scheelt drie ordes in span terwijl ze in
    dezelfde getallen staan, en die mag hier niet als stelselverschil gelden. De grootte van
    de coordinaten is wel wat een ander stelsel verzet -- graden onder 1e2 tegen RD-meters
    rond 2e5.
    """
    groot, klein = sorted((_grootte(een), _grootte(twee)), reverse=True)
    if klein > 0.0:
        return groot / klein
    return math.inf if groot > 0.0 else 1.0


def _grootte(bereik: _Bereik) -> float:
    """De grootste absolute coordinaat in deze omhullende."""
    return max(abs(waarde) for waarde in bereik)


def _toon(bereik: _Bereik) -> str:
    """Een omhullende als leesbare tekst, zodat de melding tot de eigen invoer te herleiden is."""
    return f"x {bereik[0]:g}..{bereik[2]:g}, y {bereik[1]:g}..{bereik[3]:g}"
