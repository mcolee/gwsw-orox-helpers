"""Samenvoegen: de delen weer tot de bron.

Twee rondes over de delen. `_scan_delen` verzamelt de knipstukken en wijst aan wat in meer
dan een deel kan staan; `_samengevoegd` levert daarna de triples ontdubbeld, ontknipt en
zonder knipmerken. Waarom de blanke knopen hier hun naam uit de delen houden en niet
opnieuw genummerd worden, staat in de docstring van `gwsw_orox_helpers.clip`.

Sinds issue #65 rekent de tweede ronde de per-quad-kennis van de eerste niet meer opnieuw
uit, net als de schrijfronde van de clip dat sinds issue #64 niet meer doet. `_scan_delen`
slaat tijdens haar ene lezing per deel een **positietabel** plat: per stroompositie één byte
-- `0` doorgeven (de bron-quad gaat ongewijzigd naar de serializer), `1` knipmerk overslaan,
`2` herschrijven-ontdubbelen (het herstel- en ontdubbelpad). `_samengevoegd` leest die tabel
per positie en doet alleen op byte `2` nog de herleiding (herkomst-substitutie, ontdubbeling,
het aaneen naaien van de stukken). Een byte `0`-quad -- verreweg de meeste -- gaat als de
bron-`Quad` de deur uit: dat is byte-gelijk aan de gelijke `Triple`, want Turtle kent geen
benoemde grafen. Zo levert de ronde een gemengde Quad/Triple-stroom en blijft
`merge(clip(bron))` graaf-gelijk aan de bron. De tabel is O(1) byte per quad per deel; de
delen komen niet als geheel in het geheugen.
"""

from __future__ import annotations

from array import array
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pyoxigraph

from gwsw_orox_helpers.clip.termen import (
    _GML_TYPE,
    KNIP,
    KNIP_PREFIX,
    _gml_waarde,
    _Kniptermen,
    _kniptermen,
    _term,
)
from gwsw_orox_helpers.errors import KnipError
from gwsw_orox_helpers.geometry import (
    GeometryError,
    coordinaattokens,
    parse_gml,
    tokens_per_punt,
    vervang_coordinaten,
)
from gwsw_orox_helpers.namen import GWSW
from gwsw_orox_helpers.schrijven import lees_orox


@dataclass
class _Scan:
    """Wat de eerste ronde over de delen oplevert: de stukken en wat ontdubbeld moet worden."""

    prefixen: dict[str, str] = field(default_factory=dict)
    # De GWSW-predicaten van de bron (issue #32), afgeleid uit de prefixen van het eerste
    # deel. Default 1.6; `_scan_delen` zet hem naar de basis die de delen dragen, zodat het
    # herstelde geometrie-triple met hetzelfde `hasValue` wordt weggeschreven als de bron.
    termen: _Kniptermen = field(default_factory=lambda: _kniptermen(GWSW))
    # Sleutel van een stukknoop -> de herkomst waar hij bij hoort.
    herkomst_van: dict[str, str] = field(default_factory=dict)
    # Herkomst -> volgnummer -> (coordinatentekst, ingevoegd_einde).
    stukken: dict[str, dict[int, tuple[str, bool]]] = field(default_factory=dict)
    # Herkomst -> de GML-literaal van het eerste stuk; die levert het omhulsel.
    sjabloon: dict[str, str] = field(default_factory=dict)
    aantallen: dict[str, set[int]] = field(default_factory=dict)
    # Subjecten waarvan de triples in meer dan een deel kunnen staan.
    ontdubbelen: set[str] = field(default_factory=set)
    # De positietabel per deel (issue #65): één `array('B')` per deel, in de volgorde van
    # `delen`, met per stroompositie `0` doorgeven / `1` knipmerk overslaan / `2`
    # herschrijven-ontdubbelen. `_scan_delen` slaat hem als laatste stap plat (`_bouw_posities`)
    # wanneer `herkomst_van` en `ontdubbelen` niet meer veranderen; `_samengevoegd` leest hem.
    posities: list[array[int]] = field(default_factory=list)


def _scan_delen(delen: Sequence[Path], termen: _Kniptermen) -> _Scan:
    """Eerste ronde over de delen: knipstukken verzamelen en dubbele subjecten aanwijzen.

    De sleutel van een term is hier zijn IRI, of `_:<naam>` voor een blanke knoop. Anders
    dan bij het knippen worden die blanke knopen *niet* hernummerd: de clip heeft ze een
    vaste naam gegeven en die naam is precies de identiteit die de delen delen. De twee
    takken staan uitgeschreven en niet in een hulpfunctie per term: deze lus draait per quad
    van elk deel, op de delen van De Wolden en Hoogeveen bijna vier miljoen keer per deel.

    Sinds issue #65 slaat deze ronde als laatste stap (`_bouw_posities`) een positietabel per
    deel plat, zodat `_samengevoegd` de herleiding niet per quad hoeft over te doen; zie de
    moduledocstring. `termen` is de bron-termenset die `merge_orox` uit de delen detecteert
    (`_bronbasis`: prefix, IRI-scan, 1.6 met melding); daaruit volgt tegen welk `hasValue` de
    knipgeometrie vergeleken en teruggeschreven wordt (issue #32).
    """
    scan = _Scan(termen=termen)
    gezien: set[str] = set()
    merken: dict[str, dict[str, str]] = {}
    verwijzers: dict[str, set[str]] = {}
    named_node = pyoxigraph.NamedNode
    blank_node = pyoxigraph.BlankNode
    literal = pyoxigraph.Literal
    has_value = scan.termen.has_value

    # De per-positie-kennis voor de positietabel (issue #65), net als `clip.plan._maak_plan`:
    # elke term-sleutel krijgt een int-id (interning), en per stroompositie bewaren we het
    # subject-id, het object-id (-1 voor een literaal of een niet-benoemd object) en of de quad
    # een knip:-predicaat draagt. `array('i')` is ~4 B per kolom, geen quads; ná de scan slaat
    # `_bouw_posities` dat per deel plat tot één byte per positie en worden deze int-tabellen
    # losgelaten. De delen komen zo nooit als geheel in het geheugen.
    sleutel_id: dict[str, int] = {}
    sleutels: list[str] = []

    def _id(sleutel: str) -> int:
        gevonden = sleutel_id.get(sleutel)
        if gevonden is None:
            gevonden = sleutel_id[sleutel] = len(sleutels)
            sleutels.append(sleutel)
        return gevonden

    deel_kennis: list[tuple[array[int], array[int], bytearray]] = []

    for index, pad in enumerate(delen):
        geopend = lees_orox(pad)
        if index == 0:
            scan.prefixen = {
                naam: iri for naam, iri in geopend.prefixen.items() if naam != KNIP_PREFIX
            }
        hier: set[str] = set()
        subj_ids = array("i")
        obj_ids = array("i")
        knip = bytearray()
        for quad in geopend.quads:
            subject_in = quad.subject
            if isinstance(subject_in, named_node):
                onderwerp = subject_in.value
            else:
                assert isinstance(subject_in, blank_node)  # een subject is nooit een literaal
                onderwerp = f"_:{subject_in.value}"
            hier.add(onderwerp)
            subj_ids.append(_id(onderwerp))
            predicaat = quad.predicate.value
            object_in = quad.object
            is_knip = predicaat.startswith(KNIP)
            if is_knip and isinstance(object_in, literal):
                merken.setdefault(onderwerp, {})[predicaat] = object_in.value
            elif predicaat == has_value and "__knip" in onderwerp:
                # 9c (issue #65): het GML-sjabloon alleen bewaren voor een stukknoop
                # (`<origineel>__knip<k>`). `_verwerk_merken` en `_hersteld` lezen de sjabloon
                # alleen voor stukknopen en hun herkomsten; de sjabloon van een gewoon
                # geometrie-subject werd nooit gelezen. Dit scheelt een `_gml_waarde`-aanroep
                # (en de dict-groei) op elk niet-geknipt hasValue-subject.
                gml = _gml_waarde(object_in)
                if gml is not None:
                    scan.sjabloon.setdefault(onderwerp, gml)
            voorwerp: str | None
            if isinstance(object_in, named_node):
                voorwerp = object_in.value
            elif isinstance(object_in, blank_node):
                voorwerp = f"_:{object_in.value}"
            else:
                voorwerp = None
            if voorwerp is None:
                obj_ids.append(-1)
            else:
                obj_ids.append(_id(voorwerp))
                if "__knip" in voorwerp:
                    verwijzers.setdefault(voorwerp, set()).add(onderwerp)
            knip.append(1 if is_knip else 0)
        deel_kennis.append((subj_ids, obj_ids, knip))
        for sleutel in hier:
            if sleutel in gezien:
                scan.ontdubbelen.add(sleutel)
            gezien.add(sleutel)

    _verwerk_merken(scan, merken)

    # Een triple die naar een stukknoop wees, wijst na het herschrijven naar de herkomst;
    # zulke triples staan dan in elk deel dat een stuk draagt en moeten ontdubbeld worden.
    scan.ontdubbelen |= set(scan.stukken)
    for stukknoop in scan.herkomst_van:
        scan.ontdubbelen |= verwijzers.get(stukknoop, set())

    _bouw_posities(scan, sleutels, deel_kennis)
    return scan


def _bouw_posities(
    scan: _Scan,
    sleutels: list[str],
    deel_kennis: list[tuple[array[int], array[int], bytearray]],
) -> None:
    """Slaat de per-positie-kennis van de scanronde plat tot de positietabel (issue #65).

    Per stroompositie wordt één byte bewaard: `1` voor een knip:-predicaat (overslaan), `2`
    zodra het huidige pad (`_samengevoegd`, byte `2`) iets zou herschrijven of ontdubbelen --
    het subject is een stukknoop, het object is een stukknoop, of het subject moet ontdubbeld
    worden -- en anders `0`, waarbij `_samengevoegd` de bron-quad ongewijzigd doorgeeft.

    De keuze is per *term* (stukknoop-zijn, ontdubbel-zijn) één keer opgezocht
    (`stukknoop_per_id`, `ontdubbel_per_id`) en dan per positie geïndexeerd, zodat het
    platslaan over de posities niets meer opzoekt. Byte `0` is veilig omdat het huidige pad
    voor zo'n positie exact `triple(subject_in, predicaat, object_in)` levert, en dat is
    byte-gelijk aan de bron-`Quad` in de default-graaf; over-markeren als `2` is nooit fout,
    onder-markeren (byte `0` waar het pad wél herschrijft) wel -- vandaar de drie voorwaarden.
    """
    herkomst_van = scan.herkomst_van
    ontdubbelen = scan.ontdubbelen
    stukknoop_per_id = [sleutel in herkomst_van for sleutel in sleutels]
    ontdubbel_per_id = [sleutel in ontdubbelen for sleutel in sleutels]
    for subj_ids, obj_ids, knip in deel_kennis:
        tabel = array("B", bytes(len(subj_ids)))
        for positie in range(len(subj_ids)):
            if knip[positie]:
                tabel[positie] = 1
                continue
            onder = subj_ids[positie]
            if stukknoop_per_id[onder]:
                tabel[positie] = 2
                continue
            voor = obj_ids[positie]
            if voor != -1 and stukknoop_per_id[voor]:
                tabel[positie] = 2
                continue
            if ontdubbel_per_id[onder]:
                tabel[positie] = 2
        scan.posities.append(tabel)


def _verwerk_merken(scan: _Scan, merken: dict[str, dict[str, str]]) -> None:
    """Vertaalt de knipmerken naar de stukkenadministratie en controleert of ze compleet is."""
    for knoop, merk in merken.items():
        herkomst = merk.get(f"{KNIP}herkomst")
        if herkomst is None:
            continue
        try:
            volgnummer = int(merk[f"{KNIP}volgnummer"])
            aantal = int(merk[f"{KNIP}aantal"])
        except (KeyError, ValueError) as fout:
            raise KnipError(
                f"knipmerk op {knoop!r} is onvolledig of onleesbaar ({fout}); zonder volgnummer "
                f"en aantal is de geknipte geometrie niet terug te leggen."
            ) from fout
        tekst = scan.sjabloon.get(knoop)
        if tekst is None:
            raise KnipError(
                f"knipstuk {knoop!r} draagt geen GML-geometrie; er valt niets aaneen te naaien."
            )
        scan.herkomst_van[knoop] = herkomst
        scan.aantallen.setdefault(herkomst, set()).add(aantal)
        rij = scan.stukken.setdefault(herkomst, {})
        # De getallen van het stuk blijven de brontekst; alleen de scheiders gaan hier al
        # op een enkele spatie, want `_hersteld` splitst deze tekst toch weer op witruimte.
        rij[volgnummer] = (
            " ".join(coordinaattokens(tekst)),
            merk.get(f"{KNIP}ingevoegdEinde") == "true",
        )
        scan.sjabloon.setdefault(herkomst, tekst)

    for herkomst, rij in scan.stukken.items():
        aantallen = scan.aantallen[herkomst]
        if len(aantallen) != 1:
            raise KnipError(
                f"de stukken van {herkomst!r} noemen verschillende aantallen {sorted(aantallen)}; "
                f"dat zijn stukken uit verschillende knipbeurten."
            )
        aantal = next(iter(aantallen))
        if sorted(rij) != list(range(aantal)):
            ontbreekt = sorted(set(range(aantal)) - set(rij))
            raise KnipError(
                f"van {herkomst!r} ontbreken de stukken {ontbreekt}; de delen zijn niet compleet "
                f"en de geometrie zou korter terugkomen dan ze was."
            )


def _samengevoegd(
    delen: Sequence[Path], scan: _Scan
) -> Iterator[pyoxigraph.Quad | pyoxigraph.Triple]:
    """De triples van alle delen samen: ontdubbeld, ontknipt en zonder knipmerken.

    Sinds issue #65 leest deze ronde de positietabel van de scanronde (`scan.posities`, één
    `array('B')` per deel) per stroompositie in plaats van per quad opnieuw uit te rekenen wat
    er moet gebeuren. Bij byte `0` gaat de bron-`Quad` ongewijzigd de deur uit -- geen nieuwe
    `Triple`, geen sleutel-herleiding, geen opzoeking; dat mag omdat Turtle geen benoemde
    grafen kent, dus een default-graaf-`Quad` schrijft byte-gelijk aan de gelijke `Triple`. Bij
    byte `1` (een knip:-merk) wordt de quad overgeslagen. Alleen byte `2` loopt het oude pad:
    herkomst-substitutie, ontdubbeling en het aaneen naaien van de stukken. De sleutels worden
    daar op dezelfde manier gelezen als in `_scan_delen`, en om dezelfde reden uitgeschreven.

    De positie-index loopt per deel gelijk met de scanronde: pyoxigraph levert de quads van een
    bestand in documentvolgorde, dus positie `i` hier is positie `i` daar (dezelfde aanname als
    `clip.stroom._deelstroom` sinds issue #64).
    """
    gezien: set[tuple[str, str, str]] = set()
    geschreven: set[str] = set()
    # Vaste tabellen en typen als lokale naam; alles hieronder draait per quad van elk deel.
    herkomst_van = scan.herkomst_van
    ontdubbelen = scan.ontdubbelen
    has_value = scan.termen.has_value
    named_node = pyoxigraph.NamedNode
    blank_node = pyoxigraph.BlankNode
    triple = pyoxigraph.Triple
    for deel_index, pad in enumerate(delen):
        posities = scan.posities[deel_index]
        for positie, quad in enumerate(lees_orox(pad).quads):
            byte = posities[positie]
            if byte == 0:
                # Verreweg de meeste quads: geen knipmerk, geen stukknoop, geen ontdubbeling.
                # De bron-quad gaat ongewijzigd door (byte-gelijk aan de gelijke Triple).
                yield quad
                continue
            if byte == 1:
                # Een knip:-merk; `merge_orox` gooit elke triple uit die naamruimte weg.
                continue

            # --- Byte 2: het herschrijf- en ontdubbelpad (het oude `merge.py:199-228`).
            predicaat = quad.predicate.value
            subject_in = quad.subject
            if isinstance(subject_in, named_node):
                onderwerp = subject_in.value
            else:
                assert isinstance(subject_in, blank_node)  # een subject is nooit een literaal
                onderwerp = f"_:{subject_in.value}"
            herkomst = herkomst_van.get(onderwerp)
            subject: pyoxigraph.NamedNode | pyoxigraph.BlankNode
            if herkomst is not None:
                if predicaat == has_value and _gml_waarde(quad.object) is not None:
                    if herkomst not in geschreven:
                        geschreven.add(herkomst)
                        yield _hersteld(herkomst, scan)
                    continue
                subject = _term(herkomst)
            else:
                # De term staat er al: `_term(onderwerp)` zou hem letterlijk opnieuw
                # opbouwen uit de tekst die er zojuist uit kwam.
                subject = subject_in

            object_in = quad.object
            if isinstance(object_in, named_node):
                doel = herkomst_van.get(object_in.value)
            elif isinstance(object_in, blank_node):
                doel = herkomst_van.get(f"_:{object_in.value}")
            else:
                doel = None
            object_ = _term(doel) if doel is not None else object_in

            sleutel = herkomst if herkomst is not None else onderwerp
            if sleutel in ontdubbelen:
                merk = (sleutel, predicaat, _objectsleutel(object_))
                if merk in gezien:
                    continue
                gezien.add(merk)
            yield triple(subject, quad.predicate, object_)


def _objectsleutel(term: object) -> str:
    """Een tekstvorm van een object die twee gelijke objecten gelijk maakt."""
    if isinstance(term, pyoxigraph.Literal):
        return "|".join(("L", term.datatype.value, term.language or "", term.value))
    if isinstance(term, pyoxigraph.BlankNode):
        return f"B{term.value}"
    return f"N{getattr(term, 'value', term)}"


def _hersteld(herkomst: str, scan: _Scan) -> pyoxigraph.Triple:
    """De oorspronkelijke geometrie: de stukken aaneen, het ingevoegde knippunt eruit."""
    sjabloon = scan.sjabloon[herkomst]
    stap = _stapgrootte(sjabloon)
    rij = scan.stukken[herkomst]
    tokens: list[str] = []
    for volgnummer in sorted(rij):
        tekst, ingevoegd_einde = rij[volgnummer]
        punten = tekst.split()
        # Van elk stuk na het eerste vervalt het eerste punt (dat herhaalt het laatste punt
        # van het vorige stuk) en van elk stuk dat op een ingevoegd knippunt eindigt het
        # laatste. Wat overblijft is letterlijk de tokenreeks van de bron.
        if volgnummer > 0:
            punten = punten[stap:]
        if ingevoegd_einde:
            punten = punten[: max(len(punten) - stap, 0)]
        tokens.extend(punten)
    literal = vervang_coordinaten(sjabloon, " ".join(tokens))
    return pyoxigraph.Triple(
        _term(herkomst),
        scan.termen.has_value_knoop,
        pyoxigraph.Literal(literal, datatype=_GML_TYPE),
    )


def _stapgrootte(sjabloon: str) -> int:
    """Het aantal getallen per punt, op dezelfde manier bepaald als bij het knippen.

    Niet uit de `srsDimension` gelezen maar uit de verhouding tussen het aantal tokens en
    het aantal punten dat `parse_gml` erin ziet -- `geometry.tokens_per_punt`, dezelfde
    functie die `_knip_lijn` de stukken mee verdeelde. Zou de literaal geen srsDimension
    dragen, dan tellen beide kanten en komen ze op hetzelfde uit, en blijft het aaneen
    naaien sluitend.

    Komt die verhouding niet rond, dan is er niets te raden: het aaneen naaien snoeit per
    punt van de tokenreeks, dus een stap van 2 waar de bron er 3 bedoelde levert een
    geometrie op die niemand ooit geschreven heeft -- en dat stilzwijgend. Een stuk dat de
    clip zelf schreef komt hier nooit; wat hier komt is een deel van elders.

    Het puntental komt hier vandaan en niet uit `tokens_per_punt` zelf: een vlak (dat geen
    `.coords` heeft) en een onleesbare literaal horen hier geen fout uit shapely te geven
    maar de melding hieronder, met de getallen erin waarmee de auteur ziet waarom.
    """
    try:
        punten = len(parse_gml(sjabloon).coords)
    except (GeometryError, NotImplementedError):
        punten = 0
    stap = tokens_per_punt(sjabloon, punten)
    if stap is not None:
        return stap
    raise KnipError(
        f"uit {sjabloon!r} is niet af te lezen hoeveel getallen er op een punt gaan "
        f"({len(coordinaattokens(sjabloon))} coordinaatwaarden op {punten} punten); het "
        f"aaneen naaien van de stukken zou dan op de verkeerde plaats snoeien."
    )
