"""Tests voor het inlezen van de OroX-dataset."""

from __future__ import annotations

import ast
import gc
import inspect
import textwrap
from collections.abc import Iterator
from pathlib import Path

import pytest
from rdflib import RDF, URIRef
from rdflib.term import Node as RdfNode

from gwsw_orox_helpers import dataset as dataset_module
from gwsw_orox_helpers.bronnen import gebundelde_ontologie_voor
from gwsw_orox_helpers.dataset import (
    GWSW,
    GwswDataset,
    aspects_of,
    lees_ontologie,
    load_dataset,
    parts_of,
)
from gwsw_orox_helpers.errors import DatasetError
from gwsw_orox_helpers.graaf import GraafIndex

TOETS = "http://example.org/toets#"
NETWERKWORTELS = ["Put", "Gemaal", "Lozingspunt"]
TTL_DIR = Path(__file__).parent / "fixtures" / "ttl"


def test_voorbeeld_levert_strengen_en_knooppunten(voorbeeld: GwswDataset) -> None:
    # Twee leidingen plus een onderdeelverbinding (de doorlaat tussen put B en haar
    # compartiment); het GWSW rekent beide tot de verbindingen van het netwerk. De
    # ongelijkheid is de assert: de lader neemt elke orientatie uit de
    # `Verbinding`-afsluiting als streng, niet alleen `Leidingorientatie`.
    assert len(voorbeeld.conduits) == 3
    assert len(voorbeeld.of_class("VrijvervalRioolleiding")) == 2
    # Vier knopen: twee putten, een gemaal en een compartiment. Alleen de eerste twee
    # zijn een `Put`; het gemaal en het compartiment hangen elders in de hierarchie.
    assert len(voorbeeld.nodes) == 4
    assert len(voorbeeld.of_class("Put")) == 2
    assert voorbeeld.of_class("Gemaal") == [f"{TOETS}Gem"]


def test_koppeling_loopt_via_de_putorientatie(voorbeeld: GwswDataset) -> None:
    streng = voorbeeld.conduits[f"{TOETS}L1"]

    assert streng.label == "1"
    assert streng.start_node == f"{TOETS}PutA"
    assert streng.end_node == f"{TOETS}PutB"
    assert streng.bob_start == 8.60
    assert streng.line is not None


def test_meervoudig_rdf_type(voorbeeld: GwswDataset) -> None:
    put = voorbeeld.nodes[f"{TOETS}PutA"]

    # De put is zowel Inspectieput als VerdektePut.
    assert f"{GWSW}Inspectieput" in put.types
    assert f"{GWSW}VerdektePut" in put.types


def test_klassenhierarchie_uit_de_ontologie(voorbeeld: GwswDataset) -> None:
    assert voorbeeld.is_a(f"{TOETS}L1", "VrijvervalRioolleiding")
    assert voorbeeld.is_a(f"{TOETS}PutA", "Put")
    assert not voorbeeld.is_a(f"{TOETS}L1", "Put")


def test_types_of_bouwt_de_typen_van_een_knoop_maar_een_keer(voorbeeld: GwswDataset) -> None:
    """De typen van een knoop zijn een unie; die hoort niet per aanroep te ontstaan.

    `is_a` is het warmste predicaat van de checkfase -- ruim een miljoen aanroepen per
    nlriochecker-run via `klim_naar_knoop` en `of_class` -- en elke aanroep liep hier
    langs `node.types | node.orientation_types`. Die unie is per definitie steeds
    dezelfde: knopen en strengen wijzigen na het laden niet meer. De tweede aanroep
    hoort dus hetzelfde object terug te geven en niet een verse kopie (issue #12).
    """
    uri = f"{TOETS}PutA"
    node = voorbeeld.nodes[uri]

    eerste = voorbeeld.types_of(uri)

    assert eerste == node.types | node.orientation_types
    assert voorbeeld.types_of(uri) is eerste


def test_de_typenmemo_gaat_niet_mee_naar_een_uitgedunde_dataset(voorbeeld: GwswDataset) -> None:
    """Een `replace()`-afgeleide krijgt een eigen memo, net als bij `_resolved_nodes`.

    `subset()` maakt een dataset met minder knopen. Deelde zij de memo van haar
    herkomst, dan zou zij typen blijven melden voor een knoop die zij niet meer heeft --
    en dat is precies het antwoord waarop `of_class` en `klim_naar_knoop` selecteren.
    """
    uri = f"{TOETS}PutA"
    assert voorbeeld.types_of(uri), "voorwaarde: de put draagt typen en vult dus de memo"

    kleiner = voorbeeld.subset([ander for ander in voorbeeld.nodes if ander != uri])

    assert uri not in kleiner.nodes
    assert kleiner.types_of(uri) == frozenset()
    # En andersom: de volle dataset houdt haar eigen antwoord.
    assert voorbeeld.types_of(uri)


def test_closure_bouwt_de_terugval_alleen_waar_de_hierarchie_hem_niet_kent(
    voorbeeld: GwswDataset, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Op een treffer hoort er geen wegwerp-URI en geen wegwerp-afsluiting te ontstaan.

    `closure` loopt via `klassen._afsluiting`, en die bouwde zijn terugval als eager
    default van `dict.get`: ook op de treffer, en met een tweede `_uri`-aanroep erbij.
    `is_a` vraagt hem ruim een miljoen keer per run (issue #12). Het gedrag blijft aan
    beide kanten wat het was -- de afsluiting op een treffer, de wortel zelf waar de
    hierarchie hem niet kent -- en dat is wat de tweede helft van elk blok vastlegt.
    """
    from gwsw_orox_helpers import klassen as klassen_module

    aanroepen: list[str] = []
    echte_uri = klassen_module._uri

    def geteld(naam: str) -> str:
        aanroepen.append(naam)
        return echte_uri(naam)

    monkeypatch.setattr(klassen_module, "_uri", geteld)

    gesloten = voorbeeld.closure("Put")

    assert aanroepen == ["Put"]
    assert f"{GWSW}Inspectieput" in gesloten

    aanroepen.clear()
    onbekend = voorbeeld.closure("KlasseDieNietBestaat")

    assert aanroepen == ["KlasseDieNietBestaat"]
    assert onbekend == frozenset({f"{GWSW}KlasseDieNietBestaat"})


def test_koppeling_aan_compartiment_wordt_naar_de_put_herleid(voorbeeld: GwswDataset) -> None:
    # Streng "2" koppelt aan een compartiment, niet aan de put zelf.
    streng = voorbeeld.conduits[f"{TOETS}L2"]

    assert streng.start_node == f"{TOETS}PutB_c1"
    assert voorbeeld.resolve_network_node(streng.start_node, NETWERKWORTELS) == f"{TOETS}PutB"


def test_koppeling_aan_een_compartiment_zonder_geometrie(voorbeeld: GwswDataset) -> None:
    """Een knooppunt hoeft geen puntgeometrie te hebben om een knoop te zijn.

    Streng "2" koppelt aan een compartiment waarvan de orientatie geen Punt draagt.
    Wie knopen aan hun geometrie herkent, mist die koppeling.
    """
    streng = voorbeeld.conduits[f"{TOETS}L2"]

    assert streng.start_node == f"{TOETS}PutB_c1"
    assert voorbeeld.nodes[streng.start_node].point is None


def test_onleesbaar_bestand_geeft_dataseterror(tmp_path: Path) -> None:
    with pytest.raises(DatasetError, match="kan niet gelezen worden"):
        load_dataset(tmp_path / "bestaat_niet.ttl", ontology_paths=[])


def test_ongeldige_turtle_geeft_dataseterror(tmp_path: Path) -> None:
    stuk = tmp_path / "stuk.ttl"
    stuk.write_text("dit is <geen geldige turtle", encoding="utf-8")

    with pytest.raises(DatasetError, match="geldige Turtle"):
        load_dataset(stuk, ontology_paths=[])


def test_dataset_zonder_objecten_geeft_dataseterror(tmp_path: Path) -> None:
    leeg = tmp_path / "leeg.ttl"
    leeg.write_text("@prefix ex: <http://example.org/> .\nex:a ex:b ex:c .\n", encoding="utf-8")

    with pytest.raises(DatasetError, match="geen knooppunten of strengen"):
        load_dataset(leeg, ontology_paths=[])


def _kapotte_geometrie(tmp_path: Path) -> Path:
    """Een kopie van `top001_losliggende_put.ttl` met twee onleesbare GML-literalen.

    Twee soorten kapot tegelijk, want `inlezen._geometry` vangt ze op een plek af: een
    niet-numerieke coordinaat (een `GeometryError` uit de lezer zelf) op put C, en een
    lijn met een enkel punt (waar GEOS struikelt en de lezer de `ShapelyError` omzet) op
    streng 1. Gedeeld door de twee tests hieronder die zo'n dataset nodig hebben; hij
    staat niet in de generator omdat een gecommitte fixture met kapotte geometrie ook
    elke andere test zou bereiken die over de fixturemap loopt.
    """
    bron = (TTL_DIR / "top001_losliggende_put.ttl").read_text(encoding="utf-8")
    bron = bron.replace("1000.0 2000.0 1050.0 2000.0", "1000.0 2000.0")
    bron = bron.replace("1200.0 2500.0", "een twee")
    pad = tmp_path / "kapotte_geometrie.ttl"
    pad.write_text(bron, encoding="utf-8")
    return pad


def test_een_onleesbare_gml_literaal_belandt_in_geometry_errors(tmp_path: Path) -> None:
    """Een kapotte geometrie breekt de lezing niet af; ze wordt op het object gemeld.

    Twee soorten kapot tegelijk (zie `_kapotte_geometrie`). Allebei de objecten blijven
    bestaan, zonder geometrie en zonder z -- dat is het bedoelde gedrag en het is de
    reden dat `geometry_errors` bestaat. Sinds issue #36 is de sleutel de knoop- of
    streng-URI en niet meer die van de orientatie.
    """
    gelezen = load_dataset(_kapotte_geometrie(tmp_path), ontology_paths=[])

    assert set(gelezen.geometry_errors) == {f"{TOETS}PutC", f"{TOETS}L1"}
    assert "niet-numerieke coordinaat" in gelezen.geometry_errors[f"{TOETS}PutC"]
    assert "onbruikbare LineString-geometrie" in gelezen.geometry_errors[f"{TOETS}L1"]
    assert gelezen.nodes[f"{TOETS}PutC"].point is None
    assert gelezen.nodes[f"{TOETS}PutC"].z is None
    assert gelezen.conduits[f"{TOETS}L1"].line is None
    assert gelezen.conduits[f"{TOETS}L1"].z_values == ()
    # De rest van de export komt gewoon binnen; een onleesbaar object is geen
    # afgebroken lezing.
    assert gelezen.nodes[f"{TOETS}PutA"].point is not None


_GML_PRELUDE = (
    "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n"
    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
    "@prefix geo: <http://www.opengis.net/ont/geosparql#> .\n"
    "@prefix gwsw: <http://data.gwsw.nl/1.6/totaal/> .\n"
    "@prefix : <http://example.org/toets#> .\n\n"
    "gwsw:Putorientatie rdfs:subClassOf gwsw:Knooppunt .\n"
    "gwsw:Leidingorientatie rdfs:subClassOf gwsw:Verbinding .\n\n"
)


def _punt_aspect(coordinaten: str) -> str:
    """Een `Punt`-aspect met deze coordinatentekst (`"een twee"` is onleesbaar)."""
    return (
        "[ rdf:type gwsw:Punt ; gwsw:hasValue "
        '"<gml:Point xmlns:gml=\\"http://www.opengis.net/gml\\">'
        f'<gml:pos>{coordinaten}</gml:pos></gml:Point>"^^geo:gmlLiteral ]'
    )


def _put_met_leesbare_en_kapotte_orientatie(tmp_path: Path, *, leesbaar_eerst: bool) -> Path:
    """Een put met twee Putorientaties: een met een leesbaar Punt en een met een kapot.

    De schrijfvolgorde van de twee orientatieblokken bepaalt welke de lezer het eerst
    verwerkt -- de graafindex bewaart de stroomvolgorde -- zodat dezelfde put beide
    kanten kan toetsen: eerst leesbaar dan kapot, en omgekeerd.
    """
    put = (
        ':PutX rdf:type gwsw:Inspectieput ; rdfs:label "X" ;\n'
        "    gwsw:hasAspect :PutX_oriL , :PutX_oriK .\n\n"
    )
    leesbaar = (
        ":PutX_oriL rdf:type gwsw:Putorientatie ;\n"
        f"    gwsw:hasAspect {_punt_aspect('1000.0 2000.0')} .\n\n"
    )
    kapot = (
        ":PutX_oriK rdf:type gwsw:Putorientatie ;\n"
        f"    gwsw:hasAspect {_punt_aspect('een twee')} .\n"
    )
    blokken = (leesbaar, kapot) if leesbaar_eerst else (kapot, leesbaar)
    naam = "leesbaar_eerst" if leesbaar_eerst else "kapot_eerst"
    pad = tmp_path / f"twee_orientaties_{naam}.ttl"
    pad.write_text(_GML_PRELUDE + put + "".join(blokken), encoding="utf-8")
    return pad


def test_een_object_met_een_leesbare_en_een_kapotte_orientatie_houdt_beide(
    tmp_path: Path,
) -> None:
    """Invariant: het object staat in `geometry_errors` zodra één orientatie kapot was.

    Ook als het daarnaast een bruikbare geometrie heeft. De melding landt vóór de
    ontdubbelingsbewaker in de lezer, dus een put die via een leesbare orientatie al
    gebouwd is, houdt de fout van zijn tweede, kapotte orientatie (issue #36).
    """
    gelezen = load_dataset(
        _put_met_leesbare_en_kapotte_orientatie(tmp_path, leesbaar_eerst=True),
        ontology_paths=[],
    )

    put = gelezen.nodes[f"{TOETS}PutX"]
    assert put.point is not None  # de eerst verwerkte, leesbare orientatie gaf een punt
    assert f"{TOETS}PutX" in gelezen.geometry_errors


def test_geometry_errors_hangt_niet_af_van_de_orientatievolgorde(tmp_path: Path) -> None:
    """Order-onafhankelijkheid: welke orientatie eerst komt verandert de sleutels niet.

    Dezelfde put, met de leesbare en de kapotte orientatie in omgekeerde schrijfvolgorde.
    Het object staat beide keren in `geometry_errors` -- de melding hangt aan het object
    en niet aan de volgorde waarin de orientaties langskomen (issue #36).
    """
    leesbaar_eerst = load_dataset(
        _put_met_leesbare_en_kapotte_orientatie(tmp_path, leesbaar_eerst=True),
        ontology_paths=[],
    )
    kapot_eerst = load_dataset(
        _put_met_leesbare_en_kapotte_orientatie(tmp_path, leesbaar_eerst=False),
        ontology_paths=[],
    )

    assert set(leesbaar_eerst.geometry_errors) == {f"{TOETS}PutX"}
    assert set(kapot_eerst.geometry_errors) == {f"{TOETS}PutX"}


def test_een_wees_orientatie_valt_terug_op_de_orientatie_uri(tmp_path: Path) -> None:
    """Een kapotte orientatie zonder enkele houder sleutelt op de orientatie-URI (issue #36).

    Zonder die terugval zou de melding stil verdwijnen -- en stil verdwijnen is precies
    wat deze bevinding aanklaagt. Zowel een put- als een leidingorientatie zonder houder
    komt zo in `geometry_errors`; zo'n wees zit per definitie in geen enkele subset.
    """
    bron = _GML_PRELUDE + (
        # Een gewone, leesbare put, zodat de dataset knopen heeft.
        ':PutA rdf:type gwsw:Inspectieput ; rdfs:label "A" ;\n'
        "    gwsw:hasAspect :PutA_ori .\n:PutA_ori rdf:type gwsw:Putorientatie ;\n"
        f"    gwsw:hasAspect {_punt_aspect('1000.0 2000.0')} .\n\n"
        # Een wees-putorientatie: kapot Punt, door geen enkel object gedragen.
        ":LosPutOri rdf:type gwsw:Putorientatie ;\n"
        f"    gwsw:hasAspect {_punt_aspect('een twee')} .\n\n"
        # Een wees-leidingorientatie: een onbruikbare lijn (een enkel punt), zonder houder.
        ":LosLeidingOri rdf:type gwsw:Leidingorientatie ;\n"
        "    gwsw:hasAspect [ rdf:type gwsw:Lijn ; gwsw:hasValue "
        '"<gml:LineString xmlns:gml=\\"http://www.opengis.net/gml\\">'
        '<gml:posList srsDimension=\\"2\\">1000.0 2000.0</gml:posList>'
        '</gml:LineString>"^^geo:gmlLiteral ] .\n'
    )
    pad = tmp_path / "wees_orientatie.ttl"
    pad.write_text(bron, encoding="utf-8")

    gelezen = load_dataset(pad, ontology_paths=[])

    assert f"{TOETS}LosPutOri" in gelezen.geometry_errors
    assert "niet-numerieke coordinaat" in gelezen.geometry_errors[f"{TOETS}LosPutOri"]
    assert f"{TOETS}LosLeidingOri" in gelezen.geometry_errors
    assert "onbruikbare LineString-geometrie" in gelezen.geometry_errors[f"{TOETS}LosLeidingOri"]
    # Een wees zit in geen enkele subset, ook niet in "alles behouden".
    alles = gelezen.subset([*gelezen.nodes, *gelezen.conduits])
    assert f"{TOETS}LosPutOri" not in alles.geometry_errors
    assert f"{TOETS}LosLeidingOri" not in alles.geometry_errors


def test_hasconnection_is_symmetrisch(tmp_path: Path) -> None:
    """gwsw:hasConnection is een owl:SymmetricProperty en heeft geen inverse.

    Een export die de tripel omgekeerd schrijft is even geldig; de lader moet
    beide richtingen herkennen.
    """
    bron = (Path(__file__).parent / "fixtures" / "ttl" / "schoon.ttl").read_text(encoding="utf-8")
    omgekeerd = bron.replace(
        ":L1_b gwsw:hasConnection :PutA_ori .", ":PutA_ori gwsw:hasConnection :L1_b ."
    )
    assert omgekeerd != bron, "de fixture bevat de verwachte koppeling niet"
    pad = tmp_path / "omgekeerd.ttl"
    pad.write_text(omgekeerd, encoding="utf-8")

    dataset = load_dataset(pad, ontology_paths=[])
    streng = next(iter(dataset.conduits.values()))

    assert streng.start_node is not None
    assert streng.start_node.endswith("PutA")


def test_orientatietypen_zijn_selecteerbaar(tmp_path: Path) -> None:
    """Knooppunt-klassen als Lozingspunt staan op de orientatie, niet op het object."""
    bron = (Path(__file__).parent / "fixtures" / "ttl" / "schoon.ttl").read_text(encoding="utf-8")
    bron += "\n:PutB_ori rdf:type gwsw:Lozingspunt .\n"
    pad = tmp_path / "lozingspunt.ttl"
    pad.write_text(bron, encoding="utf-8")

    dataset = load_dataset(pad, ontology_paths=[])
    lozingspunten = dataset.of_class("Lozingspunt")

    assert [uri.rsplit("#", 1)[-1] for uri in lozingspunten] == ["PutB"]


def test_onderdeel_uit_de_graaf_is_op_klasse_te_herkennen() -> None:
    """Een overstortdrempel hangt via hasPart aan de put en wordt nooit een knoop.

    `types_of()` kent alleen knopen en strengen en geeft er dus niets op terug;
    `graph_types_of()` leest het type uit de graaf en maakt de klasse toetsbaar.
    """
    dataset = load_dataset(TTL_DIR / "adm007_overstort_met_drempel.ttl", ontology_paths=[])
    drempel = next(str(s) for s in dataset.subjects_of_class("Overstortdrempel"))

    assert dataset.types_of(drempel) == frozenset()
    assert not dataset.is_a(drempel, "Overstortdrempel")
    assert dataset.graph_is_a(drempel, "Overstortdrempel")


def _wegwerptermen(functie: object) -> list[str]:
    """De termconstructies die deze functie per aanroep uitvoert, als leesbare namen.

    Twee vormen tellen mee en allebei kosten ze een microseconde per keer: een
    `URIRef(...)`-aanroep (rdflib valideert de tekst dan met een reguliere expressie over
    de hele IRI) en een attribuutlezing op een `DefinedNamespace` als `RDF.type` (dat is
    geen attribuut maar een `__getattr__`). Aan de boom en niet aan de tekst: een
    docstring die `URIRef(` noemt is geen aanroep, en een aanroep die over twee regels
    staat mist een regelgerichte grep. De aanroep telt in beide schrijfwijzen --
    `URIRef(x)` en `rdflib.URIRef(x)` -- want een import die van vorm verandert hoort de
    bewaker niet blind te maken.
    """
    boom = ast.parse(textwrap.dedent(inspect.getsource(functie)))  # type: ignore[arg-type]
    naamruimten = {"RDF", "RDFS", "OWL", "XSD"}
    gevonden: list[str] = []
    for knoop in ast.walk(boom):
        if isinstance(knoop, ast.Call):
            naam = knoop.func
            if (isinstance(naam, ast.Name) and naam.id == "URIRef") or (
                isinstance(naam, ast.Attribute) and naam.attr == "URIRef"
            ):
                gevonden.append("URIRef(...)")
        elif isinstance(knoop, ast.Attribute) and isinstance(knoop.value, ast.Name):
            if knoop.value.id in naamruimten:
                gevonden.append(f"{knoop.value.id}.{knoop.attr}")
    return sorted(gevonden)


def test_de_hete_lezers_bouwen_hun_termen_niet_per_aanroep() -> None:
    """De opvraaglezers krijgen hun termen kant-en-klaar (issue #23).

    Alle drie bouwden ze per aanroep een term uit tekst die al een geldige graafsleutel
    is: `graph_types_of` en `subjects_of_class` een `URIRef` mét rdflib's validatieregex
    plus een `RDF.type`-lezing op de `DefinedNamespace`, en `_deksel_kenmerk` dezelfde
    handvol dekselklassen opnieuw per put én per onderdeel. Het snelpad
    (`graaf._uriref_snel`) en de eenmalige omzetting in `_read_nodes` leveren dezelfde
    termen -- `tests/test_graaf.py` telt die gelijkheid over de hele gebundelde ontologie
    -- dus wat hier vastligt is dat ze niet stilletjes terugkomen.

    Dit is de vorm-helft van het bewijs. Dat de dekseltermen ook werkelijk **buiten** de
    knopenlus gebouwd worden, is aan de vorm van `_deksel_kenmerk` niet te zien; dat telt
    de test hieronder.
    """
    from gwsw_orox_helpers.inlezen import _deksel_kenmerk

    assert _wegwerptermen(GwswDataset.graph_types_of) == []
    assert _wegwerptermen(GwswDataset.subjects_of_class) == []
    assert _wegwerptermen(_deksel_kenmerk) == []


def test_de_dekseltermen_worden_een_keer_gebouwd_en_niet_per_put(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """De omzetting hoort buiten de knopenlus te staan, en dat is te tellen.

    De winst van issue #23 aan deze kant zit niet in `_deksel_kenmerk` zelf maar in de
    plek van de omzetting: `_read_nodes` bouwt de dekselklassen een keer als
    `frozenset[URIRef]` en geeft ze door. Zet iemand die `frozenset(...)` terug ín de lus
    over de knopen, dan blijft de vormbewaker hierboven groen terwijl de regressie
    compleet is -- vandaar deze telling. Ze staat op `inlezen._uriref_snel`, precies de
    naam die de lus zou herhalen.
    """
    from gwsw_orox_helpers import inlezen as inlezen_module

    aanroepen: list[str] = []
    echte = inlezen_module._uriref_snel

    def geteld(waarde: str) -> URIRef:
        aanroepen.append(waarde)
        return echte(waarde)

    monkeypatch.setattr(inlezen_module, "_uriref_snel", geteld)

    dataset = load_dataset(TTL_DIR / "dataset_voorbeeld.ttl")

    assert dataset.nodes, "voorwaarde: er zijn knopen, dus de lus draaide"
    # Precies de dekselafsluiting, elk lid een keer -- niet een veelvoud van het aantal
    # putten. `_read_nodes` is de enige plek in de leeslaag die deze naam aanroept.
    dekselklassen = dataset.closure("Putdeksel")
    assert sorted(aanroepen) == sorted(dekselklassen)


def test_uniek_ontdubbelt_op_het_eerste_voorkomen() -> None:
    """De gedeelde ontdubbelaar van de drie orientatiebronnen (issue #30).

    `_orientations_of_class`, `_orientations_with` en `_leiding_orientations` hielden
    elk hun eigen gezien-set aan; dit is die set, een keer. Vastgelegd wordt waar die
    drie op leunen: elk element hoogstens een keer, in de volgorde waarin het voor het
    eerst langskwam, een lege bron levert niets op -- en de ontdubbelaar blijft lui. Dat
    laatste is geen detail: een eager variant (`dict.fromkeys`) geeft dezelfde lijst
    terug maar leest op een gemeentebrede export eerst de hele bron in.
    """
    from gwsw_orox_helpers.inlezen import _uniek

    assert list(_uniek([])) == []
    assert list(_uniek([3, 1, 3, 2, 1, 3])) == [3, 1, 2]
    assert list(_uniek(iter(("a", "a", "a")))) == ["a"]

    gelezen: list[int] = []

    def bron() -> Iterator[int]:
        for waarde in (1, 1, 2, 3):
            gelezen.append(waarde)
            yield waarde

    geleverd: list[int] = []
    for waarde in _uniek(bron()):
        geleverd.append(waarde)
        if len(geleverd) == 2:
            break

    assert geleverd == [1, 2]
    assert gelezen == [1, 1, 2], "de 3 is niet opgehaald: de bron loopt niet vooruit"


def test_orientations_of_class_ordent_op_klassenaam_ongeacht_invoervolgorde() -> None:
    """De orientatievolgorde is de alfabetische van de klassenaam, niet de hashvolgorde (issue #37).

    `_orientations_of_class` liep over een `frozenset[str]`, en de iteratievolgorde daarvan
    is per proces gerandomiseerd (`PYTHONHASHSEED`). Draagt één object twee orientaties van
    verschillende Knooppunt-subklassen, dan bepaalt die volgorde welke orientatie in
    `_read_nodes` de eerste is en dus de geometrie levert -- waardoor `node.point` (en sinds
    issue #36 `geometry_errors`) tussen twee runs op hetzelfde bestand kan verschillen.
    `sorted(klassen)` maakt de uitkomst reproduceerbaar: de alfabetische van de klassenaam.

    De invoer wordt hier als lijst en in niet-alfabetische volgorde aangeboden. Een
    `frozenset` zou zijn eigen, onvoorspelbare volgorde opleggen en de assert per seed laten
    wisselen; met een geordende invoer ligt vast wat de functie ermee doet -- zij laat die
    volgorde niet door maar legt haar eigen, alfabetische volgorde op.
    """
    from gwsw_orox_helpers.inlezen import _orientations_of_class

    graph = GraafIndex()
    ori_alfa = URIRef(f"{TOETS}ori_alfa")
    ori_beta = URIRef(f"{TOETS}ori_beta")
    ori_gamma = URIRef(f"{TOETS}ori_gamma")
    klasse_alfa = f"{GWSW}Knoop_Alfa"
    klasse_beta = f"{GWSW}Knoop_Beta"
    klasse_gamma = f"{GWSW}Knoop_Gamma"
    graph.voeg_toe(ori_alfa, RDF.type, URIRef(klasse_alfa))
    graph.voeg_toe(ori_beta, RDF.type, URIRef(klasse_beta))
    graph.voeg_toe(ori_gamma, RDF.type, URIRef(klasse_gamma))

    resultaat = list(_orientations_of_class(graph, [klasse_gamma, klasse_alfa, klasse_beta]))

    assert resultaat == [ori_alfa, ori_beta, ori_gamma]


def test_graph_types_of_geeft_dezelfde_typen_als_de_urirefweg(voorbeeld: GwswDataset) -> None:
    """Het snelpad verandert het antwoord niet, voor geen enkel subject in de export.

    De tegenhanger van de guard hierboven: die zegt dat de termen niet meer per aanroep
    gebouwd worden, deze zegt dat het antwoord daar niet van verandert. De vergelijking
    loopt over de knopen, de strengen én de onderdelen die alleen in de graaf staan (een
    overstortdrempel wordt nooit een knoop), plus twee teksten die nergens in de graaf
    voorkomen -- de misser hoort net zo goed leeg te blijven.
    """

    def via_uriref(uri: str) -> frozenset[str]:
        uit_graaf = {str(soort) for soort in voorbeeld.graph.objects(URIRef(uri), RDF.type)}
        return voorbeeld.types_of(uri) | uit_graaf

    onderdelen = [deel for uri in voorbeeld.nodes for deel in voorbeeld.onderdelen(uri)]
    uris = [*voorbeeld.nodes, *voorbeeld.conduits, *onderdelen, f"{TOETS}BestaatNiet", ""]

    assert uris, "voorwaarde: er valt iets te vergelijken"
    for uri in uris:
        assert voorbeeld.graph_types_of(uri) == via_uriref(uri), uri


def test_is_a_geeft_hetzelfde_antwoord_als_de_doorsnedevraag(voorbeeld: GwswDataset) -> None:
    """`isdisjoint` in plaats van een doorsnede bouwen; het oordeel blijft hetzelfde.

    `bool(typen & afsluiting)` bouwde per aanroep een wegwerp-verzameling om er daarna
    alleen de leegheid van te vragen. `not typen.isdisjoint(afsluiting)` beantwoordt
    dezelfde vraag zonder die verzameling (issue #12, doorgevoerd bij #23). Wat hier
    vastligt is dat de twee op elke combinatie hetzelfde zeggen -- inclusief de lege
    typenverzameling (een URI die geen knoop en geen streng is) en een wortel die de
    hierarchie niet kent, waar de afsluiting op de wortel zelf blijft steken.
    """
    wortels = ["Put", "Leiding", "Knooppunt", "Overstortdrempel", "Stelsel", "KlasseZonderBestaan"]
    uris = [*voorbeeld.nodes, *voorbeeld.conduits, f"{TOETS}BestaatNiet"]

    for uri in uris:
        typen = voorbeeld.types_of(uri)
        for wortel in wortels:
            assert voorbeeld.is_a(uri, wortel) == bool(typen & voorbeeld.closure(wortel)), (
                uri,
                wortel,
            )


def test_onderdelen_vindt_de_delen_van_een_put() -> None:
    """`onderdelen` loopt hasPart neerwaarts en filtert desgewenst op een wortelklasse."""
    dataset = load_dataset(TTL_DIR / "adm007_overstort_met_drempel.ttl", ontology_paths=[])
    put = "http://example.org/toets#PutO"

    assert dataset.onderdelen(put) == ["http://example.org/toets#DrempelO"]
    assert dataset.onderdelen(put, "Overstortdrempel") == ["http://example.org/toets#DrempelO"]
    assert dataset.onderdelen(put, "Compartiment") == []
    # De volgorde is de graafvolgorde van `parts_of`, zonder sortering.
    orientatie = "http://example.org/toets#L1_ori"
    assert dataset.onderdelen(orientatie) == [
        str(deel) for deel in parts_of(dataset.graph, URIRef(orientatie))
    ]


def test_onderdeel_label_leest_het_label_van_een_willekeurig_subject() -> None:
    """Ook een onderdeel dat geen knoop of streng is heeft zo een leesbaar label."""
    dataset = load_dataset(TTL_DIR / "adm007_overstort_met_drempel.ttl", ontology_paths=[])

    assert dataset.onderdeel_label("http://example.org/toets#DrempelO") == "DrempelO"
    assert dataset.onderdeel_label("http://example.org/toets#L1_b") is None


def test_onderdeel_aspecten_geeft_dezelfde_kenmerken_als_de_private_lezing() -> None:
    """De publieke aspectlezing is exact de private `_read_aspects` op de graaf."""
    from gwsw_orox_helpers.dataset import _read_aspects

    dataset = load_dataset(TTL_DIR / "adm007_overstort_met_drempel.ttl", ontology_paths=[])
    drempel = "http://example.org/toets#DrempelO"

    aspecten = dataset.onderdeel_aspecten(drempel)
    assert aspecten == list(_read_aspects(dataset.graph, URIRef(drempel)))
    assert {(aspect.kind, aspect.number) for aspect in aspecten} == {
        ("Drempelniveau", 9.0),
        ("Drempelbreedte", 2000.0),
    }


def test_onderdeel_lezers_vinden_ook_een_bnode_onderdeel(tmp_path: Path) -> None:
    """Een anoniem (`[ ... ]`) onderdeel houdt zijn label en kenmerken.

    De `onderdeel_*`-lezers krijgen hun subject als tekst; voor een BNode-onderdeel
    verloor de vaste `URIRef(uri)`-omweg dan het label en de kenmerken (bevinding uit
    de Taak 3-review van issue #26). `_subject_term` herstelt dat: staat de tekst niet
    als URIRef in de graaf, dan telt de gelijknamige BNode.
    """
    bron = (TTL_DIR / "adm007_overstort_met_drempel.ttl").read_text(encoding="utf-8")
    bron += (
        "\n:PutO gwsw:hasPart [ rdf:type gwsw:Overstortdrempel ;"
        ' rdfs:label "AnoniemeDrempel" ;'
        ' gwsw:hasAspect [ rdf:type gwsw:Drempelniveau ; gwsw:hasValue "8.5" ] ] .\n'
    )
    pad = tmp_path / "bnode_onderdeel.ttl"
    pad.write_text(bron, encoding="utf-8")

    dataset = load_dataset(pad, ontology_paths=[])
    put = "http://example.org/toets#PutO"
    bnode = next((deel for deel in dataset.onderdelen(put) if not deel.startswith("http")), None)

    assert bnode is not None, "de fixture hoort een BNode-onderdeel aan de put te hangen"
    assert dataset.onderdeel_label(bnode) == "AnoniemeDrempel"
    assert {(a.kind, a.number) for a in dataset.onderdeel_aspecten(bnode)} == {
        ("Drempelniveau", 8.5)
    }


def test_of_class_weigert_een_verbindingsklasse(voorbeeld: GwswDataset) -> None:
    """Een verbindingsklasse als rol levert stil nul op; dat hoort een fout te zijn.

    Dit draait op de echte GWSW-afsluiting, niet op de klassenhierarchie die een
    fixture zelf declareert: `Afvoerrelatie` staat in geen enkele fixture-prelude en
    is dus alleen via de ontologie als verbindingsklasse te kennen. Een `Leiding` is
    een `FysiekObject` en blijft gewoon selecteerbaar -- de weigering is smal.
    """
    with pytest.raises(DatasetError, match="verbindingsklasse"):
        voorbeeld.of_class("Afvoerrelatie")
    with pytest.raises(DatasetError, match="verbindingsklasse"):
        voorbeeld.of_class("Leidingorientatie")

    assert voorbeeld.is_connection_class("Afvoerrelatie")
    assert not voorbeeld.is_connection_class("Leiding")
    assert voorbeeld.of_class("VrijvervalRioolleiding")


def test_dekselniveau_onder_een_subklasse_van_putdeksel() -> None:
    """Een Putdeksel_ZwaarVerkeer is een Putdeksel; zijn niveau hoort mee te komen.

    Een exacte typevergelijking zou dit deksel overslaan, waarna `bovenkant` stil op
    de maaiveldhoogte terugvalt -- geen melding, alleen een andere hoogte onder elke
    hoogtecheck. Vandaar dat hier op de bovenkant getoetst wordt en niet alleen op
    het kenmerk.
    """
    dataset = load_dataset(TTL_DIR / "dataset_zwaarverkeerdeksel.ttl", ontology_paths=[])
    put = next(node for node in dataset.nodes.values() if node.label == "B")

    assert put.maaiveld == 10.0
    assert put.dekselniveau == 9.95
    assert put.bovenkant == 9.95


@pytest.mark.parametrize(
    "fixture", ["dataset_twee_houders_put_eerst.ttl", "dataset_twee_houders_straat_eerst.ttl"]
)
def test_klimmen_langs_meer_dan_een_houder(fixture: str) -> None:
    """Het compartiment hangt onder de put en onder een straat; de put moet eruit komen.

    Beide schrijfvolgordes staan er, want rdflib levert de houders op in de volgorde
    waarin ze geschreven zijn. Volgt de wandeling een enkele houder, dan loopt zij op
    de straat dood -- die is geen knoop en heeft zelf geen houder -- en telt de
    streng ten onrechte als niet aangesloten.
    """
    dataset = load_dataset(TTL_DIR / fixture, ontology_paths=[])
    compartiment = next(uri for uri in dataset.nodes if uri.endswith("PutB_c1"))
    put = next(uri for uri in dataset.nodes if uri.endswith("#PutB"))

    assert len(dataset.nodes[compartiment].parents) == 2
    assert dataset.resolve_network_node(compartiment, NETWERKWORTELS) == put
    assert compartiment in dataset.klim_naar_knoop(compartiment, NETWERKWORTELS)[1]


def test_inverse_properties_bouwen_hetzelfde_domeinmodel() -> None:
    """Een export mag `isPartOf` en `isAspectOf` schrijven; dat is geen lege dataset.

    Het GWSW declareert ze als de inverse van `hasPart` en `hasAspect`. Wie alleen de
    voorwaartse richting leest, vindt hier nul knopen en nul strengen -- en dat is
    geen melding maar een leeg rapport dat er goed uitziet.
    """
    dataset = load_dataset(TTL_DIR / "dataset_inverse_properties.ttl", ontology_paths=[])
    streng = next(iter(dataset.conduits.values()))

    assert sorted(node.label for node in dataset.nodes.values()) == ["A", "B"]
    assert streng.line is not None
    assert dataset.nodes[streng.start_node or ""].label == "A"
    assert dataset.nodes[streng.end_node or ""].label == "B"
    assert streng.bob_start == 8.60


def test_beide_schrijfrichtingen_naast_elkaar_tellen_een_keer() -> None:
    """`hasPart` en `isPartOf` naast elkaar zeggen hetzelfde, niet twee dingen.

    Nu beide richtingen gelezen worden kan een export die ze allebei schrijft elk
    kenmerk en elk onderdeel dubbel opleveren. Dat levert nergens een melding op --
    het wordt een put met twee compartimenten die er een heeft, en een kenmerk dat
    twee keer in `aspects` staat.
    """
    dataset = load_dataset(TTL_DIR / "dataset_dubbele_schrijfrichting.ttl", ontology_paths=[])
    put = next(node for node in dataset.nodes.values() if node.label == "B")
    subject = URIRef(put.uri)

    assert [aspect.kind for aspect in put.aspects].count("Begindatum") == 1
    assert len(list(parts_of(dataset.graph, subject))) == 1
    assert len(list(aspects_of(dataset.graph, subject))) == len(
        set(aspects_of(dataset.graph, subject))
    )
    compartiment = next(uri for uri in dataset.nodes if uri.endswith("PutB_c1"))
    assert dataset.nodes[compartiment].parents == (put.uri,)


def test_beheerobjecttype_kiest_de_specifiekste_klasse() -> None:
    """Bij twee typen wint de subklasse, niet de eerste letter van het alfabet.

    `Uitlaatconstructie` is volgens de ontologie een subklasse van `Bouwwerk`; een
    alfabetische keuze zou het object "Bouwwerk" noemen en daarmee de kaartlegenda en
    de aantallentabel op de algemenere naam zetten.
    """
    dataset = load_dataset(TTL_DIR / "dataset_meervoudig_objecttype.ttl", ontology_paths=[])
    uri = next(uri for uri, node in dataset.nodes.items() if node.label == "U")

    assert {t.rsplit("/", 1)[-1] for t in dataset.nodes[uri].types} == {
        "Bouwwerk",
        "Uitlaatconstructie",
    }
    assert dataset.beheerobjecttype(uri) == "Uitlaatconstructie"


def test_beheerobjecttype_bij_onvergelijkbare_typen(voorbeeld: GwswDataset) -> None:
    """Twee typen zonder subsumptierelatie: dan beslist het alfabet, en niets anders.

    Put A is zowel `Inspectieput` (onder `Rioolput`) als `VerdektePut` (rechtstreeks
    onder `Put`). Geen van beide is een subklasse van de andere, dus de ontologie wijst
    hier geen winnaar aan en de uitkomst is de alfabetisch eerste. Deze test legt dat
    vast: welke van de twee een beheerobjecttype hoort te heten is een domeinvraag, en
    de dag dat het antwoord verandert hoort dat hier te blijken.
    """
    uri = f"{TOETS}PutA"

    assert f"{GWSW}VerdektePut" not in voorbeeld.closure("Inspectieput")
    assert f"{GWSW}Inspectieput" not in voorbeeld.closure("VerdektePut")
    assert voorbeeld.beheerobjecttype(uri) == "Inspectieput"


def test_verschil_met_de_structurele_herkenning_wordt_gemeld(voorbeeld: GwswDataset) -> None:
    """Zonder ontologie zou de lader knopen aan hun geometrie herkennen.

    Dat wijkt af van de GWSW-definitie: het compartiment van put B is wel een
    knooppunt maar heeft geen punt, en haar putdeksel heeft wel een punt maar is geen
    knooppunt. Dat verschil hoort meetbaar te zijn.
    """
    assert voorbeeld.structural_diff == {
        "knooppunten_zonder_geometrie": 1,
        "knooppunten_wel_geometrie_geen_rol": 1,
    }


def test_ontologie_wordt_vastgelegd(voorbeeld: GwswDataset) -> None:
    assert [pad.name for pad in voorbeeld.ontologies] == ["gwsw_ontologie_totaal_16.ttl"]


def test_beheerobjecttype_negeert_de_orientatie() -> None:
    """De soortnaam van een object is zijn eigen type, niet dat van zijn aspect.

    Deze regel wordt zowel door de netwerktoelichting als door de GIS-uitvoer
    gebruikt; hij hoort op een plek te staan, anders loopt hij bij de volgende
    wijziging uiteen.
    """
    dataset = load_dataset(
        Path(__file__).parent / "fixtures" / "ttl" / "net001_bouwwerk_eindknoop.ttl",
        ontology_paths=[],
    )
    uri = next(uri for uri, node in dataset.nodes.items() if node.label == "U")

    assert "Bouwwerkorientatie" in {t.rsplit("/", 1)[-1] for t in dataset.types_of(uri)}
    assert dataset.beheerobjecttype(uri) == "Uitlaatconstructie"


def test_beheerobjecttype_valt_terug_op_het_aspect() -> None:
    """Is er niets anders bekend, dan is het aspecttype beter dan niets."""
    dataset = load_dataset(
        Path(__file__).parent / "fixtures" / "ttl" / "net001_bouwwerk_eindknoop.ttl",
        ontology_paths=[],
    )

    assert dataset.beheerobjecttype("urn:bestaat-niet") == ""


def test_bob_verval_is_het_verschil_over_de_streng(voorbeeld: GwswDataset) -> None:
    conduit = next(c for c in voorbeeld.conduits.values() if c.bob_start and c.bob_end)

    assert conduit.bob_verval == pytest.approx(conduit.bob_start - conduit.bob_end)


def test_bob_verval_ontbreekt_zonder_beide_bobs(voorbeeld: GwswDataset) -> None:
    conduit = next(
        c for c in voorbeeld.conduits.values() if c.bob_start is None or c.bob_end is None
    )

    assert conduit.bob_verval is None


def test_richting_van_geometrie_ziet_een_omgekeerd_getekende_lijn() -> None:
    # De netwerkknoop-wortels zoals nlriochecker ze configureert; hier inline om de
    # package los te houden.
    wortels = [
        "Put",
        "Overnamepunt",
        "Gemaal",
        "Lozingspunt",
        "UitlaatPunt",
        "Lozingsput",
        "Uitlaatconstructie",
        "Bergbezinkbassin",
        "Bergingsbassin",
        "Bezinkbassin",
    ]

    dataset = load_dataset(TTL_DIR / "top020_omgekeerd_getekend.ttl", ontology_paths=[])
    conduit = next(iter(dataset.conduits.values()))

    uitslag = dataset.richting_van_geometrie(conduit, wortels)

    assert uitslag is not None
    omgekeerd, begin, eind = uitslag
    assert omgekeerd is True
    assert begin.uri != eind.uri


def _zonder_klassenhierarchie(bron: Path, doel: Path) -> Path:
    """Schrijft een kopie van een fixture waaruit elke subklasserelatie weg is.

    Zo ziet een handgeschreven fixture eruit als de echte OroX-export: die bevat
    nul `rdfs:subClassOf`-tripels, dus zonder ontologie weet de lader niets over
    klassen.
    """
    regels = [
        regel
        for regel in bron.read_text(encoding="utf-8").splitlines()
        if "rdfs:subClassOf" not in regel
    ]
    doel.write_text("\n".join(regels) + "\n", encoding="utf-8")
    return doel


def test_klassenhierarchie_bekend_leest_de_graaf_en_niet_de_ontologielijst(
    tmp_path: Path,
) -> None:
    """De fixture declareert haar eigen subklassen; die telt, ook zonder ontologiebestand.

    Wordt dit uit `ontologies` afgeleid, dan draagt elke fixturerun ten onrechte het
    voorbehoud dat haar uitkomst geen oordeel is -- terwijl `putten()` gewoon vult.
    """
    met = load_dataset(TTL_DIR / "top001_losliggende_put.ttl", ontology_paths=[])
    zonder = load_dataset(
        _zonder_klassenhierarchie(TTL_DIR / "top001_losliggende_put.ttl", tmp_path / "kaal.ttl"),
        ontology_paths=[],
    )

    assert met.ontologies == () and met.klassenhierarchie_bekend is True
    assert zonder.klassenhierarchie_bekend is False
    # Het gevolg waar het om gaat: de wortelklasse dekt niets meer.
    assert met.of_class("Put") and zonder.of_class("Put") == []


def _zonder_orientatiewortels(bron: Path, doel: Path) -> Path:
    """Schrijft een kopie waaruit alleen de twee orientatiewortels weg zijn.

    De tussentoestand: `Put` en `Leiding` houden hun subklassen, `Knooppunt` en
    `Verbinding` krijgen er geen. Een deel van de TTL-fixtures in deze repo staat er
    zo bij; de OroX-export zonder ontologie is nog een stap kaler.
    """
    regels = [
        regel
        for regel in bron.read_text(encoding="utf-8").splitlines()
        if "subClassOf gwsw:Knooppunt" not in regel and "subClassOf gwsw:Verbinding" not in regel
    ]
    doel.write_text("\n".join(regels) + "\n", encoding="utf-8")
    return doel


def test_de_tussentoestand_geldt_als_onbekende_klassenhierarchie(tmp_path: Path) -> None:
    """Een halve hierarchie is geen hierarchie: het predicaat volgt de terugval.

    Dit is de naad waarin de faalwijze van issue #33 overleefde. `bool(subclasses)`
    stond op `True` zodra er ergens een `rdfs:subClassOf` stond -- ook een die met
    knopen en strengen niets te maken heeft -- terwijl de lader wel degelijk op
    geometrie terugviel. Dan kwam het rapport zonder voorbehoud en met een echt
    oordeel, precies wat #33 wilde uitsluiten.

    De assertie hangt aan de terugval zelf en niet aan een tweede telling: de lader
    leest hier op geometrie, en `structural_diff` laat zien dat de ontologische route
    nul knopen oplevert.
    """
    tussen = load_dataset(
        _zonder_orientatiewortels(TTL_DIR / "top001_losliggende_put.ttl", tmp_path / "tussen.ttl"),
        ontology_paths=[],
    )

    assert tussen.klassenhierarchie_bekend is False
    # De wortels die de checks gebruiken dekken hier nog wel; het lezen van de knopen
    # en strengen zelf niet -- en dat is waar het voorbehoud over gaat.
    assert tussen.of_class("Put")
    assert tussen.structural_diff["knooppunten_wel_geometrie_geen_rol"] == len(tussen.nodes)


def test_structurele_vergelijking_wordt_juist_zonder_klassenkennis_gevuld(
    tmp_path: Path,
) -> None:
    """Het diagnostische instrument hoort te werken in het geval waarvoor het bedoeld is.

    Zonder klassenhierarchie levert de ontologische route nul knopen en nul strengen
    op, terwijl de geometrie er wel degelijk vindt. Zou de vergelijking hier tegen de
    al ingelezen knopen aanzitten, dan vergelijkt zij de geometrische herkenning met
    zichzelf en blijft zij leeg -- precies dan stil, dus.
    """
    kaal = load_dataset(
        _zonder_klassenhierarchie(TTL_DIR / "top001_losliggende_put.ttl", tmp_path / "kaal.ttl"),
        ontology_paths=[],
    )

    assert kaal.structural_diff["knooppunten_wel_geometrie_geen_rol"] == len(kaal.nodes)
    assert kaal.structural_diff["strengen_wel_geometrie_geen_rol"] == len(kaal.conduits)
    assert "knooppunten_zonder_geometrie" not in kaal.structural_diff


FANTOOM = TTL_DIR / "dataset_fantoomkoppeling.ttl"


def test_fantoomkoppeling_naar_een_hulpstuk_wordt_op_naamstam_hersteld() -> None:
    """`:L1_e hasConnection :T1_put` bestaat nergens; de stam `:T1` is een T-stuk (issue #60).

    Drie tegenproeven houden het herstel smal. Streng 2 koppelt netjes aan de orientatie
    en telt dus niet als herstel. Streng 3 wijst naar `:Onbekend_put`, waarvan de stam
    helemaal geen knoop is. Streng 4 wijst naar `:PutB_put`: put B bestaat en is een
    knoop, maar draagt een Putorientatie en geen Hulpstukorientatie -- die laatste
    scheidt de guard `stam in hulpstukken` van een zwakkere `stam in nodes`. Alle drie
    blijven los.
    """
    from gwsw_orox_helpers.dataset import Koppelingsherstel

    dataset = load_dataset(FANTOOM, ontology_paths=[])

    assert dataset.conduits[f"{TOETS}L1"].end_node == f"{TOETS}T1"
    assert dataset.conduits[f"{TOETS}L2"].start_node == f"{TOETS}T1"
    assert dataset.conduits[f"{TOETS}L3"].end_node is None
    assert dataset.conduits[f"{TOETS}L4"].end_node is None
    assert dataset.koppelingsherstel == Koppelingsherstel(koppelingen=1, hulpstukken=1)


def test_zonder_fantoomkoppeling_is_er_niets_hersteld(voorbeeld: GwswDataset) -> None:
    assert voorbeeld.koppelingsherstel.koppelingen == 0


def test_functie_per_klasse_komt_uit_de_restricties() -> None:
    dataset = load_dataset(TTL_DIR / "top022_hulpstuk_te_weinig.ttl", ontology_paths=[])

    assert dataset.functie_per_klasse[f"{GWSW}Kruisstuk"] == "VerbindenVanVierLeidingen"
    assert dataset.functie_per_klasse[f"{GWSW}Afsluitstuk"] == "AfsluitenVanLeidingen"
    # Een subklasse zonder eigen restrictie erft de functie van haar bovenklasse ...
    assert dataset.functie_per_klasse[f"{GWSW}T_stuk_Speciaal"] == "VerbindenVanDrieLeidingen"
    # ... maar een eigen restrictie wint van wat de bovenklasse zou geven.
    assert dataset.functie_per_klasse[f"{GWSW}T_stuk"] == "VerbindenVanDrieLeidingen"
    assert dataset.functie_per_klasse[f"{GWSW}Verbindingsstuk"] == "VerbindenVanLeidingen"


class _GcWaarnemer:
    """Een `Voortgang` die bij elke melding noteert of de cyclische GC aanstond.

    De voortgang is de enige terugkoppeling die `load_dataset` -- en sinds issue #33 ook
    `lees_ontologie` -- tijdens het lezen geeft, en dus de enige manier om van buitenaf
    te zien wat de GC daar doet. Voortgang is weergave en geen logica: deze waarnemer
    leest alleen en beinvloedt niets.
    """

    def __init__(self) -> None:
        self.bij_stap: list[bool] = []

    def start_fase(self, naam: str, totaal: int | None) -> None:
        """Doet niets; de fase begint voor het leesblok en zegt hier dus niets."""

    def stap(self, n: int = 1, label: str | None = None) -> None:
        self.bij_stap.append(gc.isenabled())

    def einde_fase(self) -> None:
        """Doet niets; waar de fase afsluit is geen belofte aan de afnemer."""


def test_cyclische_gc_ligt_stil_tijdens_het_lezen_en_komt_daarna_terug() -> None:
    """Het gedocumenteerde neveneffect van `load_dataset`, aan beide kanten vastgelegd.

    Tijdens de lezing ligt de cyclische GC van het hele proces stil -- niet alleen om het
    vullen van de grafindex heen, maar om het hele leesblok. Daarna staat hij weer aan. De
    afnemer moet op allebei kunnen rekenen; de docstring van `load_dataset` belooft het.

    De voortgangsmelding is het enige moment binnen dat blok waarop de lader zich van
    buitenaf laat zien, en dus de enige manier om de eerste helft van die belofte te
    toetsen. Waar de fase *afsluit* wordt bewust niet vastgelegd -- dat is een keuze in de
    aanroepvolgorde en geen toezegging.
    """
    assert gc.isenabled(), "voorwaarde: de testrun begint met een ingeschakelde GC"
    waarnemer = _GcWaarnemer()

    dataset = load_dataset(
        TTL_DIR / "dataset_voorbeeld.ttl", ontology_paths=[], voortgang=waarnemer
    )

    assert dataset.nodes, "de fixture hoort knopen op te leveren"
    # Een bestand, geen ontologie: precies een `stap`, en die valt tussen de twee parses
    # in -- dus binnen het blok waar de GC stilligt en niet meer alleen om `_parse` heen.
    assert waarnemer.bij_stap == [False]
    assert gc.isenabled()


def test_cyclische_gc_ligt_ook_stil_tijdens_de_objectopbouw(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """De verbreding zelf: de GC ligt ook stil ná de parses, bij `_read_nodes`.

    De voortgangstest hierboven kijkt tussen de twee parses; die blijft groen als het
    blok weer tot alleen het parseblok versmalt. Deze test kijkt op het moment dat de
    waardeobjecten worden opgebouwd -- het deel dat issue #7 aan het venster toevoegde.
    """
    assert gc.isenabled(), "voorwaarde: de testrun begint met een ingeschakelde GC"
    gezien: list[bool] = []
    echte_read_nodes = dataset_module._read_nodes

    def bespied(*args: object, **kwargs: object) -> object:
        gezien.append(gc.isenabled())
        return echte_read_nodes(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(dataset_module, "_read_nodes", bespied)

    dataset = load_dataset(TTL_DIR / "dataset_voorbeeld.ttl", ontology_paths=[])

    assert dataset.nodes, "de fixture hoort knopen op te leveren"
    assert gezien == [False]
    assert gc.isenabled()


@pytest.mark.parametrize("soort", ["ontbrekend", "onleesbaar"])
def test_cyclische_gc_komt_ook_na_een_dataseterror_terug(tmp_path: Path, soort: str) -> None:
    """Het herstel hangt aan een `finally`, dus een fout halverwege laat hem niet uit.

    Zonder dit zou een enkele mislukte lezing de GC van het hele proces van de afnemer
    uitgeschakeld achterlaten -- stil, en pas merkbaar aan het geheugen van alles wat
    erna komt.
    """
    assert gc.isenabled(), "voorwaarde: de testrun begint met een ingeschakelde GC"
    if soort == "ontbrekend":
        pad = tmp_path / "bestaat_niet.ttl"
    else:
        pad = tmp_path / "stuk.ttl"
        pad.write_text("dit is <geen geldige turtle", encoding="utf-8")

    with pytest.raises(DatasetError):
        load_dataset(pad, ontology_paths=[])

    assert gc.isenabled()


# --- De ontologie als eigen leesweg (issue #33) ----------------------------------------

# Het aantal triples van de gebundelde GWSW 1.6-ontologie (`owl:versionInfo` versie=1.6;
# zie de Harde regels in `CLAUDE.md`). Het getal komt uit issue #19 en staat hier als
# onafhankelijke ijkwaarde: het bewijst dat `lees_ontologie()` zonder argumenten de
# gebundelde ontologie leest en niet per ongeluk een lege of halve index oplevert.
#
# **Bij een ontologie-upgrade schuift dit getal mee** en hoort het hier bijgewerkt te
# worden -- naast `uv run python scripts/maak_gwsw_index.py` en de versieregel in
# `CLAUDE.md`, de twee stappen die die Harde regel wél opsomt. Het is de derde plek, en
# hij meldt zich vanzelf: deze test wordt rood. Dezelfde afhankelijkheid dragen
# `AANTAL_DATATYPES` en `AANTAL_KENMERKKLASSEN` in `tests/test_ontologie.py` al sinds
# issue #19.
AANTAL_TRIPELS_GWSW16 = 63_614


def _tripels(index: GraafIndex) -> set[tuple[RdfNode, RdfNode, RdfNode]]:
    """Alle triples van een index als verzameling.

    De index biedt met opzet geen iteratie over de hele graaf (zie de docstring van
    `graaf`): het leescontract van de checks heeft die niet nodig. Voor een
    inhoudsvergelijking tussen twee indexen is ze wel nodig, en dan is de spo-index de
    enige weg erheen. Een test mag daarvoor naar binnen kijken; productiecode niet.
    """
    return {
        (subject, predicate, object_)
        for subject, per_predicaat in index._spo.items()
        for predicate, objecten in per_predicaat.items()
        for object_ in objecten
    }


class _Verslag:
    """Een `Voortgang` die opschrijft wat er gemeld werd; leest alleen, stuurt niets."""

    def __init__(self) -> None:
        self.fasen: list[tuple[str, int | None]] = []
        self.stappen: list[str | None] = []
        self.eindes = 0

    def start_fase(self, naam: str, totaal: int | None) -> None:
        self.fasen.append((naam, totaal))

    def stap(self, n: int = 1, label: str | None = None) -> None:
        self.stappen.append(label)

    def einde_fase(self) -> None:
        self.eindes += 1


def test_lees_ontologie_met_een_lege_lijst_geeft_een_lege_index() -> None:
    """Een lege lijst is de expliciete keuze om zonder ontologie te lezen (`ontologiepaden`).

    De fase komt er ook dan, met totaal nul: wie fasen meetelt hoort de fase-indeling
    niet van de inhoud van zijn argument te zien afhangen. Zie de docstring van
    `lees_ontologie`; dit is de bewaker van die keuze (bevinding uit de review van #33).
    """
    verslag = _Verslag()

    assert len(lees_ontologie([], voortgang=verslag)) == 0
    assert verslag.fasen == [("Ontologie laden", 0)]
    assert verslag.stappen == []
    assert verslag.eindes == 1


def test_lees_ontologie_levert_de_restrictiebron_van_load_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Precies de index die `load_dataset` intern opbouwt en daarna weggooit (issue #33).

    De `restrictiebron` is een lokale van `load_dataset` en komt nergens naar buiten; ze
    is alleen te pakken te krijgen op de plek waar de lader haar gebruikt. Vandaar de
    onderschepping van `_subclass_closure`: wat daar binnenkomt *is* de bron waarop de
    klassenafleiding draait. Zonder deze test zou "dezelfde weg" een belofte in een
    docstring zijn -- een tweede parseerpad met een net andere aanroep zou hier
    stilzwijgend een andere index opleveren.

    Op de gebundelde ontologie, want dat is het geval dat de afnemer krijgt als hij
    niets opgeeft; het tripelaantal is de ijkwaarde uit issue #19.
    """
    gevangen: list[GraafIndex] = []
    echte_afsluiting = dataset_module._subclass_closure

    def bespied(bron: GraafIndex) -> dict[str, frozenset[str]]:
        gevangen.append(bron)
        return echte_afsluiting(bron)

    monkeypatch.setattr(dataset_module, "_subclass_closure", bespied)
    load_dataset(TTL_DIR / "dataset_voorbeeld.ttl")

    (restrictiebron,) = gevangen
    los = lees_ontologie()

    assert len(los) == len(restrictiebron) == AANTAL_TRIPELS_GWSW16
    assert _tripels(los) == _tripels(restrictiebron)


# Het tripelaantal van de gebundelde GWSW 1.7-ontologie, naast `AANTAL_TRIPELS_GWSW16`
# (issue #32). Gemeten via de echte package-API: `lees_ontologie` parseert de 1.7-bundel
# tot precies dezelfde `GraafIndex`-vorm. Het parseerpad is versie-agnostisch, dus dit
# getal is nu al hard te meten -- de klasse-afgeleiden (subklasse-afsluiting, de 709
# kenmerkklassen) spellen nog met de 1.6-basis en komen pas na de versiedetectie van
# deel c aan bod. Schuift bij een 1.7-upgrade net zo mee als het 1.6-getal.
AANTAL_TRIPELS_GWSW17 = 66_664


def test_de_17_bundel_draagt_zijn_eigen_tripelaantal() -> None:
    """De 1.7-bundel is via `lees_ontologie` te lezen en draagt zijn eigen ijkwaarde.

    Deel b baseline: het parseerpad kent geen versie, dus het tripelaantal is meetbaar
    zonder de detectie die deel c toevoegt. De 1.6-ijkwaarde blijft ongemoeid ernaast.
    """
    los = lees_ontologie(paden=[gebundelde_ontologie_voor("1.7")])
    assert len(los) == AANTAL_TRIPELS_GWSW17
    assert AANTAL_TRIPELS_GWSW17 != AANTAL_TRIPELS_GWSW16


def test_lees_ontologie_meldt_een_eigen_fase_met_een_stap_per_bestand(tmp_path: Path) -> None:
    """Een fase "Ontologie laden" met één stap per bestand, in de opgegeven volgorde."""
    eerste = tmp_path / "eerste.ttl"
    eerste.write_text("@prefix ex: <http://example.org/> .\nex:a ex:b ex:c .\n", encoding="utf-8")
    tweede = tmp_path / "tweede.ttl"
    tweede.write_text("@prefix ex: <http://example.org/> .\nex:d ex:e ex:f .\n", encoding="utf-8")
    verslag = _Verslag()

    index = lees_ontologie([eerste, tweede], voortgang=verslag)

    assert verslag.fasen == [("Ontologie laden", 2)]
    assert verslag.stappen == ["eerste.ttl", "tweede.ttl"]
    assert verslag.eindes == 1
    # De bestanden stapelen in één index; de tweede overschrijft de eerste niet.
    assert len(index) == 2


def test_de_voortgang_van_load_dataset_blijft_een_enkele_ttl_fase(tmp_path: Path) -> None:
    """De fase van de lader is bevroren: "TTL laden", `1 + len(paden)` stappen (issue #33).

    `lees_ontologie` deelt zijn parseerpad met `load_dataset`. Zou dat delen op faseniveau
    gebeuren -- de nieuwe functie aanroepen inclusief haar `start_fase` -- dan kreeg de
    lader er stilzwijgend een tweede fase bij en zag elke afnemer met een voortgangsbalk
    iets anders dan voorheen. Dit is de bewaker daarvoor: de dataset gaat voorop, de
    ontologiebestanden tellen in dezelfde fase mee, en er is er precies één.
    """
    ontologie = tmp_path / "mini_ontologie.ttl"
    ontologie.write_text(
        "@prefix gwsw: <http://data.gwsw.nl/1.6/totaal/> .\n"
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
        "gwsw:Inspectieput rdfs:subClassOf gwsw:Put .\n",
        encoding="utf-8",
    )
    verslag = _Verslag()

    load_dataset(TTL_DIR / "dataset_voorbeeld.ttl", [ontologie], voortgang=verslag)

    assert verslag.fasen == [("TTL laden", 2)]
    assert verslag.stappen == ["dataset_voorbeeld.ttl", "mini_ontologie.ttl"]
    assert verslag.eindes == 1


def test_lees_ontologie_legt_de_cyclische_gc_stil_en_zet_hem_terug(tmp_path: Path) -> None:
    """Hetzelfde neveneffect als `load_dataset`, en met dezelfde toezegging in de docstring.

    De voortgangsmelding is ook hier het enige moment binnen het leesblok waarop de
    functie zich van buitenaf laat zien; `_GcWaarnemer` noteert er de stand van de GC.
    """
    assert gc.isenabled(), "voorwaarde: de testrun begint met een ingeschakelde GC"
    pad = tmp_path / "mini.ttl"
    pad.write_text("@prefix ex: <http://example.org/> .\nex:a ex:b ex:c .\n", encoding="utf-8")
    waarnemer = _GcWaarnemer()

    lees_ontologie([pad], voortgang=waarnemer)

    assert waarnemer.bij_stap == [False]
    assert gc.isenabled()


def test_lees_ontologie_geeft_de_terugvalcodering_door() -> None:
    """Dezelfde coderingsregel als bij `load_dataset`: UTF-8, tenzij de afnemer anders zegt."""
    with pytest.raises(DatasetError, match="geen geldige UTF-8"):
        lees_ontologie([TTL_DIR / "codering_cp850.ttl"])

    index = lees_ontologie([TTL_DIR / "codering_cp850.ttl"], terugvalcodering="cp850")

    assert len(index) > 0


def test_lees_ontologie_geeft_dataseterror_bij_een_ontbrekend_pad(tmp_path: Path) -> None:
    with pytest.raises(DatasetError, match="kan niet gelezen worden"):
        lees_ontologie([tmp_path / "bestaat_niet.ttl"])


def test_lees_ontologie_zet_de_gc_ook_na_een_fout_terug(tmp_path: Path) -> None:
    """Het herstel hangt aan een `finally`; een fout halverwege laat de GC niet uit."""
    assert gc.isenabled(), "voorwaarde: de testrun begint met een ingeschakelde GC"

    with pytest.raises(DatasetError):
        lees_ontologie([tmp_path / "bestaat_niet.ttl"])

    assert gc.isenabled()


def test_stelsel_leden_scheidt_lokale_stelsels_van_buckets() -> None:
    """De regel waarmee de nulmetingjoin een stelsel als focusnode herkent (#17).

    Een lokaal stelsel draagt alleen strengen; een gemeentebrede `_geb_0`-bucket draagt
    strengen en putten door elkaar heen. `nulbevinding._Joiner.stelsel` gebruikt dat
    onderscheid om de overtreding aan het stelsel te koppelen.
    """
    dataset = load_dataset(TTL_DIR / "stelsels_registratie.ttl", ontology_paths=[])

    lokaal = buckets = 0
    for subject in dataset.subjects_of_class("Stelsel"):
        strengen, knopen = dataset.stelsel_leden(str(subject))
        if strengen and not knopen:
            lokaal += 1
        elif strengen and knopen:
            buckets += 1

    assert lokaal == 2  # vuilwater-1 en gemengd-1
    assert buckets == 1  # de hemelwater-bucket met een streng én een put


# --- De overslag- en omwegtakken van de lezers (issue #16) -----------------------------
#
# Zeven vormen die conform GWSW 1.6 zijn maar in geen enkele andere fixture voorkomen, en
# die `inlezen.py` elk met een eigen tak afhandelt: overslaan wat geen inwinning is,
# overslaan wat geen waarde draagt, en het putdekselniveau langs twee omwegen vinden. Ze
# stonden alle zeven ongedekt in het dekkingsrapport; een refactor die er een stilzette
# bleef groen.

ROMMELIG = TTL_DIR / "dataset_rommelige_export.ttl"


@pytest.fixture(scope="module")
def rommelig() -> GwswDataset:
    """De export met de zeven ongebruikelijke vormen; zonder ontologie gelezen.

    De fixture declareert haar eigen klassenhierarchie in de gedeelde prelude, dus de
    lader herkent knopen en strengen aan hun orientatieklasse en niet aan hun geometrie.
    Dat is hier wezenlijk: put E draagt geen punt en moet toch een knoop zijn.
    """
    return load_dataset(ROMMELIG, ontology_paths=[])


def test_een_subaspect_dat_geen_inwinning_is_telt_niet_als_herkomst(
    rommelig: GwswDataset,
) -> None:
    """Een kenmerk mag meer sub-aspecten dragen dan alleen zijn Inwinning.

    `_read_inwinning` loopt ze allemaal af en moet overslaan wat geen `gwsw:Inwinning`
    is. Leest hij in plaats daarvan het eerste het beste sub-aspect, dan krijgt het
    kenmerk een herkomst die er niet staat -- een verzinsel dat nergens een melding
    oplevert en dat de hoogte- en ouderdomsanalyses wel meewegen.
    """
    begindatum = rommelig.nodes[f"{TOETS}PutA"].aspect("Begindatum")

    assert begindatum is not None
    assert begindatum.value == "1980-01-01"
    assert begindatum.inwinning is None
    # Voorwaarde: het kenmerk draagt wel degelijk een sub-aspect, alleen geen Inwinning.
    subaspecten = list(aspects_of(rommelig.graph, URIRef(f"{TOETS}PutA_bd")))
    assert subaspecten
    assert not any(
        (deel, RDF.type, URIRef(f"{GWSW}Inwinning")) in rommelig.graph for deel in subaspecten
    )


def test_een_kenmerk_zonder_waarde_telt_als_afwezig(rommelig: GwswDataset) -> None:
    """Een Maaiveldhoogte zonder `hasValue` is geen meting maar een leeg kenmerk.

    `_aspect_van_klasse` slaat hem over. Zou hij hem meenemen, dan kreeg de put een
    maaiveldkenmerk zonder getal: `Node.maaiveld` blijft dan alsnog leeg, maar
    `maaiveld_aspect` niet -- en dat is het veld waaraan ATTR-013 en de vulwaardestap
    zien of er iets geregistreerd is.
    """
    put = rommelig.nodes[f"{TOETS}PutB"]

    assert put.maaiveld_aspect is None
    assert put.maaiveld is None
    assert put.bovenkant is None
    # Voorwaarde: de maaiveldorientatie ernaast draagt wel degelijk een Maaiveldhoogte.
    assert rommelig.subjects_of_class("Maaiveldhoogte")


def test_putdekselniveau_rechtstreeks_aan_de_put(rommelig: GwswDataset) -> None:
    """De eerste omweg van `_deksel_kenmerk`: geen Putdeksel-onderdeel, geen orientatie.

    Sommige exports hangen het niveau rechtstreeks aan de put. Wie alleen de weg via het
    Putdeksel-onderdeel volgt, laat `Node.bovenkant` stil op de maaiveldhoogte
    terugvallen -- geen melding, alleen een andere hoogte onder elke hoogtecheck.
    """
    put = rommelig.nodes[f"{TOETS}PutC"]

    assert put.dekselniveau == 9.80
    assert put.bovenkant == 9.80
    assert rommelig.onderdelen(f"{TOETS}PutC") == [], "de put heeft geen Putdeksel-onderdeel"


def test_putdekselniveau_aan_het_putdeksel_zonder_dekselorientatie(
    rommelig: GwswDataset,
) -> None:
    """De tweede omweg: het Putdeksel is er wel, de Dekselorientatie niet.

    `_deksel_kenmerk` kijkt eerst in de orientaties van het onderdeel en daarna op het
    onderdeel zelf. Valt die tweede stap weg, dan verdwijnt het niveau met dezelfde
    stille terugval op het maaiveld als hierboven.
    """
    put = rommelig.nodes[f"{TOETS}PutD"]

    assert put.dekselniveau == 9.70
    assert rommelig.onderdelen(f"{TOETS}PutD", "Putdeksel") == [f"{TOETS}PutD_dek"]
    assert rommelig.subjects_of_class("Dekselorientatie") == [], (
        "voorwaarde: geen enkel putdeksel in deze fixture draagt een Dekselorientatie"
    )


def test_een_geometrie_aspect_zonder_literaal_laat_de_knoop_staan(
    rommelig: GwswDataset,
) -> None:
    """Een Punt zonder `hasValue` is geen geometriefout maar een leeg aspect.

    De put blijft een knoop -- haar orientatie is een Putorientatie -- alleen zonder
    punt. Dat is iets anders dan een onleesbare literaal: die belandt in
    `geometry_errors` (zie `test_een_onleesbare_gml_literaal_belandt_in_geometry_errors`)
    en deze niet. Het onderscheid telt voor het rapport: een lege geometrie is een
    registratiegat, een onleesbare is een exportfout.
    """
    put = rommelig.nodes[f"{TOETS}PutE"]

    assert put.point is None
    assert put.z is None
    assert f"{TOETS}PutE_ori" not in rommelig.geometry_errors
    # Voorwaarde: de orientatie draagt wel degelijk een Punt-aspect, alleen zonder waarde.
    punten = [
        aspect
        for aspect in aspects_of(rommelig.graph, URIRef(f"{TOETS}PutE_ori"))
        if (aspect, RDF.type, URIRef(f"{GWSW}Punt")) in rommelig.graph
    ]
    assert punten


def test_twee_orientaties_leveren_een_knoop_en_een_streng(rommelig: GwswDataset) -> None:
    """Een object met twee orientaties telt een keer, niet twee keer.

    Het GWSW verbiedt het niet en een export mag het schrijven; de twee lezers houden
    per object de eerste orientatie aan die zij tegenkomen. Zonder die overslag zou
    dezelfde put -- en dezelfde streng -- twee keer in het domeinmodel staan, met elke
    bevinding erop verdubbeld en met een tweede, andere geometrie.
    """
    putorientaties = {
        str(orientatie)
        for orientatie in rommelig.graph.subjects(RDF.type, URIRef(f"{GWSW}Putorientatie"))
        if str(orientatie).startswith(f"{TOETS}PutF")
    }
    leidingorientaties = {
        str(orientatie)
        for orientatie in rommelig.graph.subjects(RDF.type, URIRef(f"{GWSW}Leidingorientatie"))
    }

    assert putorientaties == {f"{TOETS}PutF_ori", f"{TOETS}PutF_ori2"}
    assert leidingorientaties == {f"{TOETS}L1_ori", f"{TOETS}L1_ori2"}
    assert [uri for uri in rommelig.nodes if uri.startswith(f"{TOETS}PutF")] == [f"{TOETS}PutF"]
    assert list(rommelig.conduits) == [f"{TOETS}L1"]
    # Elke put en elke streng een keer, en geen "PutF (2)" ertussen.
    assert sorted(node.label for node in rommelig.nodes.values()) == list("ABCDEF")

    # Welke van de twee het wordt is geen willekeur: het is de eerst geschreven
    # orientatie, want de lezers lopen de graaf in schrijfvolgorde af en slaan het
    # object over zodra het er staat. Dat is ook aan de geometrie te zien -- de tweede
    # orientatie ligt vijf meter noordelijker en die y komt er niet uit.
    put = rommelig.nodes[f"{TOETS}PutF"]
    assert put.orientation == f"{TOETS}PutF_ori"
    assert put.point is not None and put.point.y == 2000.0
    streng = rommelig.conduits[f"{TOETS}L1"]
    assert streng.line is not None
    assert streng.line.coords[0][1] == 2000.0


# --- `subset()`: wat er meegesneden wordt en wat niet (issue #16) ----------------------


def test_subset_dunt_het_domeinmodel_uit_maar_laat_de_graaf_heel(
    voorbeeld: GwswDataset,
) -> None:
    """`subset()` snijdt `nodes` en `conduits`; de graafindex gaat ongewijzigd mee.

    Dat is geen detail maar de reden dat de methode bruikbaar is: de checks zoeken hun
    onderdelen -- een overstortdrempel, een compartiment -- rechtstreeks in de graaf op,
    en een meegesneden index zou daar stilzwijgend gegevens weglaten. De keerzijde staat
    in de docstring van de methode en hier: `subjects_of_class()` blijft over de
    volledige export lopen, ook op een uitgedunde dataset.
    """
    behouden = f"{TOETS}PutA"
    kleiner = voorbeeld.subset([behouden])

    assert set(kleiner.nodes) == {behouden}
    assert kleiner.conduits == {}
    # Niet een gefilterde kopie maar letterlijk dezelfde index.
    assert kleiner.graph is voorbeeld.graph
    assert len(kleiner.graph) == len(voorbeeld.graph)
    assert kleiner.subjects_of_class("Put") == voorbeeld.subjects_of_class("Put")
    # Beide putten, ook die welke net uit `nodes` gesneden is. (De lijst zelf mag een
    # subject vaker noemen: put A is Inspectieput én VerdektePut, allebei in de
    # afsluiting van Put.)
    assert {str(subject) for subject in kleiner.subjects_of_class("Put")} == {
        f"{TOETS}PutA",
        f"{TOETS}PutB",
    }
    # De herkomst blijft ongemoeid: `subset` levert een nieuwe dataset op.
    assert len(voorbeeld.nodes) == 4
    assert len(voorbeeld.conduits) == 3
    # En de aanroeper mag elke iterable meegeven, ook een eenmalige.
    assert set(voorbeeld.subset(iter([behouden])).nodes) == {behouden}


def test_subset_draagt_de_rest_van_de_dataset_ongewijzigd_over(voorbeeld: GwswDataset) -> None:
    """Alles wat niet over knopen en strengen gaat, komt onveranderd mee.

    `subset()` is een `replace()` met drie velden erin; de andere komen ongewijzigd mee.
    Daar bouwt de afnemer op die na het uitdunnen nog de bron, de klassenhierarchie, de
    ontologiepaden of het herstel van de fantoomkoppeling nodig heeft -- en juist een
    `replace()` is de vorm waarin dat stil te breken is.

    De twee memo's zijn de uitzondering en met opzet: ze staan op `init=False` en
    beginnen leeg (zie `test_de_typenmemo_gaat_niet_mee_naar_een_uitgedunde_dataset` en
    `test_een_replace_afgeleide_begint_met_een_lege_herleidingsmemo`).
    """
    kleiner = voorbeeld.subset([*voorbeeld.nodes, *voorbeeld.conduits])

    assert kleiner.nodes == voorbeeld.nodes
    assert kleiner.conduits == voorbeeld.conduits
    assert kleiner.source == voorbeeld.source
    assert kleiner.subclasses is voorbeeld.subclasses
    assert kleiner.ontologies == voorbeeld.ontologies
    assert kleiner.decode_fallback == voorbeeld.decode_fallback
    assert kleiner.structural_diff == voorbeeld.structural_diff
    assert kleiner.kenmerk_property == voorbeeld.kenmerk_property
    assert kleiner.functie_per_klasse == voorbeeld.functie_per_klasse
    assert kleiner.koppelingsherstel == voorbeeld.koppelingsherstel
    assert kleiner._types_memo == {}
    assert kleiner._resolved_nodes == {}


def test_subset_houdt_de_geometriefouten_bij_hun_object(tmp_path: Path) -> None:
    """`geometry_errors` is op het object gesleuteld, dus het filter van `subset` klopt.

    Tot issue #36 sleutelde de lezer de melding op de **orientatie**, terwijl `subset()`
    filtert op de knoop- en streng-URI's die de aanroeper doorgeeft; die verzamelingen
    zijn per constructie disjunct, dus elke `subset()` -- ook een die *elk* object behoudt
    -- kwam zonder geometriefouten terug. Nu de sleutels objecten zijn doet het bestaande
    filter zijn werk: een subset die alles behoudt geeft dezelfde `geometry_errors` als de
    bron, en een echte deelverzameling houdt alleen de fouten van de behouden objecten.
    """
    gelezen = load_dataset(_kapotte_geometrie(tmp_path), ontology_paths=[])

    assert set(gelezen.geometry_errors) == {f"{TOETS}PutC", f"{TOETS}L1"}
    assert f"{TOETS}PutC" in gelezen.nodes
    assert f"{TOETS}L1" in gelezen.conduits

    # "Alles behouden" levert nu dezelfde foutenlijst als de bron.
    alles = gelezen.subset([*gelezen.nodes, *gelezen.conduits])
    assert alles.nodes == gelezen.nodes
    assert alles.geometry_errors == gelezen.geometry_errors

    # Een echte deelverzameling houdt alleen de fout van het behouden object.
    alleen_putc = gelezen.subset([f"{TOETS}PutC"])
    assert set(alleen_putc.geometry_errors) == {f"{TOETS}PutC"}
