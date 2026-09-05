"""De twee ingangen van de cliplaag: `clip_orox` en `merge_orox`.

Hier staat alleen de volgorde waarin de fasen langskomen -- de grenslaag lezen, het plan
maken, per vlak een gefilterde stroom wegschrijven, en de omkering daarvan. Elke stap zelf
woont in zijn eigen submodule; het verhaal eromheen in de docstring van
`gwsw_orox_helpers.clip`.
"""

from __future__ import annotations

import itertools
from pathlib import Path
from typing import TYPE_CHECKING, cast

from gwsw_orox_helpers.clip.bereik import _meld_bereikverschil
from gwsw_orox_helpers.clip.grenzen import _bestandsnaam, _lees_grenzen
from gwsw_orox_helpers.clip.merge import _samengevoegd, _scan_delen
from gwsw_orox_helpers.clip.plan import _maak_plan
from gwsw_orox_helpers.clip.stroom import _deelstroom
from gwsw_orox_helpers.clip.termen import (
    KNIP,
    KNIP_PREFIX,
    _bronbasis,
    _bronbasis_en_rest,
    _kniptermen,
)
from gwsw_orox_helpers.errors import KnipError
from gwsw_orox_helpers.schrijven import lees_orox, schrijf_orox_quads

if TYPE_CHECKING:
    from collections.abc import Iterable

    import pyoxigraph


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
    geen geheugen voor de triples zelf. Sinds issue #64 rekent elke schrijfpass niet meer
    per quad uit waar hij heen gaat: de analyseronde slaat die kennis één keer plat tot een
    positietabel (per stroompositie een masker-byte en een herschrijf-vlag) die de pass
    alleen nog leest, zodat een quad zonder blanke knoop of geknipte geometrie ongewijzigd
    de deur uit gaat. Met `bereikcontrole=True` komt daar een lezing bij
    die na een klein aantal geometrieen weer wordt losgelaten; zonder de vlag verandert er
    aan het aantal lezingen niets.

    `bron` mag een str- of ander `os.PathLike`-pad zijn en wordt tot `Path` gemaakt (issue
    #55): een bibliotheek hoort een str-pad te accepteren, en hieronder wordt `bron.stem`
    gelezen. De annotatie blijft `Path` -- die is gepind in `tests/test_publieke_api.py`; dit
    is een runtime-verbreding van de geaccepteerde typen, geen contractwijziging.
    """
    bron = Path(bron)
    vlakken = _lees_grenzen(grenzen, sleutel)
    # De basis van de bron één keer detecteren en die éne opening met het plan delen: de
    # basisdetectie verbruikt alleen de kop tot het eerste GWSW-predicaat, en de kop plus de
    # rest gaan via `itertools.chain` als één stroom naar `_maak_plan` (issue #61). Zo wordt
    # de bron voor plan én basis samen één keer geopend in plaats van twee keer. De naam
    # `geopend` mag de deellus hieronder niet overleven -- met een terugvalcodering draagt die
    # half-verbruikte stroom de hele gedecodeerde bron, en die hoort losgelaten te worden
    # zodra het plan hem gelezen heeft, niet pas bij de eerste herbinding in de lus.
    geopend = lees_orox(bron, fallback_encoding)
    basis, verbruikt = _bronbasis_en_rest(geopend.quads, bron)
    termen = _kniptermen(basis)
    if bereikcontrole:
        _meld_bereikverschil(bron, grenzen, vlakken, fallback_encoding, termen.has_value)
    plan = _maak_plan(bron, itertools.chain(verbruikt, geopend.quads), vlakken, termen)
    del geopend, verbruikt

    uitmap = Path(uitmap)
    paden: list[Path] = []
    for index, naam in enumerate(plan.namen):
        doel = uitmap / f"{bron.stem}__{_bestandsnaam(naam)}.ttl"
        geopend = lees_orox(bron, fallback_encoding)
        # De gedetecteerde `gwsw:`-basis expliciet in de deel-kop, zodat een deel
        # zelfbeschrijvend is: draagt de bron geen eigen `gwsw:`-prefix, dan zou de kop
        # anders de 1.6 uit `STANDAARD_PREFIXEN` erven terwijl de triples de bronversie
        # dragen, en `merge_orox` het deel op de verkeerde versie herenigen (issue #32,
        # reviewronde). Voor een bron mét `gwsw:`-prefix is dit dezelfde waarde en dus geen
        # bytewijziging.
        prefixen = {**geopend.prefixen, "gwsw": termen.basis, KNIP_PREFIX: KNIP}
        # `_deelstroom` levert sinds issue #64 een gemengde Quad/Triple-stroom (de snelle tak
        # geeft de bron-Quad ongewijzigd door, het herschrijfpad een Triple). De serializer
        # aanvaardt de mix -- Turtle kent geen benoemde grafen -- maar het uniontype van
        # `schrijf_orox_quads` verwoordt hem homogeen; de cast overbrugt dat zonder de gepinde
        # publieke signatuur te raken.
        deelstroom = cast(
            "Iterable[pyoxigraph.Quad] | Iterable[pyoxigraph.Triple]",
            _deelstroom(geopend.quads, plan, index, termen),
        )
        schrijf_orox_quads(deelstroom, doel, prefixen=prefixen)
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

    `doel` mag een str- of ander `os.PathLike`-pad zijn en wordt door `schrijf_orox_quads`
    tot `Path` gemaakt (issue #55); hier alvast, zodat de coercie zichtbaar bij de ingang
    staat. De annotatie blijft `Path` (gepind in `tests/test_publieke_api.py`).
    """
    doel = Path(doel)
    if not delen:
        raise KnipError("merge_orox: geen delen opgegeven; er valt niets samen te voegen.")

    # Dezelfde IRI-detectie als bij het knippen, zodat de hereniging het geknipte `hasValue`
    # op de bronversie herkent en terugschrijft (issue #32, reviewronde). Over álle delen
    # geketend en niet alleen het eerste: een degeneratief deel kan enkel de ontologiekop
    # dragen (geen enkel GWSW-predicaat), en dan zou detectie op dat ene deel ten onrechte op
    # 1.6 terugvallen en waarschuwen. De keten stopt bij het eerste GWSW-predicaat, dus in de
    # praktijk komt hij niet verder dan het eerste niet-lege deel.
    quads = itertools.chain.from_iterable(lees_orox(pad).quads for pad in delen)
    termen = _kniptermen(_bronbasis(quads, delen[0]))
    scan = _scan_delen(delen, termen)
    schrijf_orox_quads(_samengevoegd(delen, scan), doel, prefixen=scan.prefixen)
