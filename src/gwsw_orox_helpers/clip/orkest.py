"""De twee ingangen van de cliplaag: `clip_orox` en `merge_orox`.

Hier staat alleen de volgorde waarin de fasen langskomen -- de grenslaag lezen, het plan
maken, per vlak een gefilterde stroom wegschrijven, en de omkering daarvan. Elke stap zelf
woont in zijn eigen submodule; het verhaal eromheen in de docstring van
`gwsw_orox_helpers.clip`.
"""

from __future__ import annotations

import logging
from pathlib import Path

from gwsw_orox_helpers import namen
from gwsw_orox_helpers.clip.bereik import _meld_bereikverschil
from gwsw_orox_helpers.clip.grenzen import _bestandsnaam, _lees_grenzen
from gwsw_orox_helpers.clip.merge import _samengevoegd, _scan_delen
from gwsw_orox_helpers.clip.plan import _maak_plan
from gwsw_orox_helpers.clip.stroom import _deelstroom
from gwsw_orox_helpers.clip.termen import KNIP, KNIP_PREFIX, _kniptermen
from gwsw_orox_helpers.errors import KnipError
from gwsw_orox_helpers.schrijven import lees_orox, schrijf_orox_quads

_logger = logging.getLogger(__name__)


def _bronbasis(bron: Path, fallback_encoding: str | None) -> str:
    """De GWSW-basis van de bron (issue #32): prefix, IRI-scan, of 1.6 met melding.

    Dezelfde volgorde als de leeslaag (`bestand._parse`): de `gwsw:`-prefix van de bron is
    de goedkope eerste weg, de predicaat-IRI's zijn de terugval voor een export zonder die
    declaratie, en zonder herkenbare versie valt de clip terug op 1.6 -- met een melding,
    zodat een 1.7-bron niet stil op de 1.6-predicaten geknipt wordt (dan zou de geometrie
    niet gezaaid worden en zou alles naar elk vlak gaan).
    """
    geopend = lees_orox(bron, fallback_encoding)
    basis = namen.basis_uit_prefixen(geopend.prefixen)
    if basis is None:
        basis = next(
            (b for quad in geopend.quads if (b := namen.basis_uit_iri(quad.predicate.value))),
            None,
        )
    if basis is None:
        _logger.warning(
            "%s: geen herkenbare GWSW-versie in de prefixen of de IRI's; de clip valt terug "
            "op de 1.6-predicaten. Een bron op een andere versie wordt daarmee mogelijk niet "
            "correct geknipt.",
            bron,
        )
        return namen.GWSW
    return basis


def clip_orox(
    bron: Path,
    grenzen: Path,
    uitmap: Path,
    *,
    sleutel: str,
    fallback_encoding: str | None = None,
    bereikcontrole: bool = False,
) -> list[Path]:
    """Knipt de OroX-export `bron` langs `grenzen` in een bestand per vlak.

    `grenzen` is een GeoJSON-FeatureCollection met N vlakken in EPSG:28992 -- hetzelfde
    stelsel als de GML-literalen in de bron, die het impliciet laten (RD, geen srsName
    dat er iets anders van maakt). Dat wordt aangenomen en niet gevalideerd. `sleutel`
    is de property waaruit de bestandsnaam volgt (`gemeentenaam`, `gemeentecode`, ...);
    de waarden moeten onderling verschillen, anders zouden twee vlakken hetzelfde
    bestand willen schrijven.

    Levert de N geschreven paden op, in de volgorde van de vlakken in `grenzen`. Elk
    bestand is een geldige OroX-TTL met de prefixen van de bron plus `knip:` voor de
    knipmerken; samen dragen ze elke triple van de bron minstens een keer, zodat
    `merge_orox` de bron weer oplevert.

    `fallback_encoding` betekent hetzelfde als in `load_dataset` en `schrijf_orox`: de
    BrutIS-export van De Wolden en Hoogeveen is geen zuivere UTF-8 en is zonder
    terugval niet te lezen. De uitvoer is hoe dan ook UTF-8.

    `bereikcontrole` staat standaard **uit** en verandert aangezet niets aan de uitvoer:
    de geschreven delen zijn byte voor byte dezelfde. Aan legt hij de omhullende van de
    grenslaag naast die van de bron en schrijft hij een `logging`-waarschuwing als de twee
    niet bij elkaar kunnen horen -- een grenslaag in WGS84-graden tegen een bron in
    RD-meters is de gewone vergissing, en zonder deze controle schuift de terugval op het
    dichtstbijzijnde vlak (`knip._vlak_van`) dan stilzwijgend elk object naar hetzelfde
    deel. Zie `clip.bereik` voor wat er precies vergeleken wordt en waarom het een
    waarschuwing is en geen weigering.

    De bron wordt N+1 keer gelezen: een keer om te bepalen wat waarheen gaat, en daarna
    een keer per vlak om te schrijven. Dat is bewust: de toewijzing is pas rond als de
    hele graaf gezien is, en de delen daarna uit een gefilterde stroom schrijven kost
    geen geheugen voor de triples zelf. Met `bereikcontrole=True` komt daar een lezing bij
    die na een klein aantal geometrieen weer wordt losgelaten; zonder de vlag verandert er
    aan het aantal lezingen niets.
    """
    vlakken = _lees_grenzen(grenzen, sleutel)
    # De basis van de bron één keer detecteren en als termenset doorgeven, zodat de
    # analyseronde en de schrijfronde tegen dezelfde (versie-juiste) predicaten vergelijken.
    termen = _kniptermen(_bronbasis(bron, fallback_encoding))
    if bereikcontrole:
        _meld_bereikverschil(bron, grenzen, vlakken, fallback_encoding, termen.has_value)
    plan = _maak_plan(bron, vlakken, fallback_encoding, termen)

    uitmap = Path(uitmap)
    paden: list[Path] = []
    for index, naam in enumerate(plan.namen):
        doel = uitmap / f"{bron.stem}__{_bestandsnaam(naam)}.ttl"
        geopend = lees_orox(bron, fallback_encoding)
        prefixen = {**geopend.prefixen, KNIP_PREFIX: KNIP}
        schrijf_orox_quads(_deelstroom(geopend.quads, plan, index, termen), doel, prefixen=prefixen)
        paden.append(doel)
    return paden


def merge_orox(delen: list[Path], doel: Path) -> None:
    """Voegt de delen van `clip_orox` weer samen tot een OroX-TTL op `doel`.

    Drie dingen tegelijk: de vereniging van de triples met ontdubbeling op inhoud (een
    blok dat in meer dan een deel staat, staat er in elk deel volledig in en hoort er
    hier een keer uit te komen), het aaneen naaien van de geknipte lijnstukken per
    herkomst, en het weggooien van de knipmerken. Wat eruit komt is de bron: dezelfde
    triples, dezelfde literalen, dezelfde blanke-knoopstructuur.

    De delen moeten samen compleet zijn -- van elke geknipte lijn moeten alle stukken
    er zijn. Ontbreekt er een, dan is de lijn niet te herstellen en volgt een
    `KnipError` in plaats van een stilzwijgend kortere geometrie.
    """
    if not delen:
        raise KnipError("merge_orox: geen delen opgegeven; er valt niets samen te voegen.")

    scan = _scan_delen(delen)
    schrijf_orox_quads(_samengevoegd(delen, scan), doel, prefixen=scan.prefixen)
