"""Tests voor `netwerk`: de wandeling omhoog en de tekenrichting, als vrije functies.

Twee dingen tegelijk, en ze horen bij elkaar. Ten eerste dat de vrije functies zonder
dataset te gebruiken zijn -- dat is de winst van issue #27: een handgebouwd
`nodes`-woordenboek en een `is_a`-lambda zijn genoeg, er hoeft geen TTL geladen te
worden. Ten tweede dat de gepinde methoden op `GwswDataset` er dunne doorgeefluiken
naar zijn gebleven: **gelijk antwoord én gelijke memo-semantiek**. Die tweede helft is
geen doublure van `tests/test_dataset.py` maar de bewaker van de verhuizing zelf.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from shapely.geometry import LineString, Point

from gwsw_orox_helpers import netwerk
from gwsw_orox_helpers.dataset import GwswDataset, load_dataset
from gwsw_orox_helpers.domein import Conduit, Node

TOETS = "http://example.org/toets#"
TTL_DIR = Path(__file__).parent / "fixtures" / "ttl"

# Dezelfde wortels als `tests/test_dataset.py`; zo staat de vergelijking op de lijst
# waarmee de wandeling in de praktijk gevoerd wordt.
NETWERKWORTELS = ["Put", "Gemaal", "Lozingspunt"]


def _knoop(uri: str, *soorten: str, houders: tuple[str, ...] = ()) -> Node:
    """Een kale knoop met alleen wat de wandeling van hem leest: typen en houders."""
    return Node(
        uri=uri,
        label=uri,
        types=frozenset(soorten),
        orientation=None,
        orientation_types=frozenset(),
        point=None,
        z=None,
        parents=houders,
    )


def _is_a(nodes: dict[str, Node]) -> netwerk.TypePredicaat:
    """Het smalle typepredicaat van `GwswDataset.is_a`, op een handgebouwd woordenboek."""
    return lambda uri, root: root in nodes[uri].types if uri in nodes else False


def test_schakels_houdt_alleen_de_bezochte_uris_die_een_knoop_zijn(
    voorbeeld: GwswDataset,
) -> None:
    """De bezochte URI's die een knoop zijn; de rest hoort niet in een analyseset.

    De verwachting komt niet uit de methode maar uit de fixture: `dataset_voorbeeld.ttl`
    draagt vier knopen, en een URI die er niet in staat hoort weg te vallen -- ook de
    orientatie van een put, die wel in de graaf staat maar nooit een knoop wordt.
    """
    bezocht = {*voorbeeld.nodes, f"{TOETS}PutA_ori", f"{TOETS}BestaatNiet"}

    assert netwerk._schakels(bezocht, voorbeeld.nodes) == frozenset(voorbeeld.nodes)
    # En de methode zegt hetzelfde: zij is sinds issue #27 een doorgeefluik.
    assert voorbeeld._schakels(bezocht) == netwerk._schakels(bezocht, voorbeeld.nodes)


def test_de_wandeling_werkt_op_een_handgebouwd_woordenboek() -> None:
    """De winst van issue #27: geen TTL, geen ontologie, geen `GwswDataset`.

    Het geval is dat van `dataset_twee_houders_*.ttl`, maar dan met de hand: een
    compartiment dat onder een straat *en* onder een put hangt. De straat is geen knoop
    en loopt dood; wie een enkel pad volgt komt daar terecht en meldt de streng ten
    onrechte als niet aangesloten. De verwachte uitkomst is dus de put, plus de bezochte
    schakels die zelf een knoop zijn -- het compartiment en de put, niet de straat.
    """
    nodes = {
        f"{TOETS}PutB": _knoop(f"{TOETS}PutB", "Put"),
        f"{TOETS}PutB_c1": _knoop(
            f"{TOETS}PutB_c1", "Compartiment", houders=(f"{TOETS}Straat", f"{TOETS}PutB")
        ),
    }

    knoop, schakels = netwerk.klim_naar_knoop(f"{TOETS}PutB_c1", ["Put"], nodes, _is_a(nodes))

    assert knoop == f"{TOETS}PutB"
    assert schakels == frozenset({f"{TOETS}PutB_c1", f"{TOETS}PutB"})


def test_de_wandeling_loopt_dood_zonder_knoop_erboven() -> None:
    """Zonder houder die een wortelklasse draagt is er geen knoop -- en geen fout.

    De schakels komen er dan nog wel uit: `afbakening` houdt ze in de analyseset, zodat
    dezelfde wandeling op de uitgedunde dataset niet alsnog doodloopt.
    """
    nodes = {f"{TOETS}T1": _knoop(f"{TOETS}T1", "Hulpstuk")}

    assert netwerk.klim_naar_knoop(f"{TOETS}T1", ["Put"], nodes, _is_a(nodes)) == (
        None,
        frozenset({f"{TOETS}T1"}),
    )
    # Een URI die helemaal niet bestaat loopt op dezelfde manier dood, met lege schakels.
    assert netwerk.klim_naar_knoop(f"{TOETS}Weg", ["Put"], nodes, _is_a(nodes)) == (
        None,
        frozenset(),
    )
    # En `None` in, `None` uit: dat is wat een streng zonder koppeling oplevert.
    assert netwerk.klim_naar_knoop(None, ["Put"], nodes, _is_a(nodes)) == (None, frozenset())


def test_de_vrije_wandeling_geeft_hetzelfde_als_de_methode(voorbeeld: GwswDataset) -> None:
    """Gelijkwaardigheid op elke URI van de voorbeeldexport, plus twee missers.

    Dit is de bewaker van de verhuizing zelf (issue #27): de methode is een doorgeefluik
    geworden, en die belofte geldt niet voor één gunstig geval maar voor elke knoop, elke
    streng en de URI's die nergens staan.
    """
    uris: list[str | None] = [*voorbeeld.nodes, *voorbeeld.conduits, f"{TOETS}BestaatNiet", None]

    assert len(uris) > 2, "voorwaarde: er valt iets te vergelijken"
    for uri in uris:
        assert netwerk.klim_naar_knoop(
            uri, NETWERKWORTELS, voorbeeld.nodes, voorbeeld.is_a
        ) == voorbeeld.klim_naar_knoop(uri, NETWERKWORTELS), uri


def test_de_vrije_herleiding_geeft_hetzelfde_als_de_methode(voorbeeld: GwswDataset) -> None:
    """`resolve_network_node` is de eerste uitkomst van de wandeling, en blijft dat.

    Met een verse memo per aanroep, zodat de vergelijking over het rekenwerk gaat en
    niet over een gedeelde memo; dat die memo werkt staat in de test hieronder.
    """
    uris: list[str | None] = [*voorbeeld.nodes, *voorbeeld.conduits, f"{TOETS}BestaatNiet", None]

    for uri in uris:
        vrij = netwerk.resolve_network_node(
            uri, NETWERKWORTELS, voorbeeld.nodes, voorbeeld.is_a, {}
        )
        assert vrij == voorbeeld.resolve_network_node(uri, NETWERKWORTELS), uri
        assert vrij == voorbeeld.klim_naar_knoop(uri, NETWERKWORTELS)[0], uri


def test_de_herleiding_schrijft_en_leest_de_meegegeven_memo(voorbeeld: GwswDataset) -> None:
    """De memo is een parameter; hij wordt gevuld en op de tweede aanroep gelezen.

    Het lezen is niet aan een gelijke uitkomst te zien -- die zou de wandeling ook zonder
    memo geven. Vandaar het vergiftigde antwoord: staat er iets in de memo, dan hoort dat
    eruit te komen zonder dat er opnieuw geklommen wordt.
    """
    compartiment = f"{TOETS}PutB_c1"
    sleutel = (compartiment, tuple(NETWERKWORTELS))
    memo: netwerk.Knoopmemo = {}

    eerste = netwerk.resolve_network_node(
        compartiment, NETWERKWORTELS, voorbeeld.nodes, voorbeeld.is_a, memo
    )

    assert eerste == f"{TOETS}PutB"
    assert memo == {sleutel: f"{TOETS}PutB"}

    memo[sleutel] = "urn:vergiftigd"
    assert (
        netwerk.resolve_network_node(
            compartiment, NETWERKWORTELS, voorbeeld.nodes, voorbeeld.is_a, memo
        )
        == "urn:vergiftigd"
    )
    # `None` in gaat buiten de memo om: er valt niets te herleiden en niets te onthouden.
    geen = netwerk.resolve_network_node(None, NETWERKWORTELS, voorbeeld.nodes, voorbeeld.is_a, memo)
    assert geen is None
    assert set(memo) == {sleutel}


def test_de_methode_voedt_de_memo_van_de_dataclass(voorbeeld: GwswDataset) -> None:
    """Het doorgeefluik gebruikt `_resolved_nodes` en geen eigen memo (issue #27).

    Dit is de helft die stil kan breken: een vrije functie met een eigen memo zou
    dezelfde antwoorden geven en toch elke run opnieuw klimmen. Weer met een vergiftigd
    antwoord, want alleen dat maakt het lezen van *deze* dict zichtbaar.

    Op een `replace()`-kopie en niet op de fixture zelf: die is sessiebreed, en een
    vergiftigde memo achterlaten zou elke volgende test besmetten. De kopie deelt de
    knopen en krijgt een eigen lege memo -- dat is dezelfde eigenschap die de test
    hieronder vastlegt, hier als gereedschap gebruikt.
    """
    eigen = replace(voorbeeld)
    compartiment = f"{TOETS}PutB_c1"
    sleutel = (compartiment, tuple(NETWERKWORTELS))

    assert eigen.resolve_network_node(compartiment, NETWERKWORTELS) == f"{TOETS}PutB"
    assert eigen._resolved_nodes[sleutel] == f"{TOETS}PutB"

    eigen._resolved_nodes[sleutel] = "urn:vergiftigd"

    assert eigen.resolve_network_node(compartiment, NETWERKWORTELS) == "urn:vergiftigd"
    # En de fixture zelf is niet aangeraakt.
    assert voorbeeld._resolved_nodes.get(sleutel) in (None, f"{TOETS}PutB")


def test_een_replace_afgeleide_begint_met_een_lege_herleidingsmemo(
    voorbeeld: GwswDataset,
) -> None:
    """`subset()` erft de memo niet, en dat is precies de bedoeling van `init=False`.

    Een uitgedunde dataset kan anders resolven dan de volle export -- de wandeling ziet
    minder knopen -- dus een gedeelde memo zou antwoorden tussen de twee laten lekken.
    De verhuizing naar `netwerk` verandert daar niets aan: de memo blijft op de dataclass
    en de doorgeefluik geeft die van *zijn eigen* instantie mee.
    """
    compartiment = f"{TOETS}PutB_c1"
    put = f"{TOETS}PutB"
    assert voorbeeld.resolve_network_node(compartiment, NETWERKWORTELS) == put
    # De aanroep hierboven vult de memo; deze test hangt dus niet aan een eerdere.
    assert voorbeeld._resolved_nodes, "voorwaarde: de volle dataset heeft een gevulde memo"

    kleiner = voorbeeld.subset([uri for uri in voorbeeld.nodes if uri != put])

    assert kleiner._resolved_nodes == {}
    # En zij rekent zelf: zonder de put erboven levert dezelfde vraag niets meer op.
    assert kleiner.resolve_network_node(compartiment, NETWERKWORTELS) is None
    assert voorbeeld.resolve_network_node(compartiment, NETWERKWORTELS) == put


def test_de_tekenrichting_is_zonder_dataset_te_bepalen() -> None:
    """Twee putten, een lijn die de verkeerde kant op getekend is; verder niets nodig.

    De administratie zegt A -> B, de lijn begint bij B. `omgekeerd` hoort `True` te zijn
    en de twee putten komen er in administratieve volgorde uit -- dat is wat TOP-020 en
    de richtingspijlen op de kaart lezen.
    """
    a, b = _knoop(f"{TOETS}A", "Put"), _knoop(f"{TOETS}B", "Put")
    nodes = {
        f"{TOETS}A": replace(a, point=Point(0.0, 0.0)),
        f"{TOETS}B": replace(b, point=Point(10.0, 0.0)),
    }
    streng = Conduit(
        uri=f"{TOETS}L1",
        label="1",
        types=frozenset({"Leiding"}),
        line=LineString([(10.0, 0.0), (0.0, 0.0)]),
        start_node=f"{TOETS}A",
        end_node=f"{TOETS}B",
    )

    uitslag = netwerk.richting_van_geometrie(streng, ["Put"], nodes, _is_a(nodes), {})

    assert uitslag is not None
    omgekeerd, begin, eind = uitslag
    assert omgekeerd is True
    assert (begin.uri, eind.uri) == (f"{TOETS}A", f"{TOETS}B")
    # En met de lijn de goede kant op is er niets aan de hand.
    juist = replace(streng, line=LineString([(0.0, 0.0), (10.0, 0.0)]))
    goed = netwerk.richting_van_geometrie(juist, ["Put"], nodes, _is_a(nodes), {})
    assert goed is not None and goed[0] is False


def test_de_vrije_tekenrichting_geeft_hetzelfde_als_de_methode(voorbeeld: GwswDataset) -> None:
    """Gelijkwaardigheid op de omgekeerd getekende fixture en op elke streng van de export.

    De voorbeeldexport levert er de `None`-gevallen bij -- een streng zonder lijn, en de
    onderdeelverbinding waarvan begin en eind op dezelfde put uitkomen -- zodat de
    vergelijking niet alleen over de geslaagde tak loopt.
    """
    omgekeerd = load_dataset(TTL_DIR / "top020_omgekeerd_getekend.ttl", ontology_paths=[])
    uitslagen = []
    for dataset in (omgekeerd, voorbeeld):
        for conduit in dataset.conduits.values():
            vrij = netwerk.richting_van_geometrie(
                conduit, NETWERKWORTELS, dataset.nodes, dataset.is_a, {}
            )
            uitslag = dataset.richting_van_geometrie(conduit, NETWERKWORTELS)
            assert vrij == uitslag, conduit.uri
            uitslagen.append(uitslag)

    # Voorwaarde: de twee soorten uitkomst komen allebei voor in deze vergelijking.
    assert any(uitslag is not None for uitslag in uitslagen)
    assert any(uitslag is None for uitslag in uitslagen)


def test_de_tekenrichting_zwijgt_waar_er_niets_te_vergelijken_valt() -> None:
    """De vier redenen om `None` te geven, elk apart -- en zonder een TTL te schrijven.

    Vier takken die tot issue #27 alleen via een export te bereiken waren, en waarvoor er
    geen fixture bestond: een streng zonder lijn, met een lege lijn, met een geometrie die
    geen lijn is (een `gml:Point` in de leidinggeometrie; zie TOP-016), en een streng
    waarvan een van de koppelingen niet op een knoop met een punt uitkomt. Geen van vier
    is een fout -- er valt alleen niets te zeggen -- en dat verschil is precies waar
    TOP-020 en de richtingspijlen op leunen.
    """
    nodes = {f"{TOETS}A": replace(_knoop(f"{TOETS}A", "Put"), point=Point(0.0, 0.0))}
    streng = Conduit(
        uri=f"{TOETS}L1",
        label="1",
        types=frozenset({"Leiding"}),
        line=LineString([(0.0, 0.0), (10.0, 0.0)]),
        start_node=f"{TOETS}A",
        end_node=f"{TOETS}B",
    )

    def richting(**anders: object) -> object:
        return netwerk.richting_van_geometrie(
            replace(streng, **anders),  # type: ignore[arg-type]
            ["Put"],
            nodes,
            _is_a(nodes),
            {},
        )

    assert richting(line=None) is None
    assert richting(line=LineString()) is None
    assert richting(line=Point(0.0, 0.0)) is None
    # De eindkoppeling wijst naar iets dat geen knoop is; de beginput bestaat wel.
    assert richting() is None
