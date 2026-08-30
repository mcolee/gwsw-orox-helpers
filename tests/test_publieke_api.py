"""API-pin: het publieke oppervlak dat nlriochecker importeert ligt hier vast.

Deze package is de leeslaag onder nlriochecker en de Harde regel in `CLAUDE.md` is dat
die afnemer nooit breekt. Fasewerk (schrijven, clippen) is additief; een gewijzigde
handtekening of een verdwenen veld hoort niet ongemerkt te kunnen gebeuren. De lijsten
hieronder zijn geen wens maar een foto van wat nlriochecker importeert. Verzamelen doe je
die foto met een AST-sweep en niet met een kale `grep`: een import met haakjes zet zijn
namen op vervolgregels en die mist een regelgerichte grep (zo ontbraken de vier
`dataset.KLASSE_*`-constanten in de eerste versie van deze lijst). Wel goed:

    python3 - <<'PY'
    import ast, pathlib, collections
    namen = collections.defaultdict(set)
    for wortel in ("/home/martin/nlriochecker/src", "/home/martin/nlriochecker/tests"):
        for pad in pathlib.Path(wortel).rglob("*.py"):
            for knoop in ast.walk(ast.parse(pad.read_text(encoding="utf-8"))):
                if not isinstance(knoop, ast.ImportFrom):
                    continue
                if "gwsw_orox_helpers" in (knoop.module or ""):
                    namen[knoop.module].update(alias.name for alias in knoop.names)
    for module in sorted(namen):
        print(module, "->", ", ".join(sorted(namen[module])))
    PY

Wie toch grept, doet dat met context (`grep -rn -A3 "gwsw_orox_helpers"`) en leest de
vervolgregels mee. Namen die nlriochecker via de module benadert (`dataset.ontologiepaden`)
komen uit geen van beide sweeps en staan hier omdat de auteur ze aanwees.

Valt deze test om, dan is dat geen test die bijgewerkt moet worden: het is een
contractbreuk die eerst met de auteur besproken hoort te worden (CHANGELOG-regel plus
versiebump in beide repo's). Alleen een bewust en afgestemd contractbesluit verandert
de foto.
"""

from __future__ import annotations

import ast
import dataclasses
import importlib
import inspect
import re
import textwrap
from pathlib import Path
from typing import Any

import pytest

from gwsw_orox_helpers import bronnen, cache, dataset, errors, geometry, graaf, voortgang

MODULES = {
    "bronnen": bronnen,
    "cache": cache,
    "dataset": dataset,
    "errors": errors,
    "geometry": geometry,
    "graaf": graaf,
    "voortgang": voortgang,
}

# Een default die een objectrepr is, draagt een geheugenadres; dat is geen contract.
ADRES = re.compile(r" object at 0x[0-9a-f]+>")

# De submodules van het `clip`-package, in de volgorde van de importrichting: een submodule
# mag alleen naar een zuster *boven* zich wijzen. Zie de docstring van `gwsw_orox_helpers.clip`
# en de lagentabel in `docs/architectuur.md`. Wie een fase toevoegt, hernoemt of verplaatst,
# komt langs `test_de_clipsnit_ligt_vast` en `test_de_clipsubmodules_houden_de_importrichting`.
CLIPLAGEN = ("termen", "grenzen", "knip", "plan", "stroom", "merge", "orkest")

# De snit van de leeskant (issue #26): `bestand` draagt het parseerpad -- IO, codering en
# de procesbrede GC -- en `inlezen` houdt de domeinlezers, die uitsluitend een gevulde
# `GraafIndex` consumeren. Alle vier de namen zijn privé; ze staan hier niet als contract
# maar als *snit*, net als `CLIPLAGEN` hierboven.
BESTAND_FUNCTIES = ("_decode", "_gc_uit", "_parse", "_quiet_rdflib")

# De snit van de netwerkkant (issue #27): `netwerk` draagt de wandeling langs hasPart
# omhoog en de tekenrichting van een streng, als vrije functies op `nodes` en een
# typepredicaat. `dataset` houdt er drie gepinde methoden voor over die niets anders doen
# dan doorgeven. Net als `BESTAND_FUNCTIES` staan deze namen hier als *snit* en niet als
# contract -- de drie methoden staan als contract al in `HANDTEKENINGEN` hierboven.
# Eén tuple en niet twee: de vier functies van `netwerk` en de vier doorgeefluiken op
# `GwswDataset` heten hetzelfde, en dat is precies wat de bewaker toetst. `_schakels` staat
# erbij als *functie* maar wordt als methode niet afgedwongen -- die is privé en wordt
# binnen de package door niemand meer aangeroepen, dus de auteur mag hem schrappen zonder
# deze test rood te maken (zie de docstring van de methode). De drie andere kunnen niet
# stilletjes verdwijnen: die staan hierboven in `HANDTEKENINGEN`.
NETWERK_FUNCTIES = (
    "_schakels",
    "klim_naar_knoop",
    "resolve_network_node",
    "richting_van_geometrie",
)

# De modules die `netwerk` mag zien. Alleen `domein`: hij rekent met de waardeobjecten en
# met shapely, en weet van `dataset`, `cache`, `graaf` en de ontologie niets. Zou daar een
# rand bij komen, dan is de wandeling weer alleen via een volledige dataset toetsbaar.
NETWERK_MAG_IMPORTEREN = frozenset({"domein"})

# De modules die `bestand` mag zien. Hij staat in de lagentabel onder `inlezen` omdat hij
# alleen op deze bladeren leunt, en hij weet dus niets van de lezers, van `dataset` of van
# `cache`. Tussen `bestand` en `inlezen` loopt géén rand: die volgorde is een
# rangschikking en geen afhankelijkheid (zie `docs/architectuur.md`, "De lagen").
BESTAND_MAG_IMPORTEREN = frozenset({"codering", "errors", "graaf", "rdfmotor"})

# De enige modules van de package die de cliplaag mag importeren. `dataset`, `graaf`,
# `inlezen`, `klassen`, `ontologie` en `cache` staan er nadrukkelijk niet bij: de clip heeft
# een eigen pad naast de leeslaag en bouwt geen domeinmodel. `rdfmotor` staat er evenmin
# bij, en om een andere reden: de clip ontleedt en serialiseert niet zelf maar leent
# `lees_orox` / `schrijf_orox_quads` van `schrijven`. De term-fabrieken die `clip/` wél
# rechtstreeks bij pyoxigraph haalt, gaan sowieso niet door die adapter.
CLIP_MAG_IMPORTEREN = frozenset({"clip", "errors", "geometry", "namen", "schrijven"})


def _clipbronnen() -> dict[str, str]:
    """De broncode van het clip-package en van elke submodule, per naam."""
    from gwsw_orox_helpers import clip

    bronnen_ = {"clip": inspect.getsource(clip)}
    for naam in CLIPLAGEN:
        module = importlib.import_module(f"gwsw_orox_helpers.clip.{naam}")
        bronnen_[f"clip.{naam}"] = inspect.getsource(module)
    return bronnen_


def _pakketimporten(bron: str) -> set[str]:
    """De modules van de package die deze bron importeert, hoe hij ze ook schrijft.

    Aan de boom en niet aan een regex op regelbegin: een ingesprongen import in een functie,
    `from gwsw_orox_helpers import dataset` en `import gwsw_orox_helpers.graaf` zijn alle
    drie manieren om de leeslaag binnen te halen die een `^from ...`-patroon niet ziet.
    Wat eruit komt is de naam onder de package (`dataset`, `clip.knip`).
    """
    gevonden: set[str] = set()
    for knoop in ast.walk(ast.parse(bron)):
        if isinstance(knoop, ast.ImportFrom):
            if knoop.level:  # `from . import x` / `from .knip import y`, binnen clip/
                gevonden.update(
                    f"clip.{knoop.module}" if knoop.module else f"clip.{alias.name}"
                    for alias in knoop.names
                )
            elif knoop.module == "gwsw_orox_helpers":
                gevonden.update(alias.name for alias in knoop.names)
            elif knoop.module and knoop.module.startswith("gwsw_orox_helpers."):
                gevonden.add(knoop.module.removeprefix("gwsw_orox_helpers."))
        elif isinstance(knoop, ast.Import):
            gevonden.update(
                alias.name.removeprefix("gwsw_orox_helpers.")
                for alias in knoop.names
                if alias.name.startswith("gwsw_orox_helpers.")
            )
    return gevonden


def _is_docstring(regel: ast.stmt) -> bool:
    """Of dit de docstring van een functie is; die telt niet als lichaam."""
    return (
        isinstance(regel, ast.Expr)
        and isinstance(regel.value, ast.Constant)
        and isinstance(regel.value.value, str)
    )


def _op(naam: str) -> Any:
    """Zoekt `module.naam` of `module.Klasse.methode` op."""
    module, *rest = naam.split(".")
    gevonden: Any = MODULES[module]
    for stap in rest:
        gevonden = getattr(gevonden, stap)
    return gevonden


def _handtekening(obj: Any) -> str:
    """De handtekening als tekst, zonder het geheugenadres van een objectdefault."""
    return ADRES.sub(" object>", str(inspect.signature(obj)))


HANDTEKENINGEN: dict[str, str] = {
    # De lader en zijn domeinmodel.
    "dataset.load_dataset": (
        "(dataset_path: 'Path', ontology_paths: 'list[Path] | None' = None, "
        "fallback_encoding: 'str | None' = None, *, voortgang: 'Voortgang' = "
        "<gwsw_orox_helpers.voortgang.NulVoortgang object>) -> 'GwswDataset'"
    ),
    "dataset.markeer_vulwaarden": (
        "(dataset: 'GwswDataset', kenmerken: 'Sequence[str]', band_m: 'float') -> 'GwswDataset'"
    ),
    "dataset.ontologiepaden": "(ontology_paths: 'list[Path] | None') -> 'list[Path]'",
    # Additief sinds issue #33: de ontologie-index die `load_dataset` intern opbouwt, nu
    # ook los op te vragen. Hij staat hier **niet** omdat nlriochecker hem importeert --
    # dat doet die (nog) niet -- maar omdat de auteur hem aanwees: issue #33 zet
    # `lees_ontologie` met zoveel woorden in dit bestand ("additief: `lees_ontologie` mag
    # erbij; bestaande pins ongewijzigd"). Dat is de tweede categorie uit de docstring
    # hierboven. De parameternamen zijn Nederlands (`paden`/`terugvalcodering`), anders
    # dan de bevroren Engelse van `load_dataset`/`laad_met_cache`: de auteur koos bij #33
    # voor `CLAUDE.md` (Nederlandse identifiers) boven symmetrie, op het moment dat de
    # naam nog vrij lag. Vanaf hier ligt hij vast.
    "dataset.lees_ontologie": (
        "(paden: 'list[Path] | None' = None, "
        "terugvalcodering: 'str | None' = None, *, voortgang: 'Voortgang' = "
        "<gwsw_orox_helpers.voortgang.NulVoortgang object>) -> 'GraafIndex'"
    ),
    "dataset.GwswDataset": (
        "(source: 'Path', graph: 'GraafIndex', nodes: 'dict[str, Node]', "
        "conduits: 'dict[str, Conduit]', subclasses: 'dict[str, frozenset[str]]', "
        "geometry_errors: 'dict[str, str]' = <factory>, "
        "decode_fallback: 'DecodeFallback | None' = None, "
        "ontologies: 'tuple[Path, ...]' = (), structural_diff: 'dict[str, int]' = <factory>, "
        "kenmerk_property: 'dict[str, str]' = <factory>, "
        "functie_per_klasse: 'dict[str, str]' = <factory>, "
        "koppelingsherstel: 'Koppelingsherstel' = "
        "Koppelingsherstel(koppelingen=0, hulpstukken=0)) -> None"
    ),
    "dataset.Node": (
        "(uri: 'str', label: 'str', types: 'frozenset[str]', orientation: 'str | None', "
        "orientation_types: 'frozenset[str]', point: 'Point | None', z: 'float | None', "
        "parents: 'tuple[str, ...]', aspects: 'tuple[Aspect, ...]' = (), "
        "maaiveld_aspect: 'Aspect | None' = None, maaiveld_inwinning: 'Inwinning | None' = None, "
        "deksel_aspect: 'Aspect | None' = None, deksel_inwinning: 'Inwinning | None' = None, "
        "multipart: 'bool' = False, vulwaarden: 'tuple[Vulwaarde, ...]' = ()) -> None"
    ),
    "dataset.Conduit": (
        "(uri: 'str', label: 'str', types: 'frozenset[str]', line: 'LineString | None', "
        "start_node: 'str | None', end_node: 'str | None', "
        "bob_start_aspect: 'Aspect | None' = None, bob_end_aspect: 'Aspect | None' = None, "
        "aspects: 'tuple[Aspect, ...]' = (), multipart: 'bool' = False, "
        "z_values: 'tuple[float | None, ...]' = (), "
        "vulwaarden: 'tuple[Vulwaarde, ...]' = ()) -> None"
    ),
    "dataset.Aspect": (
        "(kind: 'str', value: 'str | None' = None, reference: 'str | None' = None, "
        "inwinning: 'Inwinning | None' = None) -> None"
    ),
    "dataset.Inwinning": "(wijze: 'str | None' = None, datum: 'date | None' = None) -> None",
    "dataset.Vulwaarde": "(kind: 'str', value: 'float') -> None",
    # De graafhulpen die de checks rechtstreeks aanroepen.
    "dataset.parts_of": "(graph: 'GraafIndex', subject: 'RdfNode') -> 'Iterator[RdfNode]'",
    "dataset.part_holders_of": "(graph: 'GraafIndex', subject: 'RdfNode') -> 'Iterator[RdfNode]'",
    "dataset.aspects_of": "(graph: 'GraafIndex', subject: 'RdfNode') -> 'Iterator[RdfNode]'",
    "dataset.aspect_holders_of": (
        "(graph: 'GraafIndex', subject: 'RdfNode') -> 'Iterator[RdfNode]'"
    ),
    # De methoden van GwswDataset waar de checks op leunen.
    "dataset.GwswDataset.beheerobjecttype": "(self, uri: 'str') -> 'str'",
    "dataset.GwswDataset.closure": "(self, root: 'str') -> 'frozenset[str]'",
    "dataset.GwswDataset.graph_is_a": "(self, uri: 'str', root: 'str') -> 'bool'",
    "dataset.GwswDataset.graph_types_of": "(self, uri: 'str') -> 'frozenset[str]'",
    "dataset.GwswDataset.is_a": "(self, uri: 'str', root: 'str') -> 'bool'",
    "dataset.GwswDataset.is_connection_class": "(self, root: 'str') -> 'bool'",
    "dataset.GwswDataset.klim_naar_knoop": (
        "(self, uri: 'str | None', roots: 'list[str]') -> 'tuple[str | None, frozenset[str]]'"
    ),
    "dataset.GwswDataset.of_class": "(self, root: 'str') -> 'list[str]'",
    "dataset.GwswDataset.onderdeel_aspecten": "(self, uri: 'str') -> 'list[Aspect]'",
    "dataset.GwswDataset.onderdeel_label": "(self, uri: 'str') -> 'str | None'",
    "dataset.GwswDataset.onderdelen": (
        "(self, uri: 'str', wortel: 'str | None' = None) -> 'list[str]'"
    ),
    "dataset.GwswDataset.resolve_network_node": (
        "(self, uri: 'str | None', roots: 'list[str]') -> 'str | None'"
    ),
    "dataset.GwswDataset.richting_van_geometrie": (
        "(self, conduit: 'Conduit', roots: 'list[str]') -> 'tuple[bool, Node, Node] | None'"
    ),
    "dataset.GwswDataset.stelsel_leden": (
        "(self, uri: 'str') -> 'tuple[tuple[str, ...], tuple[str, ...]]'"
    ),
    "dataset.GwswDataset.subjects_of_class": "(self, root: 'str') -> 'list[RdfNode]'",
    "dataset.GwswDataset.subset": "(self, uris: 'Iterable[str]') -> 'GwswDataset'",
    "dataset.GwswDataset.types_of": "(self, uri: 'str') -> 'frozenset[str]'",
    # De grafindex.
    "graaf.GraafIndex": "() -> 'None'",
    "graaf.GraafIndex.heeft_subject": "(self, term: 'RdfNode') -> 'bool'",
    "graaf.GraafIndex.objects": (
        "(self, subject: 'RdfNode', predicate: 'RdfNode') -> 'Iterator[RdfNode]'"
    ),
    "graaf.GraafIndex.subject_objects": (
        "(self, predicate: 'RdfNode') -> 'Iterator[tuple[RdfNode, RdfNode]]'"
    ),
    "graaf.GraafIndex.subjects": (
        "(self, predicate: 'RdfNode', object_: 'RdfNode') -> 'Iterator[RdfNode]'"
    ),
    "graaf.GraafIndex.value": (
        "(self, subject: 'RdfNode', predicate: 'RdfNode') -> 'RdfNode | None'"
    ),
    "graaf.GraafIndex.voeg_toe": (
        "(self, subject: 'RdfNode', predicate: 'RdfNode', object_: 'RdfNode') -> 'None'"
    ),
    "graaf.GraafIndex.vul_uit": "(self, quads: 'Iterable[pyoxigraph.Quad]') -> 'None'",
    # De termomzetting waarmee de index gevuld wordt. Hij staat hier omdat de auteur hem
    # aanwees bij issue #21/#23: nlriochecker importeert hem rechtstreeks
    # (`scripts/maak_voorbeeld.py:57`, `from gwsw_orox_helpers.graaf import naar_rdflib`)
    # om een pyoxigraph-parse in rdflib-termen te lezen zonder de index te bouwen. Dat is
    # dezelfde tweede categorie als `dataset.lees_ontologie` hierboven: geen naam die uit
    # de AST-sweep over `src/` en `tests/` van de afnemer komt, maar wel een naam waarop
    # hij leunt. **Additief**: deze regel legt de bestaande handtekening vast en verandert
    # er niets aan.
    "graaf.naar_rdflib": (
        "(term: 'pyoxigraph.NamedNode | pyoxigraph.BlankNode | pyoxigraph.Literal | "
        "pyoxigraph.Triple') -> 'RdfNode'"
    ),
    # Geometrie.
    "geometry.parse_gml": "(literal: 'str') -> 'Point | LineString | Polygon'",
    "geometry.parse_gml_z": "(literal: 'str') -> 'list[float | None]'",
    "geometry.is_multipart_literal": "(literal: 'str') -> 'bool'",
    # De cache-API.
    "cache.laad_met_cache": (
        "(dataset_path: 'Path', ontology_paths: 'list[Path] | None' = None, "
        "cache_dir: 'Path | None' = None, gebruik_cache: 'bool' = True, "
        "fallback_encoding: 'str | None' = None, *, voortgang: 'Voortgang' = "
        "<gwsw_orox_helpers.voortgang.NulVoortgang object>) "
        "-> 'tuple[GwswDataset, CacheUitslag]'"
    ),
    "cache.cachesleutel": (
        "(dataset_path: 'Path', ontology_paths: 'list[Path] | None' = None, "
        "fallback_encoding: 'str | None' = None) -> 'str'"
    ),
    "cache.standaard_cachemap": "() -> 'Path'",
    "cache.CacheUitslag": (
        "(bron: 'str', sleutel: 'str', seconden: 'float', melding: 'str' = '') -> None"
    ),
    # Voortgang als protocol.
    "voortgang.NulVoortgang": "()",
    "voortgang.Voortgang.start_fase": "(self, naam: 'str', totaal: 'int | None') -> 'None'",
    "voortgang.Voortgang.stap": "(self, n: 'int' = 1, label: 'str | None' = None) -> 'None'",
    "voortgang.Voortgang.einde_fase": "(self) -> 'None'",
    # Gebundelde bronnen.
    "bronnen.gebundelde_ontologie": "() -> pathlib.Path",
    "bronnen.vocabulaire_index_pad": "() -> pathlib.Path",
}

VELDEN: dict[str, tuple[str, ...]] = {
    "dataset.GwswDataset": (
        "source",
        "graph",
        "nodes",
        "conduits",
        "subclasses",
        "geometry_errors",
        "decode_fallback",
        "ontologies",
        "structural_diff",
        "kenmerk_property",
        "functie_per_klasse",
        "koppelingsherstel",
    ),
    "dataset.Node": (
        "uri",
        "label",
        "types",
        "orientation",
        "orientation_types",
        "point",
        "z",
        "parents",
        "aspects",
        "maaiveld_aspect",
        "maaiveld_inwinning",
        "deksel_aspect",
        "deksel_inwinning",
        "multipart",
        "vulwaarden",
    ),
    "dataset.Conduit": (
        "uri",
        "label",
        "types",
        "line",
        "start_node",
        "end_node",
        "bob_start_aspect",
        "bob_end_aspect",
        "aspects",
        "multipart",
        "z_values",
        "vulwaarden",
    ),
    "dataset.Aspect": ("kind", "value", "reference", "inwinning"),
    "dataset.Inwinning": ("wijze", "datum"),
    "dataset.Vulwaarde": ("kind", "value"),
    "cache.CacheUitslag": ("bron", "sleutel", "seconden", "melding"),
}

# De IRI-constanten die nlriochecker rechtstreeks importeert; hun waarde is het contract.
CONSTANTEN: dict[str, str] = {
    "dataset.GWSW": "http://data.gwsw.nl/1.6/totaal/",
    "dataset.HAS_CONNECTION": "http://data.gwsw.nl/1.6/totaal/hasConnection",
    "dataset.HAS_REFERENCE": "http://data.gwsw.nl/1.6/totaal/hasReference",
    "dataset.HAS_VALUE": "http://data.gwsw.nl/1.6/totaal/hasValue",
    # De klassen waarop nlriochecker aspecten herkent; komen uit een haakjes-import.
    "dataset.KLASSE_BOB_BEGIN": "http://data.gwsw.nl/1.6/totaal/BobBeginpuntLeiding",
    "dataset.KLASSE_BOB_EIND": "http://data.gwsw.nl/1.6/totaal/BobEindpuntLeiding",
    "dataset.KLASSE_MAAIVELDHOOGTE": "http://data.gwsw.nl/1.6/totaal/Maaiveldhoogte",
    "dataset.KLASSE_PUTDEKSELNIVEAU": "http://data.gwsw.nl/1.6/totaal/Putdekselniveau",
}


@pytest.mark.parametrize("naam", sorted(HANDTEKENINGEN))
def test_handtekening_ligt_vast(naam: str) -> None:
    assert _handtekening(_op(naam)) == HANDTEKENINGEN[naam]


@pytest.mark.parametrize("naam", sorted(VELDEN))
def test_velden_liggen_vast(naam: str) -> None:
    # Niet-init-velden (memo's) horen niet bij het contract; `GwswDataset._resolved_nodes`
    # is er zo een.
    velden = tuple(veld.name for veld in dataclasses.fields(_op(naam)) if veld.init)
    assert velden == VELDEN[naam]


@pytest.mark.parametrize("naam", sorted(CONSTANTEN))
def test_constante_ligt_vast(naam: str) -> None:
    assert str(_op(naam)) == CONSTANTEN[naam]


def test_uitzonderingen_houden_hun_plaats_in_de_hierarchie() -> None:
    # nlriochecker vangt DatasetError; GeometryError vangt het als ValueError.
    assert issubclass(errors.DatasetError, errors.OroxError)
    assert issubclass(errors.OroxError, Exception)
    assert issubclass(geometry.GeometryError, ValueError)


def test_nul_voortgang_is_een_niets_doende_voortgang() -> None:
    assert isinstance(voortgang.NUL_VOORTGANG, voortgang.NulVoortgang)
    assert voortgang.NUL_VOORTGANG.start_fase("fase", 3) is None
    assert voortgang.NUL_VOORTGANG.stap(1, "label") is None
    assert voortgang.NUL_VOORTGANG.einde_fase() is None


def test_schrijflaag_is_additief() -> None:
    """Fase 2 voegt namen toe en haalt er geen weg (Harde regel: additief only)."""
    from gwsw_orox_helpers import schrijven

    assert callable(schrijven.schrijf_orox)
    assert callable(schrijven.schrijf_orox_quads)
    assert callable(schrijven.lees_orox)
    # De schrijver hangt niet aan de leeslaag: geen import van dataset/graaf/cache.
    bron = inspect.getsource(schrijven)
    assert "from gwsw_orox_helpers.dataset import" not in bron
    assert "from gwsw_orox_helpers.graaf import" not in bron


def test_cliplaag_is_additief() -> None:
    """Fase 3 doet hetzelfde: namen erbij, en een eigen pad naast de leeslaag."""
    from gwsw_orox_helpers import clip

    assert callable(clip.clip_orox)
    assert callable(clip.merge_orox)
    assert _handtekening(clip.clip_orox) == (
        "(bron: 'Path', grenzen: 'Path', uitmap: 'Path', *, sleutel: 'str', "
        "fallback_encoding: 'str | None' = None) -> 'list[Path]'"
    )
    assert _handtekening(clip.merge_orox) == "(delen: 'list[Path]', doel: 'Path') -> 'None'"
    # En ze staan, net als de schrijflaag, ook op de package zelf.
    import gwsw_orox_helpers

    assert gwsw_orox_helpers.clip_orox is clip.clip_orox
    assert gwsw_orox_helpers.merge_orox is clip.merge_orox
    # De clip hangt net zomin aan de leeslaag; alleen de GML-lezers worden gedeeld. Sinds de
    # hersnit is `clip` een package, dus de vraag geldt niet alleen aan het oppervlak maar aan
    # elke submodule: een enkele `from ...dataset import` in een fase zou de laag alsnog op de
    # leeslaag laten hangen zonder dat het her-exporterende `__init__.py` er iets van laat zien.
    for naam, bron in _clipbronnen().items():
        assert "from gwsw_orox_helpers.dataset import" not in bron, naam
        assert "from gwsw_orox_helpers.graaf import" not in bron, naam


def test_de_clipsnit_ligt_vast() -> None:
    """Het clip-package bestaat uit precies deze fasen, elk in een eigen submodule."""
    from gwsw_orox_helpers import clip

    pakket = Path(clip.__file__ or "").parent
    aanwezig = {pad.stem for pad in pakket.glob("*.py")} - {"__init__"}

    assert aanwezig == set(CLIPLAGEN)
    assert clip.__doc__ is not None and len(clip.__doc__.splitlines()) > 50, (
        "het verhaal van de clip hoort in de package-docstring te blijven staan"
    )
    # Het `__init__.py` is dun: het draagt het verhaal en de her-export, geen fase. Aan de
    # boom en niet aan de tekst -- het verhaal noemt zelf functienamen, dus een kale
    # `"def " not in bron` zou omvallen zodra iemand er `_maak_plan` in uitschrijft.
    boom = ast.parse(inspect.getsource(clip))
    definities = [
        knoop.name
        for knoop in boom.body
        if isinstance(knoop, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    ]
    assert definities == [], f"{definities} horen in een fase te staan, niet in __init__.py"


def test_de_bestandssnit_ligt_vast() -> None:
    """Het parseerpad staat in `bestand`, de domeinlezers in `inlezen` (issue #26).

    Dezelfde soort bewaker als `test_de_clipsnit_ligt_vast`, en om dezelfde reden: de
    twee clusters in `inlezen` deelden alleen de `GraafIndex` en zijn nu gescheiden, maar
    zonder test is dat een zin in een docstring en belet niets dat de volgende lezer weer
    een `path.read_bytes()` naast een kenmerklezer zet.

    Drie dingen tegelijk, elk op de AST en niet op de tekst. Welke functies `bestand`
    draagt -- precies de vier, niet meer -- zodat een domeinlezer er niet stilzwijgend bij
    komt te staan. Dat `inlezen` ze niet meer kent, ook niet als her-import: hij raakt geen
    bestand meer aan, en dat is de winst van de snit. En de importrichting: `bestand` leunt
    alleen op de bladeren (`codering`, `errors`, `graaf`, `rdfmotor`) en er loopt geen rand
    tússen hem en `inlezen` -- in geen van beide richtingen. Zou zo'n rand er alsnog komen,
    dan zou het testen van de lezers weer een echt bestand vergen.

    De importtoets is een **deelverzameling** en geen gelijkheid, net als bij
    `CLIP_MAG_IMPORTEREN`: de constante is een toestemmingslijst ("mag importeren"), en een
    gelijkheid zou een module rood maken die er met goede reden eentje minder nodig heeft.
    Wat bewaakt moet worden is de andere kant -- een rand naar `inlezen`, `dataset` of
    `cache` -- en die vangt de deelverzameling wél.

    Wat hier niet staat maar er wel bij hoort: `bestand` hoort in `cache.LADERMODULES`,
    anders blijft een cache na een wijziging aan het parseerpad de oude lezing teruggeven.
    `tests/test_cache.py::test_de_ladermodulelijst_dekt_de_hele_leeslaag` is daar de
    bewaker van -- die eist van elke module van de package dat hij gehasht of met een reden
    uitgezonderd is, dus een tweede assert hier zou dezelfde regel nog eens zijn.
    """
    from gwsw_orox_helpers import bestand, inlezen

    boom = ast.parse(inspect.getsource(bestand))
    definities = tuple(
        sorted(
            knoop.name
            for knoop in boom.body
            if isinstance(knoop, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        )
    )
    assert definities == BESTAND_FUNCTIES

    achtergebleven = sorted(naam for naam in BESTAND_FUNCTIES if naam in vars(inlezen))
    assert achtergebleven == [], (
        f"{achtergebleven} hoort in `bestand` te wonen; `inlezen` leest geen bestanden meer"
    )

    assert _pakketimporten(inspect.getsource(bestand)) <= BESTAND_MAG_IMPORTEREN
    assert "bestand" not in _pakketimporten(inspect.getsource(inlezen)), (
        "tussen `bestand` en `inlezen` hoort geen rand te lopen, ook niet als her-import"
    )


def test_de_netwerksnit_ligt_vast() -> None:
    """De wandeling woont in `netwerk`; `dataset` houdt er doorgeefluiken over (issue #27).

    Drie dingen tegelijk, elk op de AST en niet op de tekst -- dezelfde soort bewaker als
    `test_de_bestandssnit_ligt_vast`. Welke functies `netwerk` draagt, precies de vier.
    Dat hij alleen op `domein` leunt, zodat de wandeling toetsbaar blijft zonder een
    ingelezen export (dat is de hele winst van de verhuizing; een enkele import van
    `dataset` of `graaf` maakt haar weer ongedaan). En dat de methoden op `GwswDataset`
    **dun** zijn gebleven: één `return netwerk.<zelfde naam>(...)` en niets anders.

    Die derde is de belangrijkste en hij is niet aan het antwoord te zien. Zou iemand de
    wandeling terugkopiëren in `dataset.py` -- of er "even" een extra stap voor zetten --
    dan blijven alle gedragstests groen terwijl er weer twee exemplaren van dezelfde
    logica staan, precies de toestand die #27 opruimde.

    Wat hier niet staat maar er wel bij hoort: de handtekeningen van de drie publieke
    methoden liggen in `HANDTEKENINGEN` vast, en `netwerk` hoort in `cache.LADERMODULES`
    (`tests/test_cache.py::test_de_ladermodulelijst_dekt_de_hele_leeslaag` bewaakt dat).
    """
    from gwsw_orox_helpers import netwerk

    boom = ast.parse(inspect.getsource(netwerk))
    definities = tuple(
        sorted(
            knoop.name
            for knoop in boom.body
            if isinstance(knoop, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        )
    )
    assert definities == tuple(sorted(NETWERK_FUNCTIES))

    assert _pakketimporten(inspect.getsource(netwerk)) <= NETWERK_MAG_IMPORTEREN

    for naam in NETWERK_FUNCTIES:
        methode_op_de_dataset = getattr(dataset.GwswDataset, naam, None)
        if methode_op_de_dataset is None:  # alleen `_schakels` mag ooit verdwijnen
            continue
        bron = textwrap.dedent(inspect.getsource(methode_op_de_dataset))
        (methode,) = [
            knoop for knoop in ast.walk(ast.parse(bron)) if isinstance(knoop, ast.FunctionDef)
        ]
        lijf = [regel for regel in methode.body if not _is_docstring(regel)]
        assert len(lijf) == 1, f"{naam} doet meer dan doorgeven"
        (regel,) = lijf
        assert isinstance(regel, ast.Return)
        aanroep = regel.value
        assert isinstance(aanroep, ast.Call), f"{naam} geeft niet een aanroep terug"
        doel = aanroep.func
        assert isinstance(doel, ast.Attribute) and isinstance(doel.value, ast.Name)
        assert (doel.value.id, doel.attr) == ("netwerk", naam), f"{naam} wijst ergens anders heen"


def test_de_clipsubmodules_houden_de_importrichting() -> None:
    """Elke fase importeert alleen de bladeren onder de cliplaag en zusters boven zich.

    Twee dingen tegelijk, en allebei aan de broncode: welke modules van de package een fase
    mag zien (`CLIP_MAG_IMPORTEREN` -- geen `dataset`/`graaf`/`inlezen`/`cache`), en dat de
    zusterranden binnen het package een richting houden. Die richting is de volgorde van
    `CLIPLAGEN`: `termen` weet van niemand, `orkest` weet van iedereen. Zonder deze test kan
    een fase stil een lus met een andere sluiten, en dan is de hersnit weer een bak.
    """
    for naam, bron in _clipbronnen().items():
        eigen = naam.removeprefix("clip.") if naam != "clip" else None
        for pad in sorted(_pakketimporten(bron)):
            kop, *rest = pad.split(".")
            assert kop in CLIP_MAG_IMPORTEREN, f"{naam} importeert {pad}"
            if kop != "clip" or not rest:
                continue
            zuster = rest[0]
            assert zuster in CLIPLAGEN, f"{naam} importeert onbekende zuster {zuster}"
            if eigen is None:  # __init__.py mag elke fase her-exporteren
                continue
            assert CLIPLAGEN.index(zuster) < CLIPLAGEN.index(eigen), (
                f"{naam} importeert {zuster}, dat onder hem ligt; de importrichting draait om"
            )
