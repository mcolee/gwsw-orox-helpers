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

import dataclasses
import inspect
import re
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
