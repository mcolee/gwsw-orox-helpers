"""De clip verdeelt een OroX ruimtelijk en de merge maakt er weer het origineel van."""

import json
import sys
from collections import Counter
from pathlib import Path

import pyoxigraph
import pytest
import rdflib

# Dezelfde keuze als in `test_schrijven.py`: `rdflib.compare.isomorphic` en niet
# `Graph.isomorphic()`. Die laatste slaat elke triple met een blanke knoop over en
# verklaart die ongezien gelijk -- in `mini_orox.ttl` 22 van de 55 triples, en juist het
# deel waar de belofte van de knip-omkeer over gaat.
from rdflib.compare import isomorphic
from rdflib.namespace import RDF

from gwsw_orox_helpers.clip import clip_orox, merge_orox
from gwsw_orox_helpers.errors import DatasetError

TTL_DIR = Path(__file__).parent / "fixtures" / "ttl"
GIS_DIR = Path(__file__).parent / "fixtures" / "gis"
MINI = TTL_DIR / "mini_orox.ttl"
MINI_GRENS = GIS_DIR / "mini_grens.geojson"

# Het publieke GWSW-Voorbeeld van Stichting RIONED (Juinen, 119 kB, bovenstrooms
# `GwswDataset__Voorbeeld_v1.6.orox.ttl`), byte-exact als fixture in deze repo, zodat de
# round-trip op een echte export ook in CI draait en niet alleen op de machine van de
# auteur -- byte-exact omdat de knip tekstplakjes uit de posLists snijdt. Juinen ligt
# rond x=168000-169100, y=442500-443300 en dus niet in De Wolden of Hoogeveen; hij krijgt
# daarom een eigen grensfixture die zijn eigen omhullende in tweeen deelt.
JUINEN = TTL_DIR / "juinen_voorbeeld_v1_6.ttl"
JUINEN_GRENS = GIS_DIR / "juinen_grens.geojson"
# De export van De Wolden en Hoogeveen: 112 MB, ook niet getrackt (marker `zwaar`).
DEWOLDEN = Path("/home/martin/nlriochecker/data/gwsw_orox_ttl/dewoldenhoogeveen_orox.ttl")
DEWOLDEN_GRENS = GIS_DIR / "gemeentegrenzen_dewoldenhoogeveen.geojson"

MINI_BASIS = "http://sparql.gwsw.nl/repositories/Mini#"
GWSW = "http://data.gwsw.nl/1.6/totaal/"
KNIP = "https://github.com/mcolee/gwsw-orox-helpers/ns/clip#"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"


def _graaf(pad: Path) -> rdflib.Graph:
    """Leest een TTL met rdflib -- het onafhankelijke vergelijkingsgereedschap."""
    graaf = rdflib.Graph()
    graaf.parse(pad, format="turtle")
    return graaf


def _mini(naam: str) -> rdflib.URIRef:
    """Een URI uit de mini-fixture."""
    return rdflib.URIRef(f"{MINI_BASIS}{naam}")


def _tellingen(pad: Path, fallback_encoding: str | None = None) -> tuple[int, Counter[str]]:
    """Het aantal triples en het aantal objecten per GWSW-klasse, streamend geteld.

    Dezelfde meting als in `test_schrijven.py`: voor een bestand van 112 MB is een
    rdflib-graaf (en dus `isomorphic`) geen optie.
    """
    triples = 0
    klassen: Counter[str] = Counter()
    rauw = pad.read_bytes()
    try:
        tekst = rauw.decode("utf-8")
    except UnicodeDecodeError:
        assert fallback_encoding is not None
        tekst = rauw.decode(fallback_encoding)
    for quad in pyoxigraph.parse(tekst, format=pyoxigraph.RdfFormat.TURTLE):
        triples += 1
        if quad.predicate.value == RDF_TYPE and isinstance(quad.object, pyoxigraph.NamedNode):
            if quad.object.value.startswith("http://data.gwsw.nl/"):
                klassen[quad.object.value.rsplit("/", 1)[-1]] += 1
    return triples, klassen


def _geknipt(tmp_path: Path) -> list[Path]:
    """De mini-fixture geknipt langs de minigrens."""
    return clip_orox(MINI, MINI_GRENS, tmp_path / "delen", sleutel="gemeentenaam")


# --------------------------------------------------------------------------------------
# De belofte: heen en terug is dezelfde graaf
# --------------------------------------------------------------------------------------


def test_mini_round_trip_is_isomorf(tmp_path: Path) -> None:
    """`merge(clip(mini))` levert de bron terug, knip door `:Leiding_1` incluis."""
    delen = _geknipt(tmp_path)
    doel = tmp_path / "terug.ttl"
    merge_orox(delen, doel)

    assert len(delen) == 2
    assert isomorphic(_graaf(doel), _graaf(MINI))


def test_geknipte_geometrie_komt_letterlijk_terug(tmp_path: Path) -> None:
    """De herstelde posList is de tekst van de bron, niet een teruggerekende float.

    Dit is de kern van de knip-omkering: `233000.00` hoort er als `233000.00` uit te
    komen en niet als `233000.0`. Isomorfie zou dat ook opmerken, maar dan pas nadat de
    hele graaf al vergeleken is; hier staat het als eigen eis.
    """
    delen = _geknipt(tmp_path)
    doel = tmp_path / "terug.ttl"
    merge_orox(delen, doel)

    origineel = [
        str(waarde)
        for waarde in _graaf(MINI).objects(None, rdflib.URIRef(f"{GWSW}hasValue"))
        if "LineString" in str(waarde)
    ]
    hersteld = [
        str(waarde)
        for waarde in _graaf(doel).objects(None, rdflib.URIRef(f"{GWSW}hasValue"))
        if "LineString" in str(waarde)
    ]
    assert hersteld == origineel
    assert "233000.00 581000.00 8.50 233040.00 581000.00 8.40" in origineel[0]


def test_een_deel_dat_alles_dekt_is_de_identiteit(tmp_path: Path) -> None:
    """Een grenslaag met een vlak levert een deel dat zelf al de hele bron is."""
    grens = tmp_path / "alles.geojson"
    grens.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"naam": "alles"},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [0.0, 0.0],
                                    [400000.0, 0.0],
                                    [400000.0, 700000.0],
                                    [0.0, 700000.0],
                                    [0.0, 0.0],
                                ]
                            ],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    delen = clip_orox(MINI, grens, tmp_path / "delen", sleutel="naam")
    doel = tmp_path / "terug.ttl"
    merge_orox(delen, doel)

    assert len(delen) == 1
    assert isomorphic(_graaf(delen[0]), _graaf(MINI))
    assert isomorphic(_graaf(doel), _graaf(MINI))


# --------------------------------------------------------------------------------------
# Wat er in welk deel terechtkomt
# --------------------------------------------------------------------------------------


def test_elk_vlak_krijgt_een_bestand_met_zijn_naam(tmp_path: Path) -> None:
    """De uitvoernamen volgen de opgegeven property, in de volgorde van de grenslaag."""
    delen = _geknipt(tmp_path)
    assert [pad.name for pad in delen] == [
        "mini_orox__Mini-West.ttl",
        "mini_orox__Mini-Oost.ttl",
    ]


def test_de_sleutel_bepaalt_de_naam(tmp_path: Path) -> None:
    """Een andere property levert andere bestandsnamen op dezelfde verdeling."""
    delen = clip_orox(MINI, MINI_GRENS, tmp_path / "delen", sleutel="gemeentecode")
    assert [pad.name for pad in delen] == [
        "mini_orox__GM9001.ttl",
        "mini_orox__GM9002.ttl",
    ]


def test_knopen_gaan_naar_het_vlak_waarin_ze_liggen(tmp_path: Path) -> None:
    """Punt-in-vlak: `:Put_1` ligt in Mini-West en `:Put_2` in Mini-Oost."""
    west, oost = (_graaf(pad) for pad in _geknipt(tmp_path))

    assert (_mini("Put_1"), RDF.type, None) in west
    assert (_mini("Put_1"), RDF.type, None) not in oost
    assert (_mini("Put_2"), RDF.type, None) in oost
    assert (_mini("Put_2"), RDF.type, None) not in west
    # Het geometrieloze onderdeel van :Put_1 volgt zijn houder.
    assert (_mini("Put_1_deksel"), RDF.type, None) in west
    assert (_mini("Put_1_deksel"), RDF.type, None) not in oost


def test_grenskruisende_leiding_staat_in_beide_delen(tmp_path: Path) -> None:
    """De leiding houdt in elk deel zijn eigen URI, zijn kenmerken en een eigen stuk.

    Elk stuk ligt binnen het vlak waar het bij hoort: de knip zit op x=233020 en dat is
    precies de grens tussen Mini-West en Mini-Oost.
    """
    west, oost = (_graaf(pad) for pad in _geknipt(tmp_path))

    for helft in (west, oost):
        assert (_mini("Leiding_1"), RDF.type, rdflib.URIRef(f"{GWSW}Gemengdriool")) in helft
        assert helft.value(_mini("Leiding_1"), rdflib.RDFS.label) == rdflib.Literal("put 1-put 2")
        # De niet-geometrische kenmerken (lengte, inwinning) gaan mee naar elke kant.
        assert (_mini("Leiding_1_inwinning"), RDF.type, None) in helft
        assert (_mini("Leiding_1_ori"), rdflib.URIRef(f"{KNIP}geknipt"), None) in helft

    stukken = {
        naam: [
            str(waarde)
            for waarde in helft.objects(None, rdflib.URIRef(f"{GWSW}hasValue"))
            if "LineString" in str(waarde)
        ]
        for naam, helft in (("west", west), ("oost", oost))
    }
    assert len(stukken["west"]) == 1 and len(stukken["oost"]) == 1
    assert "233000.00 581000.00 8.50 233020.000 581000.000 8.450" in stukken["west"][0]
    assert "233020.000 581000.000 8.450 233040.00 581000.00 8.40" in stukken["oost"][0]


def test_knipmerken_wijzen_naar_dezelfde_herkomst(tmp_path: Path) -> None:
    """De twee stukken noemen dezelfde herkomst en samen alle volgnummers."""
    west, oost = (_graaf(pad) for pad in _geknipt(tmp_path))

    herkomsten = set()
    volgnummers = set()
    for helft in (west, oost):
        for waarde in helft.objects(None, rdflib.URIRef(f"{KNIP}herkomst")):
            herkomsten.add(str(waarde))
        for waarde in helft.objects(None, rdflib.URIRef(f"{KNIP}volgnummer")):
            volgnummers.add(int(waarde))
        for waarde in helft.objects(None, rdflib.URIRef(f"{KNIP}aantal")):
            assert int(waarde) == 2
    assert len(herkomsten) == 1
    assert volgnummers == {0, 1}


def test_geometrieloos_onderdeel_volgt_zijn_aanhechtingspunt(tmp_path: Path) -> None:
    """`:Ontluchter_1` heeft geen geometrie en hangt onder een leiding die aan beide
    kanten van de grens ligt. Zijn houder wijst dus geen kant aan; het aanhechtingspunt
    -- de `hasConnection` naar `:Put_2_ori` -- wel, en dat is Mini-Oost.
    """
    west, oost = (_graaf(pad) for pad in _geknipt(tmp_path))

    assert (_mini("Ontluchter_1"), RDF.type, None) in oost
    assert (_mini("Ontluchter_1"), RDF.type, None) not in west
    # En de hasPart-rand ernaartoe gaat mee naar dezelfde kant, zodat er niets loshangt.
    part = rdflib.URIRef(f"{GWSW}hasPart")
    assert (_mini("Leiding_1"), part, _mini("Ontluchter_1")) in oost
    assert (_mini("Leiding_1"), part, _mini("Ontluchter_1")) not in west


def test_gedeelde_structuur_staat_in_elk_deel(tmp_path: Path) -> None:
    """De ontologiekop hangt nergens aan en hoort daarom in elke helft te staan."""
    kop = rdflib.URIRef("file:///mini/GwswDataset__Mini.orox.ttl")
    for pad in _geknipt(tmp_path):
        helft = _graaf(pad)
        assert (kop, RDF.type, rdflib.OWL.Ontology) in helft
        assert helft.value(kop, rdflib.OWL.versionInfo) is not None


def test_geen_wees_verwijzing_langs_haspart_of_hasaspect(tmp_path: Path) -> None:
    """Elke helft is zelfdekkend: elke houder/onderdeel-rand heeft beide einden thuis.

    De uitzondering staat in de moduledocstring: een `hasConnection` van een geknipte
    leiding naar de put aan de overkant blijft wel over de grens wijzen. Dat is de knip
    zelf en niet een gat in de helft.
    """
    for pad in _geknipt(tmp_path):
        helft = _graaf(pad)
        subjecten = set(helft.subjects())
        for predicaat in (f"{GWSW}hasPart", f"{GWSW}hasAspect"):
            for houder, doel in helft.subject_objects(rdflib.URIRef(predicaat)):
                assert houder in subjecten
                assert doel in subjecten, f"{doel} hangt los in {pad.name}"


def test_elke_helft_is_door_de_leeslaag_te_lezen(tmp_path: Path) -> None:
    """Een deel is geen losse hoop triples maar een OroX die `load_dataset` aankan.

    De afnemer van deze package leest de delen met de leeslaag; komt daar een halve
    dataset uit die haar knopen of strengen niet meer herkent, dan is de clip stuk. De
    knip zelf laat zich hier ook zien: `:Leiding_1` is aan beide kanten een streng.
    """
    from gwsw_orox_helpers.dataset import load_dataset

    west, oost = (load_dataset(pad) for pad in _geknipt(tmp_path))

    assert set(west.nodes) == {f"{MINI_BASIS}Put_1"}
    assert set(oost.nodes) == {f"{MINI_BASIS}Put_2"}
    assert f"{MINI_BASIS}Leiding_1" in west.conduits
    assert f"{MINI_BASIS}Leiding_1" in oost.conduits
    assert not west.geometry_errors and not oost.geometry_errors
    # Elke helft draagt zijn eigen stuk van de doorgeknipte lijn.
    assert west.conduits[f"{MINI_BASIS}Leiding_1"].line is not None
    assert oost.conduits[f"{MINI_BASIS}Leiding_1"].line is not None


def test_de_delen_dragen_samen_elke_triple(tmp_path: Path) -> None:
    """Geen triple raakt bij het knippen zoek; de vereniging dekt de bron.

    Losser dan de round-trip -- blanke knopen tellen hier niet mee -- maar het wijst een
    fout in de verdeling wel meteen aan de juiste kant aan.
    """
    delen = _geknipt(tmp_path)
    samen: rdflib.Graph = rdflib.Graph()
    for pad in delen:
        samen += _graaf(pad)
    bron = _graaf(MINI)

    vast = {
        (subject, predicaat, object_)
        for subject, predicaat, object_ in bron
        if isinstance(subject, rdflib.URIRef) and not isinstance(object_, rdflib.BNode)
    }
    ontbreekt = {drietal for drietal in vast if drietal not in samen}
    assert ontbreekt == set()


# --------------------------------------------------------------------------------------
# Geometrie die niet het gewone geval is
# --------------------------------------------------------------------------------------

KOP = (
    "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n"
    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
    "@prefix geo: <http://www.opengis.net/ont/geosparql#> .\n"
    f"@prefix gwsw: <{GWSW}> .\n"
    f"@prefix : <{MINI_BASIS}> .\n"
)


def _lijn(coordinaten: str, dimensie: str = ' srsDimension=\\"3\\"') -> str:
    """Een GML-lijnliteraal met deze coordinatentekst."""
    return (
        '"<gml:LineString xmlns:gml=\\"http://www.opengis.net/gml\\">'
        f"<gml:posList{dimensie}>{coordinaten}</gml:posList>"
        '</gml:LineString>"^^geo:gmlLiteral'
    )


def _klein(tmp_path: Path, lichaam: str, naam: str = "klein.ttl") -> Path:
    """Een piepkleine OroX met alleen wat de test nodig heeft."""
    pad = tmp_path / naam
    pad.write_text(KOP + lichaam, encoding="utf-8")
    return pad


def _heen_en_terug(tmp_path: Path, bron: Path) -> tuple[list[Path], rdflib.Graph]:
    """Knipt langs de minigrens en voegt weer samen; levert de delen en het resultaat."""
    delen = clip_orox(bron, MINI_GRENS, tmp_path / "delen", sleutel="gemeentenaam")
    doel = tmp_path / "terug.ttl"
    merge_orox(delen, doel)
    return delen, _graaf(doel)


def test_lijn_die_de_grens_twee_keer_kruist_valt_in_drie_stukken(tmp_path: Path) -> None:
    """Meer kruisingen, meer stukken -- en `merge_orox` naait ze alle drie terug."""
    coordinaten = "233000.00 581000.00 8.50 233040.00 581000.00 8.40 233010.00 581000.00 8.30"
    bron = _klein(
        tmp_path,
        ":L a gwsw:Gemengdriool ; gwsw:hasAspect :L_ori .\n"
        ":L_ori a gwsw:Leidingorientatie ; gwsw:hasAspect :L_lij .\n"
        f":L_lij a gwsw:Lijn ; gwsw:hasValue {_lijn(coordinaten)} .\n",
    )
    delen, terug = _heen_en_terug(tmp_path, bron)

    aantallen = {
        int(waarde)
        for pad in delen
        for waarde in _graaf(pad).objects(None, rdflib.URIRef(f"{KNIP}aantal"))
    }
    assert aantallen == {3}
    assert isomorphic(terug, _graaf(bron))


def test_knip_op_een_bestaande_vertex_voegt_geen_punt_toe(tmp_path: Path) -> None:
    """Valt de grens precies op een vertex, dan wordt die vertex gedeeld en niets ingevoegd.

    Zonder dit onderscheid zou `merge_orox` die vertex als knippunt wegsnoeien en een
    kortere lijn teruggeven dan de bron had.
    """
    coordinaten = "233000.00 581000.00 8.50 233020.00 581000.00 8.45 233040.00 581000.00 8.40"
    bron = _klein(
        tmp_path,
        ":L a gwsw:Gemengdriool ; gwsw:hasAspect :L_ori .\n"
        ":L_ori a gwsw:Leidingorientatie ; gwsw:hasAspect :L_lij .\n"
        f":L_lij a gwsw:Lijn ; gwsw:hasValue {_lijn(coordinaten)} .\n",
    )
    delen, terug = _heen_en_terug(tmp_path, bron)

    for pad in delen:
        assert (None, rdflib.URIRef(f"{KNIP}ingevoegdEinde"), None) not in _graaf(pad)
        stuk = next(
            str(waarde) for waarde in _graaf(pad).objects(None, rdflib.URIRef(f"{GWSW}hasValue"))
        )
        assert "233020.00 581000.00 8.45" in stuk  # de brontekst, niet een herberekend getal
    assert isomorphic(terug, _graaf(bron))


def test_lijn_zonder_srsdimension_wordt_ook_geknipt(tmp_path: Path) -> None:
    """Een tweedimensionale posList zonder srsDimension: de dimensie volgt uit de telling."""
    coordinaten = "233000.00 581000.00 233040.00 581000.00"
    bron = _klein(
        tmp_path,
        ":L a gwsw:Gemengdriool ; gwsw:hasAspect :L_ori .\n"
        ":L_ori a gwsw:Leidingorientatie ; gwsw:hasAspect :L_lij .\n"
        f":L_lij a gwsw:Lijn ; gwsw:hasValue {_lijn(coordinaten, dimensie='')} .\n",
    )
    delen, terug = _heen_en_terug(tmp_path, bron)

    assert len(delen) == 2
    assert isomorphic(terug, _graaf(bron))


def test_object_buiten_alle_vlakken_valt_niet_buiten_de_boot(tmp_path: Path) -> None:
    """Wat nergens in valt, gaat naar het dichtstbijzijnde vlak in plaats van nergens heen.

    Een grenslaag dekt zelden precies alles wat een export bevat; zonder deze terugval
    zou zo'n object bij de hereniging spoorloos zijn.
    """
    bron = _klein(
        tmp_path,
        ":Ver a gwsw:Inspectieput ; gwsw:hasAspect :Ver_ori .\n"
        ":Ver_ori a gwsw:Putorientatie ; gwsw:hasAspect :Ver_pnt .\n"
        ':Ver_pnt a gwsw:Punt ; gwsw:hasValue "<gml:Point xmlns:gml=\\"'
        'http://www.opengis.net/gml\\"><gml:pos>500000.00 581000.00</gml:pos>'
        '</gml:Point>"^^geo:gmlLiteral .\n'
        ":Weg a gwsw:Gemengdriool ; gwsw:hasAspect :Weg_ori .\n"
        ":Weg_ori a gwsw:Leidingorientatie ; gwsw:hasAspect :Weg_lij .\n"
        f":Weg_lij a gwsw:Lijn ; gwsw:hasValue "
        f"{_lijn('500000.00 581000.00 1.0 500010.00 581000.00 1.0')} .\n",
    )
    delen, terug = _heen_en_terug(tmp_path, bron)

    verdeling = [(_mini("Ver"), RDF.type, None) in _graaf(pad) for pad in delen]
    assert verdeling.count(True) == 1  # precies een vlak, en niet allebei
    assert isomorphic(terug, _graaf(bron))


def test_multipart_geometrie_wordt_niet_geknipt(tmp_path: Path) -> None:
    """Twee lijnen op een knoop: die gaat heel naar elk vlak dat hij raakt.

    Knippen zou hier twee stukkenreeksen op dezelfde knoop opleveren en die zijn bij de
    hereniging niet uit elkaar te houden. Heel meegeven kost een kopie en blijft exact.
    """
    bron = _klein(
        tmp_path,
        ":L a gwsw:Gemengdriool ; gwsw:hasAspect :L_ori .\n"
        ":L_ori a gwsw:Leidingorientatie ; gwsw:hasAspect :L_lij .\n"
        f":L_lij a gwsw:Lijn ; gwsw:hasValue "
        f"{_lijn('233000.00 581000.00 8.50 233010.00 581000.00 8.45')} ,\n"
        f"   {_lijn('233030.00 581000.00 8.40 233040.00 581000.00 8.35')} .\n",
    )
    delen, terug = _heen_en_terug(tmp_path, bron)

    for pad in delen:
        helft = _graaf(pad)
        assert (None, rdflib.URIRef(f"{KNIP}herkomst"), None) not in helft
        assert len(list(helft.objects(_mini("L_lij"), rdflib.URIRef(f"{GWSW}hasValue")))) == 2
    assert isomorphic(terug, _graaf(bron))


def _drie_vlakken(tmp_path: Path) -> Path:
    """Een grenslaag van drie vlakken naast elkaar: A, B en C, elk 60 m breed."""
    grens = tmp_path / "drie.geojson"
    grens.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"naam": naam},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [links, 580960.0],
                                    [links + 60.0, 580960.0],
                                    [links + 60.0, 581040.0],
                                    [links, 581040.0],
                                    [links, 580960.0],
                                ]
                            ],
                        },
                    }
                    for naam, links in (
                        ("A", 232960.0),
                        ("B", 233020.0),
                        ("C", 233080.0),
                    )
                ],
            }
        ),
        encoding="utf-8",
    )
    return grens


def test_blok_dat_verder_reikt_dan_zijn_stukken_neemt_de_lijn_niet_mee(tmp_path: Path) -> None:
    """Een orientatie met twee blanke geometrieknopen staat in meer vlakken dan de lijn.

    De lijn en het punt hangen aan dezelfde orientatie en zitten dus in hetzelfde blok:
    blanke knopen zijn documentgebonden en gaan altijd met hun houder mee. Het punt trekt
    dat blok naar een derde vlak waar de lijn geen enkel stuk heeft. Zonder toezicht zou
    de clip daar de hele ongeknipte lijn neerzetten en zou `merge_orox` er twee
    geometrieen van maken.
    """
    grens = _drie_vlakken(tmp_path)
    bron = _klein(
        tmp_path,
        ":L a gwsw:Gemengdriool ; gwsw:hasAspect :L_ori .\n"
        ":L_ori a gwsw:Leidingorientatie ;\n"
        f"  gwsw:hasAspect [ a gwsw:Lijn ; gwsw:hasValue "
        f"{_lijn('233000.00 581000.00 8.50 233040.00 581000.00 8.40')} ] ,\n"
        '  [ a gwsw:Punt ; gwsw:hasValue "<gml:Point xmlns:gml=\\"'
        'http://www.opengis.net/gml\\"><gml:pos>233100.00 581000.00</gml:pos>'
        '</gml:Point>"^^geo:gmlLiteral ] .\n',
    )
    delen = clip_orox(bron, grens, tmp_path / "delen", sleutel="naam")
    doel = tmp_path / "terug.ttl"
    merge_orox(delen, doel)

    lijnen = [
        sum(
            1
            for waarde in _graaf(pad).objects(None, rdflib.URIRef(f"{GWSW}hasValue"))
            if "LineString" in str(waarde)
        )
        for pad in delen
    ]
    assert lijnen == [1, 1, 0]  # A en B elk een stuk, C geen -- en zeker geen hele lijn
    assert isomorphic(_graaf(doel), _graaf(bron))


def test_onleesbare_geometrie_erft_de_kant_van_zijn_houder(tmp_path: Path) -> None:
    """Een kapotte GML-literaal zaait niets; het blok volgt dan gewoon zijn houder.

    De leeslaag meldt zo'n literaal in `GwswDataset.geometry_errors`; de clip hoeft er
    niet nog een tweede keer over te vallen, en zeker geen triple over te slaan.
    """
    bron = _klein(
        tmp_path,
        ":Put a gwsw:Inspectieput ; gwsw:hasAspect :Put_ori ; gwsw:hasPart :Stuk .\n"
        ":Put_ori a gwsw:Putorientatie ; gwsw:hasAspect :Put_pnt .\n"
        ':Put_pnt a gwsw:Punt ; gwsw:hasValue "<gml:Point xmlns:gml=\\"'
        'http://www.opengis.net/gml\\"><gml:pos>233000.00 581000.00</gml:pos>'
        '</gml:Point>"^^geo:gmlLiteral .\n'
        ":Stuk a gwsw:Putdeksel ; gwsw:hasAspect :Stuk_ori .\n"
        ":Stuk_ori a gwsw:Dekselorientatie ; gwsw:hasAspect :Stuk_pnt .\n"
        ':Stuk_pnt a gwsw:Punt ; gwsw:hasValue "dit is geen GML"^^geo:gmlLiteral .\n',
    )
    delen, terug = _heen_en_terug(tmp_path, bron)

    west, oost = (_graaf(pad) for pad in delen)
    assert (_mini("Stuk"), RDF.type, None) in west
    assert (_mini("Stuk"), RDF.type, None) not in oost
    assert isomorphic(terug, _graaf(bron))


def test_inverse_schrijfrichting_telt_ook_mee(tmp_path: Path) -> None:
    """`isPartOf`/`isAspectOf` zijn de andere kant van dezelfde rand en horen erbij.

    Het GWSW declareert ze als inverse; een export mag ze schrijven. Wie alleen de
    voorwaartse richting leest, zou het onderdeel als losstaand blok zien en het naar
    elk vlak sturen.
    """
    bron = _klein(
        tmp_path,
        ":Put a gwsw:Inspectieput .\n"
        ":Put_ori a gwsw:Putorientatie ; gwsw:isAspectOf :Put ; gwsw:hasAspect :Put_pnt .\n"
        ':Put_pnt a gwsw:Punt ; gwsw:hasValue "<gml:Point xmlns:gml=\\"'
        'http://www.opengis.net/gml\\"><gml:pos>233000.00 581000.00</gml:pos>'
        '</gml:Point>"^^geo:gmlLiteral .\n'
        ":Stuk a gwsw:Putdeksel ; gwsw:isPartOf :Put .\n",
    )
    delen, terug = _heen_en_terug(tmp_path, bron)

    west, oost = (_graaf(pad) for pad in delen)
    assert (_mini("Stuk"), RDF.type, None) in west
    assert (_mini("Stuk"), RDF.type, None) not in oost
    assert isomorphic(terug, _graaf(bron))


# --------------------------------------------------------------------------------------
# Randgevallen die de knip stil kortere geometrie konden laten opleveren
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("naam", "coordinaten", "dimensie"),
    [
        (
            "eind-3d",
            "233000.00 581000.00 8.50 233040.00 581000.00 8.40 233040.00 581000.00 8.40",
            ' srsDimension=\\"3\\"',
        ),
        (
            "begin-3d",
            "233000.00 581000.00 8.50 233000.00 581000.00 8.50 233040.00 581000.00 8.40",
            ' srsDimension=\\"3\\"',
        ),
        ("eind-2d", "233000.00 581000.00 233040.00 581000.00 233040.00 581000.00", ""),
        ("begin-2d", "233000.00 581000.00 233000.00 581000.00 233040.00 581000.00", ""),
    ],
)
def test_herhaald_uiteinde_overleeft_de_knip(
    tmp_path: Path, naam: str, coordinaten: str, dimensie: str
) -> None:
    """Een lijn met een dubbel begin- of eindpunt komt met dat dubbele punt terug.

    De laatste twee vertices vallen dan samen; de vertex die de knip als "de vertex op
    deze afstand" aanwijst is de *eerste* binnen de tolerantie en dat is bij een dubbel
    eindpunt niet de laatste. Zonder klem op de uiteinden valt het herhaalde punt buiten
    elk stuk en levert de hereniging een kortere geometrie op -- zonder fout, en dat is
    het ergste soort verlies.
    """
    bron = _klein(
        tmp_path,
        ":L a gwsw:Gemengdriool ; gwsw:hasAspect :L_ori .\n"
        ":L_ori a gwsw:Leidingorientatie ; gwsw:hasAspect :L_lij .\n"
        f":L_lij a gwsw:Lijn ; gwsw:hasValue {_lijn(coordinaten, dimensie)} .\n",
        naam=f"{naam}.ttl",
    )
    _, terug = _heen_en_terug(tmp_path, bron)

    hersteld = next(
        str(waarde) for waarde in terug.objects(_mini("L_lij"), rdflib.URIRef(f"{GWSW}hasValue"))
    )
    assert coordinaten in hersteld
    assert isomorphic(terug, _graaf(bron))


def test_verwijzing_uit_een_derde_vlak_naar_een_geknipte_lijn_blijft_bewaard(
    tmp_path: Path,
) -> None:
    """Een put in vlak C wijst naar een lijn die alleen in A en B stukken heeft.

    Bij `hasPart`/`hasAspect` mag zo'n verwijzing in C wegvallen: die rand hoort bij het
    onderdeel en wordt in A en B geschreven, waar het onderdeel staat. Elk *ander*
    predicaat heeft die tweede thuisbasis niet -- de triple staat alleen in C -- en stil
    overslaan zou hem uit de hereniging laten verdwijnen. Hij blijft daarom staan en
    wijst naar de ongeknipte naam, net als de `hasConnection` die over de knip heen wijst.
    """
    grens = _drie_vlakken(tmp_path)
    bron = _klein(
        tmp_path,
        ":L a gwsw:Gemengdriool ; gwsw:hasAspect :L_ori .\n"
        ":L_ori a gwsw:Leidingorientatie ; gwsw:hasAspect :L_lij .\n"
        f":L_lij a gwsw:Lijn ; gwsw:hasValue "
        f"{_lijn('233000.00 581000.00 8.50 233040.00 581000.00 8.40')} .\n"
        ":Y a gwsw:Inspectieput ; gwsw:hasAspect :Y_ori ;\n"
        "  gwsw:hasConnection :L_lij ; rdfs:seeAlso :L_lij .\n"
        ":Y_ori a gwsw:Putorientatie ; gwsw:hasAspect :Y_pnt .\n"
        ':Y_pnt a gwsw:Punt ; gwsw:hasValue "<gml:Point xmlns:gml=\\"'
        'http://www.opengis.net/gml\\"><gml:pos>233100.00 581000.00</gml:pos>'
        '</gml:Point>"^^geo:gmlLiteral .\n',
    )
    delen = clip_orox(bron, grens, tmp_path / "delen", sleutel="naam")
    doel = tmp_path / "terug.ttl"
    merge_orox(delen, doel)

    derde = _graaf(delen[2])
    assert (_mini("Y"), rdflib.URIRef(f"{GWSW}hasConnection"), _mini("L_lij")) in derde
    assert (_mini("Y"), rdflib.RDFS.seeAlso, _mini("L_lij")) in derde
    assert isomorphic(_graaf(doel), _graaf(bron))


def test_poslist_met_dubbele_spaties_wordt_niet_geknipt(tmp_path: Path) -> None:
    """De knip snijdt tekstplakjes; wie de scheiders normaliseert, breekt de belofte.

    De hereniging zet de tokens met een enkele spatie aaneen. Draagt de bron dubbele
    spaties, newlines of randspaties in de posList, dan zouden de *getallen* wel exact
    terugkomen maar de scheiders niet -- en dan is de hereniging niet meer isomorf. De
    knip weigert daarom te knippen wat niet al genormaliseerd is: de lijn gaat heel naar
    elk vlak dat hij raakt.
    """
    coordinaten = "233000.00 581000.00 8.50  233040.00 581000.00 8.40"
    bron = _klein(
        tmp_path,
        ":L a gwsw:Gemengdriool ; gwsw:hasAspect :L_ori .\n"
        ":L_ori a gwsw:Leidingorientatie ; gwsw:hasAspect :L_lij .\n"
        f":L_lij a gwsw:Lijn ; gwsw:hasValue {_lijn(coordinaten)} .\n",
    )
    delen, terug = _heen_en_terug(tmp_path, bron)

    for pad in delen:
        helft = _graaf(pad)
        assert (None, rdflib.URIRef(f"{KNIP}herkomst"), None) not in helft
        heel = str(helft.value(_mini("L_lij"), rdflib.URIRef(f"{GWSW}hasValue")))
        assert coordinaten in heel
    assert isomorphic(terug, _graaf(bron))


def test_twee_stukken_in_een_helft_melden_zich_als_multipart(tmp_path: Path) -> None:
    """Een lijn die heen en weer over de grens loopt, laat in een helft twee stukken na.

    Die twee stukken sluiten niet op elkaar aan -- er zit per definitie een stuk uit de
    andere helft tussen -- dus er valt in die helft geen enkele lijn van te maken. Wat de
    helft dan draagt is een leiding met een meerdelige geometrie, en dat is precies wat
    twee `gwsw:Lijn`-aspecten onder een orientatie in OroX betekenen. De leeslaag leest
    het ook zo: `Conduit.multipart` staat aan, dus er komt geen halve leiding uit die
    zich als een hele voordoet.
    """
    from gwsw_orox_helpers.dataset import load_dataset

    coordinaten = "233000.00 581000.00 8.50 233040.00 581000.00 8.40 233010.00 581000.00 8.30"
    bron = _klein(
        tmp_path,
        ":L a gwsw:Gemengdriool ; gwsw:hasAspect :L_ori .\n"
        ":L_ori a gwsw:Leidingorientatie ; gwsw:hasAspect :L_lij .\n"
        f":L_lij a gwsw:Lijn ; gwsw:hasValue {_lijn(coordinaten)} .\n",
    )
    delen, terug = _heen_en_terug(tmp_path, bron)

    west = _graaf(delen[0])
    stukken = [
        str(waarde)
        for waarde in west.objects(None, rdflib.URIRef(f"{GWSW}hasValue"))
        if "LineString" in str(waarde)
    ]
    assert len(stukken) == 2, "de heen- en de terugweg liggen allebei in Mini-West"
    # Het merk op de houder zegt het ook: deze orientatie draagt stukken, geen hele lijn.
    assert (_mini("L_ori"), rdflib.URIRef(f"{KNIP}geknipt"), None) in west

    gelezen = load_dataset(delen[0])
    leiding = gelezen.conduits[f"{MINI_BASIS}L"]
    assert leiding.multipart is True
    assert leiding.line is not None
    assert not gelezen.geometry_errors
    assert isomorphic(terug, _graaf(bron))


def test_multi_geometrie_in_een_literaal_wordt_niet_geknipt(tmp_path: Path) -> None:
    """Een `gml:MultiCurve` in *een* literaal telt net zo goed als multi-geometrie.

    De shapely-lezer ziet van zo'n literaal alleen het eerste deel; knippen zou dus een
    tekstplakje uit het eerste deel snijden en de rest ongemoeid in beide helften laten
    staan. Hij gaat daarom heel naar elk vlak dat hij raakt, net als een knoop met
    meerdere GML-literalen.
    """
    multi = (
        '"<gml:MultiCurve xmlns:gml=\\"http://www.opengis.net/gml\\" '
        'srsName=\\"EPSG:28992\\">'
        '<gml:curveMember><gml:LineString><gml:posList srsDimension=\\"3\\">'
        "233000.00 581000.00 8.50 233040.00 581000.00 8.40"
        "</gml:posList></gml:LineString></gml:curveMember>"
        '<gml:curveMember><gml:LineString><gml:posList srsDimension=\\"3\\">'
        "233050.00 581000.00 8.30 233060.00 581000.00 8.20"
        "</gml:posList></gml:LineString></gml:curveMember>"
        '</gml:MultiCurve>"^^geo:gmlLiteral'
    )
    bron = _klein(
        tmp_path,
        ":L a gwsw:Gemengdriool ; gwsw:hasAspect :L_ori .\n"
        ":L_ori a gwsw:Leidingorientatie ; gwsw:hasAspect :L_lij .\n"
        f":L_lij a gwsw:Lijn ; gwsw:hasValue {multi} .\n",
    )
    delen, terug = _heen_en_terug(tmp_path, bron)

    for pad in delen:
        helft = _graaf(pad)
        assert (None, rdflib.URIRef(f"{KNIP}herkomst"), None) not in helft
        heel = str(helft.value(_mini("L_lij"), rdflib.URIRef(f"{GWSW}hasValue")))
        assert "MultiCurve" in heel and "233060.00" in heel
    assert isomorphic(terug, _graaf(bron))


def test_lijn_langs_de_grens_valt_niet_uiteen(tmp_path: Path) -> None:
    """Een lijn die over de vlakgrens zelf loopt, snijdt die grens niet.

    De doorsnede met de vlakrand is dan geen punt maar een lijnstuk; de uiteinden ervan
    zijn de enige kandidaat-knippunten, en die vallen hier op het begin van de lijn en op
    de hoek van het vlak.
    """
    coordinaten = "233020.00 580980.00 8.50 233020.00 581100.00 8.40"
    bron = _klein(
        tmp_path,
        ":L a gwsw:Gemengdriool ; gwsw:hasAspect :L_ori .\n"
        ":L_ori a gwsw:Leidingorientatie ; gwsw:hasAspect :L_lij .\n"
        f":L_lij a gwsw:Lijn ; gwsw:hasValue {_lijn(coordinaten)} .\n",
    )
    delen, terug = _heen_en_terug(tmp_path, bron)

    geknipt = [
        pad for pad in delen if (None, rdflib.URIRef(f"{KNIP}herkomst"), None) in _graaf(pad)
    ]
    assert geknipt == []
    assert isomorphic(terug, _graaf(bron))


def test_lijn_die_een_vlak_in_en_weer_uit_gaat(tmp_path: Path) -> None:
    """Een recht stuk dat een vlak binnenkomt en weer verlaat, kruist de rand twee keer.

    De doorsnede is dan een puntenpaar. De staart voorbij het laatste vlak hoort bij het
    dichtstbijzijnde vlak en wordt met het stuk ervoor samengevoegd, want dat ligt daar
    ook: twee stukken, niet drie.
    """
    coordinaten = "233000.00 581000.00 8.50 233100.00 581000.00 8.20"
    bron = _klein(
        tmp_path,
        ":L a gwsw:Gemengdriool ; gwsw:hasAspect :L_ori .\n"
        ":L_ori a gwsw:Leidingorientatie ; gwsw:hasAspect :L_lij .\n"
        f":L_lij a gwsw:Lijn ; gwsw:hasValue {_lijn(coordinaten)} .\n",
    )
    delen, terug = _heen_en_terug(tmp_path, bron)

    aantallen = {
        int(waarde)
        for pad in delen
        for waarde in _graaf(pad).objects(None, rdflib.URIRef(f"{KNIP}aantal"))
    }
    assert aantallen == {2}
    assert isomorphic(terug, _graaf(bron))


def test_lijn_met_een_vierde_coordinaat_wordt_niet_geknipt(tmp_path: Path) -> None:
    """Bij een andere srsDimension dan 2 of 3 valt er geen tekstplakje te knippen.

    De knip verdeelt de tokenreeks in punten van twee of drie getallen; een vierde getal
    per punt (een meetwaarde, een tijdstip) zou stil op de verkeerde plaats gesneden
    worden. Zo'n lijn gaat daarom heel naar elk vlak dat hij raakt.
    """
    coordinaten = "233000.00 581000.00 8.50 1.00 233040.00 581000.00 8.40 2.00"
    bron = _klein(
        tmp_path,
        ":L a gwsw:Gemengdriool ; gwsw:hasAspect :L_ori .\n"
        ":L_ori a gwsw:Leidingorientatie ; gwsw:hasAspect :L_lij .\n"
        f":L_lij a gwsw:Lijn ; gwsw:hasValue {_lijn(coordinaten, ' srsDimension=\\"4\\"')} .\n",
    )
    delen, terug = _heen_en_terug(tmp_path, bron)

    for pad in delen:
        helft = _graaf(pad)
        assert (None, rdflib.URIRef(f"{KNIP}herkomst"), None) not in helft
        assert coordinaten in str(helft.value(_mini("L_lij"), rdflib.URIRef(f"{GWSW}hasValue")))
    assert isomorphic(terug, _graaf(bron))


def test_lijn_zonder_lengte_gaat_heel_naar_het_dichtstbijzijnde_vlak(tmp_path: Path) -> None:
    """Twee gelijke coordinaten geven een lijn zonder lengte; daar valt niets te knippen.

    Hij ligt hier ook nog eens buiten elk vlak, dus er is geen vlak dat hem raakt en de
    terugval op het dichtstbijzijnde vlak is het enige dat hem in een deel houdt.
    """
    coordinaten = "500000.00 581000.00 1.00 500000.00 581000.00 1.00"
    bron = _klein(
        tmp_path,
        ":L a gwsw:Gemengdriool ; gwsw:hasAspect :L_ori .\n"
        ":L_ori a gwsw:Leidingorientatie ; gwsw:hasAspect :L_lij .\n"
        f":L_lij a gwsw:Lijn ; gwsw:hasValue {_lijn(coordinaten)} .\n",
    )
    delen, terug = _heen_en_terug(tmp_path, bron)

    verdeling = [(_mini("L"), RDF.type, None) in _graaf(pad) for pad in delen]
    assert verdeling.count(True) == 1
    assert isomorphic(terug, _graaf(bron))


# --------------------------------------------------------------------------------------
# De aanname onder de hereniging
# --------------------------------------------------------------------------------------


_GML = 'xmlns:gml="http://www.opengis.net/gml"'


def _lijnliteraal(coordinaten: str, dimensie: str = "") -> str:
    """Een GML-lijnliteraal als gewone tekst (niet als TTL-fragment)."""
    return (
        f"<gml:LineString {_GML}><gml:posList{dimensie}>{coordinaten}"
        "</gml:posList></gml:LineString>"
    )


@pytest.mark.parametrize(
    ("naam", "sjabloon", "stap"),
    [
        ("3d-met-srsdimension", _lijnliteraal("1 2 30 4 5 60", ' srsDimension="3"'), 3),
        ("2d-zonder-srsdimension", _lijnliteraal("1 2 4 5"), 2),
        ("drievoud-zonder-srsdimension", _lijnliteraal("1 2 3 4 5 6 7 8 9"), 3),
        ("vierde-getal-per-punt", _lijnliteraal("1 2 3 4 5 6 7 8", ' srsDimension="4"'), 4),
        ("los-punt", f"<gml:Point {_GML}><gml:pos>1 2 30</gml:pos></gml:Point>", 3),
    ],
)
def test_stapgrootte_volgt_de_telling_en_niet_de_srsdimension(
    naam: str, sjabloon: str, stap: int
) -> None:
    """Gedragsbehoud: de token/punt-verhouding is een opzettelijke round-trip-keuze.

    `_stapgrootte` bepaalt hoeveel getallen er per punt van een stuk gesnoeid worden en
    `_knip_lijn` bepaalt met dezelfde verhouding hoe hij de tokens over de stukken
    verdeelt. Lopen die twee ooit uiteen -- de een telt, de ander leest de srsDimension --
    dan snoeit de hereniging op de verkeerde plaats en komt er stilzwijgend een geometrie
    uit die niemand geschreven heeft. Deze uitkomsten liggen daarom per invoer vast.
    """
    from gwsw_orox_helpers.clip.merge import _stapgrootte

    assert _stapgrootte(sjabloon) == stap


@pytest.mark.parametrize(
    ("naam", "sjabloon", "melding"),
    [
        ("onleesbare-gml", "dit is geen GML", "0 coordinaatwaarden op 0 punten"),
        (
            "vlak-heeft-geen-coords",
            f"<gml:Polygon {_GML}><gml:exterior><gml:LinearRing>"
            '<gml:posList srsDimension="2">0 0 0 1 1 1 0 0</gml:posList>'
            "</gml:LinearRing></gml:exterior></gml:Polygon>",
            "8 coordinaatwaarden op 0 punten",
        ),
        ("lege-lijst", _lijnliteraal(""), "0 coordinaatwaarden op 0 punten"),
    ],
)
def test_stapgrootte_meldt_wat_hij_niet_kan_aflezen(naam: str, sjabloon: str, melding: str) -> None:
    """Gedragsbehoud: dezelfde fout met dezelfde getallen erin.

    Een vlak heeft geen `.coords` (shapely gooit `NotImplementedError`) en een onleesbare
    literaal geen punten; in allebei de gevallen valt er niets te raden. De getallen in de
    melding zijn wat de auteur bij een deel van elders nodig heeft om te zien waarom.
    """
    from gwsw_orox_helpers.clip.merge import _stapgrootte

    with pytest.raises(DatasetError, match=melding):
        _stapgrootte(sjabloon)


def test_blanke_knooplabels_overleven_de_serializer() -> None:
    """`merge_orox` leunt erop dat pyoxigraph labels van blanke knopen laat staan.

    De clip geeft elke blanke knoop een vaste naam en herkent hem in de delen aan die
    naam terug. Zou pyoxigraph bij het schrijven of lezen hernoemen, dan viel de
    hereniging stil uiteen; deze test legt de eigenschap vast waar dat op rust.
    """
    import io

    bron = '@prefix : <http://x#> .\n:a :p _:b17 .\n_:b17 :q "v" .\n'
    quads = list(pyoxigraph.parse(bron, format=pyoxigraph.RdfFormat.TURTLE))
    buffer = io.BytesIO()
    pyoxigraph.serialize(quads, buffer, pyoxigraph.RdfFormat.TURTLE)
    terug = list(pyoxigraph.parse(buffer.getvalue().decode(), format=pyoxigraph.RdfFormat.TURTLE))

    labels = {
        term.value
        for quad in terug
        for term in (quad.subject, quad.object)
        if isinstance(term, pyoxigraph.BlankNode)
    }
    assert labels == {"b17"}


# --------------------------------------------------------------------------------------
# Foutpaden
# --------------------------------------------------------------------------------------


def _grenslaag(tmp_path: Path, inhoud: object) -> Path:
    pad = tmp_path / "grens.geojson"
    pad.write_text(json.dumps(inhoud), encoding="utf-8")
    return pad


def test_ontbrekende_grenslaag_is_een_dataseterror(tmp_path: Path) -> None:
    with pytest.raises(DatasetError, match="kan niet gelezen worden"):
        clip_orox(MINI, tmp_path / "weg.geojson", tmp_path / "uit", sleutel="naam")


def test_onleesbare_grenslaag_is_een_dataseterror(tmp_path: Path) -> None:
    pad = tmp_path / "grens.geojson"
    pad.write_text("{ dit is geen json", encoding="utf-8")
    with pytest.raises(DatasetError, match="geen leesbare GeoJSON") as gevangen:
        clip_orox(MINI, pad, tmp_path / "uit", sleutel="naam")
    # De gewone JSON-fout deelt zijn `except`-blok sinds #22 met `RecursionError`; deze
    # twee regels pinnen dat zijn melding daar niet van verschoof.
    assert isinstance(gevangen.value.__cause__, json.JSONDecodeError)
    assert str(gevangen.value) == f"{pad}: geen leesbare GeoJSON ({gevangen.value.__cause__})."


def test_diep_geneste_grenslaag_is_een_dataseterror(tmp_path: Path) -> None:
    """20000x `[` laat `json.loads` een kale `RecursionError` gooien (issue #22).

    Die ontsnapte uit de publieke `clip_orox`, terwijl het hele grenzenpad `DatasetError`
    belooft. `pytest.raises(DatasetError)` legt dat allebei vast: hij faalt zowel als er
    niets vliegt als wanneer de `RecursionError` er kaal doorheen komt.
    """
    pad = tmp_path / "grens.geojson"
    pad.write_text("[" * 20000, encoding="utf-8")
    with pytest.raises(DatasetError, match="geen leesbare GeoJSON") as gevangen:
        clip_orox(MINI, pad, tmp_path / "uit", sleutel="naam")
    assert isinstance(gevangen.value.__cause__, RecursionError)


def test_grenslaag_zonder_vlakken_is_een_dataseterror(tmp_path: Path) -> None:
    pad = _grenslaag(tmp_path, {"type": "FeatureCollection", "features": []})
    with pytest.raises(DatasetError, match="geen features"):
        clip_orox(MINI, pad, tmp_path / "uit", sleutel="naam")


def test_vlak_zonder_sleutel_is_een_dataseterror(tmp_path: Path) -> None:
    pad = _grenslaag(
        tmp_path,
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"anders": "x"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
                    },
                }
            ],
        },
    )
    with pytest.raises(DatasetError, match="draagt geen 'naam'"):
        clip_orox(MINI, pad, tmp_path / "uit", sleutel="naam")


def test_twee_vlakken_met_dezelfde_naam_is_een_dataseterror(tmp_path: Path) -> None:
    vlak = {
        "type": "Feature",
        "properties": {"naam": "gelijk"},
        "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
    }
    pad = _grenslaag(tmp_path, {"type": "FeatureCollection", "features": [vlak, vlak]})
    with pytest.raises(DatasetError, match="op meer dan een vlak"):
        clip_orox(MINI, pad, tmp_path / "uit", sleutel="naam")


def test_vlak_dat_geen_vlak_is_is_een_dataseterror(tmp_path: Path) -> None:
    pad = _grenslaag(
        tmp_path,
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"naam": "lijn"},
                    "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
                }
            ],
        },
    )
    with pytest.raises(DatasetError, match="geen \\(multi\\)vlak"):
        clip_orox(MINI, pad, tmp_path / "uit", sleutel="naam")


def test_vlak_zonder_geometrie_is_een_dataseterror(tmp_path: Path) -> None:
    pad = _grenslaag(
        tmp_path,
        {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {"naam": "leeg"}}],
        },
    )
    with pytest.raises(DatasetError, match="geen leesbare geometrie"):
        clip_orox(MINI, pad, tmp_path / "uit", sleutel="naam")


def test_diep_geneste_geometrie_is_een_dataseterror(tmp_path: Path) -> None:
    """Dezelfde lek als in `test_diep_geneste_grenslaag...`, een stap verderop (issue #22).

    De twee grenzen liggen niet gelijk: de C-scanner van `json` bewaakt de C-stack (hier
    ~4990 niveaus diep), terwijl shapely's `shape()` gewone Python-recursie is en dus op
    `sys.getrecursionlimit()` (1000) stukloopt. Een `GeometryCollection` van 2000 diep
    valt daarom precies tussen de twee in: de JSON komt er nog door, de geometrie niet.
    """
    assert sys.getrecursionlimit() < 2000, "de diepte hieronder gaat uit van de standaardlimiet"
    geometrie: dict[str, object] = {"type": "Point", "coordinates": [0, 0]}
    for _ in range(2000):
        geometrie = {"type": "GeometryCollection", "geometries": [geometrie]}
    # De andere helft van de vangrail, en ze is de C-stack en niet `getrecursionlimit()`:
    # deze regel valt om zodra 2000 niveaus voor `json` te diep worden, zodat een falen niet
    # als "geen leesbare GeoJSON" op de verkeerde tak zou wijzen.
    json.loads(json.dumps(geometrie))
    pad = _grenslaag(
        tmp_path,
        {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {"naam": "diep"}, "geometry": geometrie}
            ],
        },
    )
    with pytest.raises(DatasetError, match="geen leesbare geometrie") as gevangen:
        clip_orox(MINI, pad, tmp_path / "uit", sleutel="naam")
    assert isinstance(gevangen.value.__cause__, RecursionError)


def test_bron_met_een_knipnaam_is_een_dataseterror(tmp_path: Path) -> None:
    """Een bron die zelf al `__knip<n>`-namen draagt, is na hereniging niet te scheiden."""
    bron = tmp_path / "botsing.ttl"
    bron.write_text(
        "@prefix : <http://x#> .\n@prefix gwsw: <http://data.gwsw.nl/1.6/totaal/> .\n"
        ":a__knip0 a gwsw:Lijn .\n",
        encoding="utf-8",
    )
    with pytest.raises(DatasetError, match="staart die de clip zelf"):
        clip_orox(bron, MINI_GRENS, tmp_path / "uit", sleutel="gemeentenaam")


def test_merge_zonder_delen_is_een_dataseterror(tmp_path: Path) -> None:
    with pytest.raises(DatasetError, match="geen delen opgegeven"):
        merge_orox([], tmp_path / "nooit.ttl")


def test_merge_van_een_onvolledige_set_is_een_dataseterror(tmp_path: Path) -> None:
    """Ontbreekt er een stuk, dan zou de geometrie korter terugkomen dan ze was."""
    delen = _geknipt(tmp_path)
    with pytest.raises(DatasetError, match="ontbreken de stukken"):
        merge_orox([delen[0]], tmp_path / "nooit.ttl")


def test_knipstuk_zonder_volgnummer_is_een_dataseterror(tmp_path: Path) -> None:
    """Een half merk is geen merk; zonder volgnummer valt er niets terug te leggen."""
    deel = tmp_path / "stuk.ttl"
    deel.write_text(
        f"@prefix : <http://x#> .\n@prefix knip: <{KNIP}> .\n"
        f"@prefix gwsw: <{GWSW}> .\n@prefix geo: <http://www.opengis.net/ont/geosparql#> .\n"
        ':a__knip0 knip:herkomst "http://x#a" ;\n'
        '  gwsw:hasValue "<gml:LineString><gml:posList>1 2 3 4</gml:posList></gml:LineString>"'
        "^^geo:gmlLiteral .\n",
        encoding="utf-8",
    )
    with pytest.raises(DatasetError, match="onvolledig of onleesbaar"):
        merge_orox([deel], tmp_path / "nooit.ttl")


def test_knipstuk_zonder_geometrie_is_een_dataseterror(tmp_path: Path) -> None:
    """Een stuk zonder GML-literaal draagt niets om aaneen te naaien."""
    deel = tmp_path / "stuk.ttl"
    deel.write_text(
        f"@prefix : <http://x#> .\n@prefix knip: <{KNIP}> .\n"
        ':a__knip0 knip:herkomst "http://x#a" ; knip:volgnummer 0 ; knip:aantal 1 .\n',
        encoding="utf-8",
    )
    with pytest.raises(DatasetError, match="draagt geen GML-geometrie"):
        merge_orox([deel], tmp_path / "nooit.ttl")


def test_knipstuk_met_een_onleesbare_geometrie_is_een_dataseterror(tmp_path: Path) -> None:
    """Zonder leesbare geometrie is niet te zeggen hoeveel getallen er op een punt gaan.

    Het aaneen naaien knipt per punt van de tokenreeks; raadt het daar 2 waar de bron 3
    bedoelde, dan komt er een geometrie uit die niemand ooit geschreven heeft. Dat is
    erger dan een fout, dus is het een fout.
    """
    deel = tmp_path / "stuk.ttl"
    deel.write_text(
        f"@prefix : <http://x#> .\n@prefix knip: <{KNIP}> .\n"
        f"@prefix gwsw: <{GWSW}> .\n@prefix geo: <http://www.opengis.net/ont/geosparql#> .\n"
        ':a__knip0 knip:herkomst "http://x#a" ; knip:volgnummer 0 ; knip:aantal 1 ;\n'
        '  gwsw:hasValue "dit is geen GML"^^geo:gmlLiteral .\n',
        encoding="utf-8",
    )
    with pytest.raises(DatasetError, match="hoeveel getallen er op een punt"):
        merge_orox([deel], tmp_path / "nooit.ttl")


def test_knippunt_zonder_bruikbare_hoogte_is_een_dataseterror() -> None:
    """De hoogte van een ingevoegd knippunt wordt niet verzonnen maar gemeld.

    Allebei deze gevallen horen niet voor te kunnen komen: de knip vraagt alleen om een z
    als de literaal er drie getallen per punt in heeft staan, en dan levert `parse_gml_z`
    ook drie. Een verzonnen `0.00` in de delen zou wel meteen als NAP-hoogte gelezen
    worden, dus zegt de knip liever dat zijn aanname niet opgaat.
    """
    from gwsw_orox_helpers.clip.knip import _hoogte

    with pytest.raises(DatasetError, match="geen hoogte"):
        _hoogte([0.0, 10.0], [None, None], 5.0)
    with pytest.raises(DatasetError, match="geen hoogte"):
        _hoogte([0.0, 0.0], [1.0, 2.0], 5.0)


def test_stukken_uit_verschillende_knipbeurten_is_een_dataseterror(tmp_path: Path) -> None:
    """Twee stukken die een ander totaal noemen, horen niet bij elkaar."""
    geometrie = (
        '"<gml:LineString><gml:posList>1 2 3 4</gml:posList></gml:LineString>"^^geo:gmlLiteral'
    )
    deel = tmp_path / "stuk.ttl"
    deel.write_text(
        f"@prefix : <http://x#> .\n@prefix knip: <{KNIP}> .\n"
        f"@prefix gwsw: <{GWSW}> .\n@prefix geo: <http://www.opengis.net/ont/geosparql#> .\n"
        f':a__knip0 knip:herkomst "http://x#a" ; knip:volgnummer 0 ; knip:aantal 2 ;'
        f" gwsw:hasValue {geometrie} .\n"
        f':a__knip1 knip:herkomst "http://x#a" ; knip:volgnummer 1 ; knip:aantal 3 ;'
        f" gwsw:hasValue {geometrie} .\n",
        encoding="utf-8",
    )
    with pytest.raises(DatasetError, match="verschillende aantallen"):
        merge_orox([deel], tmp_path / "nooit.ttl")


# --------------------------------------------------------------------------------------
# De echte exports
# --------------------------------------------------------------------------------------


def test_juinen_round_trip_is_isomorf(tmp_path: Path) -> None:
    """De voorbeeldexport (119 kB) overleeft knip en hereniging ongeschonden.

    Juinen ligt niet in De Wolden of Hoogeveen -- zijn coordinaten liggen rond
    x=168000-169100, y=442500-443300 -- dus de gemeentegrenzenfixture zou hem in zijn
    geheel naar het dichtstbijzijnde vlak schuiven en er niets te knippen overlaten. Hij
    krijgt daarom `juinen_grens.geojson`: twee rechthoeken die zijn eigen omhullende bij
    x=168540 in tweeen delen, dwars door een handvol leidingen heen.
    """
    delen = clip_orox(JUINEN, JUINEN_GRENS, tmp_path / "delen", sleutel="gemeentenaam")
    doel = tmp_path / "juinen_terug.ttl"
    merge_orox(delen, doel)

    assert len(delen) == 2
    assert isomorphic(_graaf(doel), _graaf(JUINEN))


def test_juinen_kent_grenskruisende_leidingen(tmp_path: Path) -> None:
    """De Juinen-grens loopt dwars door leidingen heen; anders toetst de knip niets."""
    delen = clip_orox(JUINEN, JUINEN_GRENS, tmp_path / "delen", sleutel="gemeentenaam")
    herkomsten = set()
    for pad in delen:
        for waarde in _graaf(pad).objects(None, rdflib.URIRef(f"{KNIP}herkomst")):
            herkomsten.add(str(waarde))
    assert len(herkomsten) >= 1


def _vingerafdruk(pad: Path) -> tuple[int, int, int]:
    """(aantal triples, aantal blanke knopen, ordeloze vingerafdruk van de triples).

    De vingerafdruk is de som van een 128-bits hash per triple. Dat is een
    volgorde-onafhankelijke vergelijking van twee grafen die exact is zolang er geen
    blanke knopen in staan -- en dat aantal komt er daarom bij terug, zodat de test kan
    weigeren te oordelen als die aanname niet opgaat.
    """
    import hashlib

    triples = 0
    blanken = 0
    som = 0
    for quad in pyoxigraph.parse(path=pad, format=pyoxigraph.RdfFormat.TURTLE):
        triples += 1
        regel = []
        for term in (quad.subject, quad.predicate, quad.object):
            if isinstance(term, pyoxigraph.BlankNode):
                blanken += 1
            regel.append(repr(term))
        digest = hashlib.blake2b("\x1f".join(regel).encode("utf-8"), digest_size=16).digest()
        som = (som + int.from_bytes(digest, "big")) % (1 << 128)
    return triples, blanken, som


@pytest.mark.zwaar
@pytest.mark.skipif(not DEWOLDEN.exists(), reason="de 112 MB-export ligt niet op deze machine")
def test_dewoldenhoogeveen_knipt_in_twee_en_komt_heel_terug(tmp_path: Path) -> None:
    """De 112 MB-export langs de echte gemeentegrenzen: twee delen, en weer een geheel.

    Op deze schaal is `rdflib.compare.isomorphic` geen optie -- de canonicalisatie zou
    op 1,9 miljoen triples omvallen. Deze export draagt geen enkele blanke knoop (alles
    is benoemd), en dan is een ordeloze vingerafdruk van de triples wel een *exacte*
    graafvergelijking: hij toetst hetzelfde als isomorfie zonder de canonicalisatie. De
    tellingen en de bestandsgrootte staan er als leesbare cijfers naast.

    De groottevergelijking gaat eerlijk serializer-tegen-serializer -- `schrijf_orox`
    van de bron, niet de bron zelf -- want de serializer schrijft nu eenmaal compacter
    dan BrutIS (0,911x, zie het verslag bij #2) en dat verschil is geen verlies.
    """
    from gwsw_orox_helpers.schrijven import schrijf_orox

    delen = clip_orox(
        DEWOLDEN,
        DEWOLDEN_GRENS,
        tmp_path / "delen",
        sleutel="gemeentenaam",
        fallback_encoding="cp850",
    )
    samen = tmp_path / "samen.ttl"
    merge_orox(delen, samen)

    ijk = tmp_path / "ijk.ttl"
    schrijf_orox(DEWOLDEN, ijk, fallback_encoding="cp850")

    ijk_triples, ijk_blanken, ijk_som = _vingerafdruk(ijk)
    samen_triples, _, samen_som = _vingerafdruk(samen)
    _, ijk_klassen = _tellingen(ijk)
    _, samen_klassen = _tellingen(samen)
    per_deel = [_tellingen(pad) for pad in delen]
    kruisingen = {
        str(waarde)
        for pad in delen
        for waarde in _graaf(pad).objects(None, rdflib.URIRef(f"{KNIP}herkomst"))
    }
    verhouding = samen.stat().st_size / ijk.stat().st_size
    som_objecten = sum(sum(klassen.values()) for _, klassen in per_deel)

    print(
        f"\ndelen={[pad.name for pad in delen]}"
        f"\ntriples ijk={ijk_triples} samen={samen_triples}"
        f"\nvingerafdruk gelijk={ijk_som == samen_som} (blanke knopen in de bron: {ijk_blanken})"
        f"\nobjecten met GWSW-type ijk={sum(ijk_klassen.values())} "
        f"samen={sum(samen_klassen.values())}"
        f"\nGWSW-klassen ijk={len(ijk_klassen)} samen={len(samen_klassen)}"
        f"\ngrenskruisende leidingen={len(kruisingen)}"
        f"\nper deel: "
        + ", ".join(
            f"{pad.name}: {triples} triples / {sum(klassen.values())} objecten"
            for pad, (triples, klassen) in zip(delen, per_deel, strict=True)
        )
        + f"\nsom objecten over de delen={som_objecten} tegen bron={sum(ijk_klassen.values())} "
        f"(verschil {som_objecten - sum(ijk_klassen.values())} door gedeelde structuur "
        f"en {len(kruisingen)} knippen)"
        f"\nbytes ijk={ijk.stat().st_size} samen={samen.stat().st_size} ({verhouding:.3f}x)"
    )

    assert len(delen) == 2
    assert samen_triples == ijk_triples
    assert samen_klassen == ijk_klassen
    assert ijk_blanken == 0, "zonder die aanname zegt de vingerafdruk niets"
    assert samen_som == ijk_som
    assert abs(verhouding - 1.0) <= 0.05
