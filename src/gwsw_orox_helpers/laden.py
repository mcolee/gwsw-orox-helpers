"""De lader: van TTL-bestand(en) en ontologie naar een `GwswDataset` (issue #67).

Wie een nieuwe lees-optie in `load_dataset` wil, leest hier ~240 regels lader-orkestratie
en niet meer de hele leeslaag. De vier functies delen één parseerpad: `ontologiepaden`
kiest de bestanden, `_gebundelde_paden_voor_basis` de gebundelde ontologie bij een
gedetecteerde versie, `_stapel_ontologie` stapelt ze in één index, en `lees_ontologie` /
`load_dataset` zijn de twee publieke ingangen -- de eerste levert alleen de
restrictiebron, de tweede het volle domeinmodel.

Deze module importeert `model` (voor `GwswDataset`) en de leeslaag eronder; `model` weet
van de lader niets, zodat de importrichting `dataset -> laden -> model` een lijn blijft.
`dataset` her-exporteert `load_dataset`, `ontologiepaden` en `lees_ontologie` ongewijzigd.
"""

from __future__ import annotations

import logging
import pickle
from collections.abc import Sequence
from hashlib import sha256
from pathlib import Path
from typing import cast

import rdflib

from gwsw_orox_helpers import graaf as graaf_module
from gwsw_orox_helpers.bestand import _gc_uit, _parse
from gwsw_orox_helpers.bronnen import (
    GEBUNDELDE_VERSIES,
    gebundelde_graafindex_hash_pad_voor,
    gebundelde_graafindex_pad_voor,
    gebundelde_ontologie,
    gebundelde_ontologie_voor,
    versie_van_gebundelde_ontologie,
)
from gwsw_orox_helpers.errors import InhoudError
from gwsw_orox_helpers.graaf import GraafIndex
from gwsw_orox_helpers.inlezen import (
    _read_conduits,
    _read_nodes,
    _structural_diff_uit,
)
from gwsw_orox_helpers.klassen import (
    KLASSE_PUTDEKSEL,
    WORTEL_HULPSTUKORIENTATIE,
    WORTEL_KNOOPPUNT,
    WORTEL_VERBINDING,
    _afsluiting,
    _bruikbare_afsluiting,
    _kenmerk_properties,
    _klassefuncties,
    _subclass_closure,
)
from gwsw_orox_helpers.model import GwswDataset
from gwsw_orox_helpers.namen import versie_van_basis
from gwsw_orox_helpers.voortgang import NUL_VOORTGANG, Voortgang

_logger = logging.getLogger(__name__)


def ontologiepaden(ontology_paths: list[Path] | None) -> list[Path]:
    """De ontologiebestanden waarmee gelezen wordt, met `None` als de gebundelde.

    Twee verschillende dingen die makkelijk voor elkaar doorgaan: *niets opgegeven*
    (`None`) betekent de meegeleverde GWSW-ontologie, en een *lege lijst* is de
    expliciete keuze om zonder ontologie te lezen. Dat onderscheid staat hier en
    nergens anders, zodat `load_dataset` en `cache` het niet elk anders kunnen
    invullen.

    De gebundelde ontologie is de standaard omdat de andere kant geen stille keuze
    mag zijn: zonder klassenhierarchie herkent de lader knopen en strengen niet aan
    hun GWSW-type en valt hij terug op geometrie -- zie
    `GwswDataset.klassenhierarchie_bekend`.
    """
    if ontology_paths is None:
        return [gebundelde_ontologie()]
    return [Path(pad) for pad in ontology_paths]


def _gebundelde_paden_voor_basis(basis: str) -> list[Path]:
    """De gebundelde ontologie die bij een gedetecteerde dataset-basis hoort (issue #32).

    `load_dataset` roept dit aan wanneer de afnemer geen ontologie opgaf: dan kiest de lader
    de gebundelde ontologie op de versie die hij uit de dataset detecteerde, zodat een
    1.7-dataset de 1.7-hierarchie krijgt en niet stil op de 1.6-bundel terugvalt. Is de
    gedetecteerde versie niet gebundeld (een 1.8-bron, of een onherkenbare basis), dan valt
    hij terug op de 1.6-bundel -- met een melding, want de termenset volgt dan nog wel de
    gedetecteerde basis en de hierarchie kan niet meer matchen (`klassenhierarchie_bekend`
    meldt dat eerlijk als terugval op geometrie).
    """
    versie = versie_van_basis(basis)
    if versie in GEBUNDELDE_VERSIES:
        return [gebundelde_ontologie_voor(versie)]
    _logger.warning(
        "De dataset draagt GWSW-basis %r, maar daar is geen ontologie voor gebundeld "
        "(gebundeld zijn %s); de lezing valt terug op de 1.6-ontologie. De klassenhierarchie "
        "kan dan niet matchen en het lezen leunt op geometrie.",
        basis,
        ", ".join(GEBUNDELDE_VERSIES),
    )
    return [gebundelde_ontologie()]


def _graafindex_hash(ttl_pad: Path) -> str:
    """De versheidshash van een gebundelde GraafIndex-pickle (issue #70).

    Hasht de bundel-TTL, de broncode van `graaf.py` en de rdflib-versie -- precies de drie
    dingen waarvan de picklevorm en het teruglezen ervan afhangen: de TTL bepaalt de inhoud,
    `graaf.py` de `GraafIndex`-structuur én de snelle term-constructors (`_uriref_snel`,
    `_literal_*`) die het depicklen bij naam aanroept, en de rdflib-versie de interne
    literaalvelden die die constructors zetten. `scripts/maak_gwsw_index.py` schrijft deze
    hash in het sidecar naast de pickle; `_gebundelde_graafindex` vergelijkt hem vóór het
    laden. Verandert een van de drie zonder dat de pickle opnieuw gebouwd wordt, dan klopt de
    hash niet meer en valt de lader terug op de parse -- en `test_gwsw_index.py` wordt rood.

    Dit is dezelfde afhankelijkheid die de cachesleutel al dekt (`cache.cachesleutel` hasht de
    TTL-bytes en, via `LADERMODULES`, de broncode van `graaf` en `laden` plus de rdflib-versie);
    de pickle is een van die TTL afgeleide versnelling en voegt daarom geen sleutel-ingang toe.
    """
    haas = sha256()
    haas.update(ttl_pad.read_bytes())
    haas.update(Path(cast(str, graaf_module.__file__)).read_bytes())
    haas.update(rdflib.__version__.encode("utf-8"))
    return haas.hexdigest()


def _gebundelde_graafindex(pad: Path) -> GraafIndex | None:
    """De gebundelde GraafIndex-pickle voor deze ontologie-TTL, mits vers (issue #70).

    Levert de gepickelde `GraafIndex` alleen op als `pad` precies een gebundelde bundel is én
    de opgeslagen hash bij de huidige TTL + `graaf.py` + rdflib-versie past; anders None, en
    dan parseert `_stapel_ontologie` de TTL zoals altijd. **De hash-poort staat vóór elke
    `pickle.load`**: klopt hij niet, of ontbreekt de pickle of het sidecar, dan wordt er niet
    gedepickeld. Een onleesbare of beschadigde pickle valt breed terug op None (en dus op de
    parse), zodat een kapot meegeleverd bestand de lezing nooit laat crashen.

    De pickle wordt met de package meegeleverd -- hij is dus even vertrouwd als de package-code
    zelf, niet een door de afnemer aangeleverd bestand; de hash-poort is een versheids- en geen
    veiligheidsgrens (die laatste ligt bij de cache, `cache._cachepad_vertrouwd`).

    De GC ligt hier niet apart stil: beide aanroepers (`load_dataset`, `lees_ontologie`) draaien
    `_stapel_ontologie` al binnen `bestand._gc_uit`.
    """
    versie = versie_van_gebundelde_ontologie(pad)
    if versie is None:
        return None
    pickle_pad = gebundelde_graafindex_pad_voor(versie)
    hash_pad = gebundelde_graafindex_hash_pad_voor(versie)
    try:
        opgeslagen = hash_pad.read_text(encoding="ascii").strip()
    except OSError:
        return None
    if not pickle_pad.exists() or opgeslagen != _graafindex_hash(pad):
        return None
    try:
        with pickle_pad.open("rb") as bestand:
            index = pickle.load(bestand)
    except Exception:
        # Een onbruikbare meegeleverde pickle is geen fout maar een gemiste versnelling: val
        # terug op de parse. `pickle.load` kan bij een beschadigd bestand vrijwel elke
        # uitzondering gooien, vandaar de brede vangst (zie `cache._PICKLE_FOUTEN`).
        return None
    return index if isinstance(index, GraafIndex) else None


def _stapel_ontologie(
    paden: Sequence[Path], fallback_encoding: str | None, voortgang: Voortgang
) -> GraafIndex:
    """Parseert de ontologiebestanden op volgorde in één index, met een stap per bestand.

    **Snelpad voor een gebundelde bundel** (issue #70): is er precies één pad en is dat een
    gebundelde ontologie met een verse GraafIndex-pickle ernaast, dan wordt die pickle
    gedepickeld in plaats van de 63.614-tripel-TTL opnieuw te parsen -- dezelfde index, ~0,2 s
    goedkoper. Klopt de hash niet (een gewijzigde `graaf.py`, een andere rdflib-versie, een
    ontbrekende pickle), dan valt deze lus terug op de gewone parse. Meer dan één pad -- of een
    door de afnemer opgegeven ontologiepad dat toevallig een kopie van de bundel is -- gaat
    altijd langs de parse, want stapelen in één bestaande index kan de losse pickle-index niet.

    **Zonder eigen fase, en dat is de hele reden dat deze functie bestaat.** `load_dataset`
    en `lees_ontologie` moeten hetzelfde parseerpad delen -- één plek die weet dat
    meerdere ontologiebestanden in dezelfde `GraafIndex` stapelen -- maar ze melden hun
    voortgang anders: `load_dataset` telt de ontologiebestanden mee in zijn eigen fase
    "TTL laden" (`1 + len(paden)` stappen, met de dataset als eerste), `lees_ontologie`
    opent er zijn eigen fase "Ontologie laden" voor. Zou het delen op het niveau van de
    fase gebeuren, dan zou `load_dataset` er een tweede fase bij krijgen en dus een
    andere voortgang tonen dan voorheen -- en die is bevroren (`CLAUDE.md`, Harde
    regels). Wat hier staat is precies de lus die `load_dataset` altijd al had: per
    bestand een `bestand._parse` in de gedeelde index en daarna een `stap` met de
    bestandsnaam.

    Ook de GC blijft buiten deze functie: allebei de aanroepers zetten hem zelf stil
    (`bestand._gc_uit`), `load_dataset` om zijn hele leesblok en `lees_ontologie` om deze
    lus.
    """
    if len(paden) == 1:
        vers = _gebundelde_graafindex(paden[0])
        if vers is not None:
            voortgang.stap(label=paden[0].name)
            return vers
    ontology = GraafIndex()
    for pad in paden:
        _parse(pad, fallback_encoding, index=ontology)
        voortgang.stap(label=pad.name)
    return ontology


def lees_ontologie(
    paden: list[Path] | None = None,
    terugvalcodering: str | None = None,
    *,
    voortgang: Voortgang = NUL_VOORTGANG,
) -> GraafIndex:
    """Leest de ontologiebestanden in tot de `GraafIndex` waarop de lezers werken.

    Dit is de index die `load_dataset` intern als `restrictiebron` opbouwt en daarna
    weggooit: `GwswDataset.graph` is de *dataset*graaf en `GwswDataset.ontologies` draagt
    alleen de paden. Wie de ontologische lezers van `gwsw_orox_helpers.ontologie` op een
    geladen dataset wil gebruiken -- `facetbereik`, `datatype_van_kenmerk`,
    `kenmerkbereik`, `verwachte_property`, `functie_van_klasse` -- haalt de bron ervoor
    hier op, langs precies dezelfde weg als de lader (issue #33, vervolg op #19).

    De padkeuze is die van `ontologiepaden` en dus dezelfde als bij `load_dataset`:
    `None` betekent de gebundelde GWSW-ontologie, een lege lijst is de expliciete keuze
    om zonder ontologie te lezen (en levert een lege index op), en een opgegeven lijst
    wordt in volgorde in één index gestapeld. De terugvalcodering betekent hetzelfde als
    daar; zie `codering.decodeer`. De parameters heten Nederlands (`paden`,
    `terugvalcodering`) zoals `CLAUDE.md` vraagt, en dus anders dan de bevroren
    `ontology_paths`/`fallback_encoding` van `load_dataset` -- een auteursbeslissing bij
    issue #33; `paden` en niet `ontologiepaden`, omdat dat de naam van de padkeuzefunctie
    hierboven is.

    De voortgang gaat per bestand, in een eigen fase "Ontologie laden" met één stap per
    bestand. Dat is een andere fase dan de "TTL laden" van `load_dataset` -- die telt de
    ontologie bij de dataset in één fase, en dat blijft zo.

    **Ook met een lege lijst is er precies één fase**, dan met totaal nul en zonder
    stappen. Dat is een keuze en geen restje: een aanroeper die de fasen meetelt (een
    balk per fase, een teller in een log) hoort de fase-indeling niet van de *inhoud* van
    zijn argument te zien afhangen -- "soms een fase, soms geen" is het lastigere
    contract om tegenaan te programmeren. `Voortgang.start_fase` neemt `totaal` als
    `int | None` en nul is daar een geldige waarde.

    Hetzelfde neveneffect als bij `load_dataset`, en om dezelfde reden: tijdens het lezen
    ligt de cyclische garbage collector van het hele proces stil en komt hij daarna terug,
    ook na een fout (zie `bestand._gc_uit`).
    """
    ontologie_paden = ontologiepaden(paden)
    voortgang.start_fase("Ontologie laden", len(ontologie_paden))
    with _gc_uit():
        try:
            return _stapel_ontologie(ontologie_paden, terugvalcodering, voortgang)
        finally:
            voortgang.einde_fase()


def load_dataset(
    dataset_path: Path,
    ontology_paths: list[Path] | None = None,
    fallback_encoding: str | None = None,
    *,
    voortgang: Voortgang = NUL_VOORTGANG,
) -> GwswDataset:
    """Leest de OroX-dataset en de ontologie(en) en bouwt het domeinmodel op.

    Zonder `ontology_paths` wordt de gebundelde GWSW-ontologie gelezen; een lege lijst
    betekent expliciet geen ontologie. Zie `ontologiepaden`.

    De voortgang gaat per bestand. rdflib geeft geen tussenstand binnen een bestand,
    en juist het parsen van de dataset is de lange stap; er wordt daarom geen
    percentage getoond dat er niet is.

    Turtle hoort volgens de spec UTF-8 te zijn en zonder `fallback_encoding` wordt niets
    anders geaccepteerd: een bestand dat er niet aan voldoet levert een `DatasetError`.
    Sommige exports (BrutIS) schrijven een handvol bytes in een MS-DOS-codering; de
    afnemer die dat weet, geeft de codering op (`"cp850"` is de gangbare Nederlandse
    variant). Welke dat is, is een keuze van de afnemer en niet van deze package.

    Eén neveneffect om te weten: tijdens de lezing ligt de cyclische garbage collector van
    het hele proces stil en komt hij daarna terug, ook na een fout -- de referentietelling
    blijft aan, dus wat vrijkomt gaat nog altijd meteen weg (zie `bestand._gc_uit`).
    """
    dataset_path = Path(dataset_path)
    expliciet = ontology_paths is not None
    ontologie_paden = ontologiepaden(ontology_paths)
    voortgang.start_fase("TTL laden", 1 + len(ontologie_paden))
    # Om het hele leesblok en niet alleen om het vullen van de index (`bestand._parse`):
    # ook de objectopbouw hieronder maakt miljoenen dicts, tuples en dataclasses aan, en
    # bij elke paar duizend daarvan zou de GC opnieuw door de al gevulde index lopen. Er
    # ontstaat per constructie geen kringetje -- de index, de termen en de waardeobjecten
    # wijzen alleen naar beneden. De binnenste `_gc_uit` in `bestand._parse` blijft staan
    # en is neveneffectvrij: die kijkt naar `gc.isenabled()` en laat deze stand met rust.
    with _gc_uit():
        try:
            graph, fallback = _parse(dataset_path, fallback_encoding)
            voortgang.stap(label=dataset_path.name)

            # Zonder opgegeven ontologie kiest de lader de gebundelde ontologie op de versie
            # die hij zojuist uit de dataset detecteerde (issue #32): de dataset wordt dus
            # éérst geparst, dan de bijpassende ontologie gestapeld. Een expliciet opgegeven
            # `ontology_paths` blijft leidend. Het aantal paden -- en dus de fasetelling
            # hierboven -- verandert niet: `ontologiepaden(None)` en de versiekeuze leveren
            # allebei één gebundeld bestand.
            if not expliciet:
                ontologie_paden = _gebundelde_paden_voor_basis(graph.gwsw_basis)

            # Dezelfde lus als voorheen, nu gedeeld met `lees_ontologie`; hij meldt zijn
            # stappen in de fase die hierboven al loopt en opent er geen eigen (zie
            # `_stapel_ontologie`).
            ontology = _stapel_ontologie(ontologie_paden, fallback_encoding, voortgang)
        finally:
            voortgang.einde_fase()

        # De basis van de dataset (voor het lezen van de graaf) en die van de restrictiebron
        # (voor het lezen van de ontologie) kunnen verschillen wanneer de afnemer expliciet
        # een ontologie van een andere versie opgeeft. De closures die de dataset bevragen
        # gebruiken de datasetbasis; de afgeleiden uit de restrictiebron haar eigen basis.
        data_basis = graph.gwsw_basis
        restrictiebron = ontology if len(ontology) else graph
        onto_basis = restrictiebron.gwsw_basis
        subclasses = _subclass_closure(restrictiebron)
        kenmerk_property = _kenmerk_properties(restrictiebron, subclasses, onto_basis)
        functie_per_klasse = _klassefuncties(restrictiebron, subclasses, onto_basis)
        geometry_errors: dict[str, str] = {}
        # Dezelfde twee vragen die `GwswDataset.klassenhierarchie_bekend` stelt, met
        # dezelfde functie: `None` hier betekent terugval op geometrie, en dat is precies
        # wat het voorbehoud in de uitvoer zegt.
        knooppunt = _bruikbare_afsluiting(subclasses, WORTEL_KNOOPPUNT, data_basis)
        verbinding = _bruikbare_afsluiting(subclasses, WORTEL_VERBINDING, data_basis)
        # De afsluiting, niet de kale klasse: zie `inlezen._deksel_kenmerk`. Zonder
        # klassenkennis blijft het bij Putdeksel zelf, net als bij elke andere `closure()`.
        deksel = _afsluiting(subclasses, KLASSE_PUTDEKSEL, data_basis)
        hulpstuk = _afsluiting(subclasses, WORTEL_HULPSTUKORIENTATIE, data_basis)
        nodes, knoop_houders = _read_nodes(graph, geometry_errors, knooppunt, deksel)
        conduits, herstel, streng_houders = _read_conduits(
            graph, nodes, geometry_errors, verbinding, hulpstuk
        )

    if not nodes and not conduits:
        raise InhoudError(
            f"{dataset_path}: geen knooppunten of strengen aangetroffen. Is dit een "
            f"GWSW-OroX-dataset?"
        )

    dataset = GwswDataset(
        source=dataset_path,
        graph=graph,
        nodes=nodes,
        conduits=conduits,
        subclasses=subclasses,
        geometry_errors=geometry_errors,
        decode_fallback=fallback,
        ontologies=tuple(ontologie_paden),
        kenmerk_property=kenmerk_property,
        functie_per_klasse=functie_per_klasse,
        koppelingsherstel=herstel,
    )
    # Altijd, en juist ook zonder klassenkennis: dan laat het verschil zien dat de
    # ontologische route nul objecten oplevert en de hele lezing op geometrie rust. De
    # houders die `_read_nodes`/`_read_conduits` net bezochten worden hergebruikt (issue
    # #70): bij aanwezige klassenkennis (`knooppunt`/`verbinding` niet None) zijn dat de
    # ontologische houders, anders de structurele. Zo hoeft alleen de andere kant nog
    # gelopen te worden; de uitkomst is byte-gelijk aan `_structural_diff(graph, subclasses)`.
    dataset.structural_diff.update(
        _structural_diff_uit(
            graph,
            subclasses,
            knoop_houders=knoop_houders,
            knoop_ontologisch=knooppunt is not None,
            streng_houders=streng_houders,
            streng_ontologisch=verbinding is not None,
        )
    )
    # Eén waarschuwing wanneer de dataset niet de leidende 1.6-versie is (issue #51): de
    # gepinde module-constanten (`HAS_*`, `KLASSE_*`) spellen 1.6 en treffen op deze graaf
    # stil nul. Wie versie-juist wil bevragen, gebruikt `GwswDataset.termen` of de
    # str-methoden. Precies hier en nergens anders: een cachetreffer loopt niet langs
    # `load_dataset` (zie `cache.laad_met_cache`), dus die waarschuwt niet nog eens.
    if dataset.gwsw_versie.versie != "1.6":
        _logger.warning(
            "De dataset is GWSW-versie %s; de gepinde module-constanten (HAS_*, KLASSE_*) "
            "spellen 1.6 en gelden niet voor deze dataset -- gebruik de versie-juiste "
            "`GwswDataset.termen` of de str-methoden (uris_of_class, buren, "
            "kenmerken_met_waarde).",
            dataset.gwsw_versie.versie,
        )
    return dataset
