"""Tests voor het inlezen van de OroX-dataset."""

from __future__ import annotations

from pathlib import Path

import pytest
from rdflib import URIRef

from gwsw_orox_helpers.dataset import GWSW, GwswDataset, aspects_of, load_dataset, parts_of
from gwsw_orox_helpers.errors import DatasetError

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
    assert [pad.name for pad in voorbeeld.ontologies] == ["Ontologie_GWSW_Totaal.ttl"]


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
