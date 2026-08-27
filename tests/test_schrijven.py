"""De schrijver geeft een OroX-TTL terug die naar dezelfde RDF-graaf parseert."""

from collections import Counter
from pathlib import Path

import pyoxigraph
import pytest
import rdflib

# Niet `Graph.isomorphic`, dat #2 zelf noemt: die methode vergelijkt alleen de triples
# zonder blanke knopen en verklaart de rest ongezien gelijk. In `mini_orox.ttl` is dat
# 18 van de 47 triples en in de Juinen-export 78%, dus juist het deel waar de belofte
# van deze serializer over gaat. `rdflib.compare.isomorphic` doet de echte
# knoop-toewijzing (canonicaliseren en dan vergelijken).
from rdflib.compare import isomorphic
from rdflib.namespace import OWL, RDF

from gwsw_orox_helpers.errors import DatasetError
from gwsw_orox_helpers.schrijven import (
    STANDAARD_PREFIXEN,
    lees_orox,
    schrijf_orox,
    schrijf_orox_quads,
)

TTL_DIR = Path(__file__).parent / "fixtures" / "ttl"
MINI = TTL_DIR / "mini_orox.ttl"
CP850 = TTL_DIR / "codering_cp850.ttl"

# De echte export van Stichting RIOned (Juinen); niet in deze repo getrackt.
JUINEN = Path("/home/martin/nlriochecker/data/gwsw_orox_ttl/GwswDataset__Voorbeeld_v1_6_orox.ttl")
# De export van De Wolden en Hoogeveen: 112 MB, ook niet getrackt (marker `zwaar`).
DEWOLDEN = Path("/home/martin/nlriochecker/data/gwsw_orox_ttl/dewoldenhoogeveen_orox.ttl")

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
GWSW_BASIS = "http://data.gwsw.nl/"


def _graaf(pad: Path) -> rdflib.Graph:
    """Leest een TTL met rdflib -- het onafhankelijke vergelijkingsgereedschap."""
    graaf = rdflib.Graph()
    graaf.parse(pad, format="turtle")
    return graaf


def _tekst(pad: Path, fallback_encoding: str | None) -> str:
    """De inhoud als tekst; eigen decodering, zodat de test niet op de schrijver leunt."""
    rauw = pad.read_bytes()
    try:
        return rauw.decode("utf-8")
    except UnicodeDecodeError:
        assert fallback_encoding is not None
        return rauw.decode(fallback_encoding)


def _tellingen(pad: Path, fallback_encoding: str | None = None) -> tuple[int, Counter[str]]:
    """Het aantal triples en het aantal objecten per GWSW-klasse, streamend geteld.

    Voor een bestand van 112 MB is een rdflib-graaf (en dus `isomorphic`) geen optie:
    tellingen zijn wat er op die schaal te vergelijken valt.
    """
    triples = 0
    klassen: Counter[str] = Counter()
    bron = _tekst(pad, fallback_encoding)
    for quad in pyoxigraph.parse(bron, format=pyoxigraph.RdfFormat.TURTLE):
        triples += 1
        if quad.predicate.value == RDF_TYPE and isinstance(quad.object, pyoxigraph.NamedNode):
            if quad.object.value.startswith(GWSW_BASIS):
                klassen[quad.object.value.rsplit("/", 1)[-1]] += 1
    return triples, klassen


def test_mini_orox_blijft_isomorf(tmp_path: Path) -> None:
    """Bron en teruggeschreven bestand dragen dezelfde graaf (blanke knopen incluis)."""
    doel = tmp_path / "mini_terug.ttl"
    schrijf_orox(MINI, doel)
    assert isomorphic(_graaf(MINI), _graaf(doel))


def test_ontologiekop_gaat_mee(tmp_path: Path) -> None:
    """De kop (`<file://...> a owl:Ontology ; owl:versionInfo ...`) is gewone triples.

    Isomorfie alleen zou dit niet aantonen als de kop aan bron- én doelzijde ontbrak;
    daarom hier expliciet dat hij in het teruggeschreven bestand staat.
    """
    doel = tmp_path / "mini_terug.ttl"
    schrijf_orox(MINI, doel)
    kop = rdflib.URIRef("file:///mini/GwswDataset__Mini.orox.ttl")
    terug = _graaf(doel)
    assert (kop, RDF.type, OWL.Ontology) in terug
    assert terug.value(kop, OWL.versionInfo) == rdflib.Literal("Export for GWSW from mini fixture")


def test_dataset_basis_en_standaardprefixen_staan_in_de_kop(tmp_path: Path) -> None:
    """De prefixmap van de uitvoer: de standaardzeven plus de dataset-basis uit de bron."""
    doel = tmp_path / "mini_terug.ttl"
    schrijf_orox(MINI, doel)
    kop = doel.read_text(encoding="utf-8")

    assert "@prefix : <http://sparql.gwsw.nl/repositories/Mini#> ." in kop
    for prefix, iri in STANDAARD_PREFIXEN.items():
        assert f"@prefix {prefix}: <{iri}> ." in kop


def test_gwsw_prefix_volgt_de_leeslaag() -> None:
    """De schrijver kent zijn eigen `gwsw:`-IRI; hij mag niet van de leeslaag afdrijven.

    `schrijven` importeert `dataset` bewust niet (eigen pad), dus is deze gelijkheid
    alleen hier te bewaken.
    """
    from gwsw_orox_helpers import dataset

    assert STANDAARD_PREFIXEN["gwsw"] == dataset.GWSW


def test_standaardprefixen_zijn_niet_te_wijzigen() -> None:
    """De standaardkop is gedeelde staat; een afnemer mag hem niet voor iedereen omzetten."""
    with pytest.raises(TypeError):
        STANDAARD_PREFIXEN["gwsw"] = "http://data.gwsw.nl/1.5/totaal/"  # type: ignore[index]


def test_gefilterde_stroom_schrijft_twee_helften(tmp_path: Path) -> None:
    """De ingang voor de clip: één parse, een gefilterde stroom, twee bestanden.

    Samen dragen de helften hier weer de hele bron. Dat geldt *omdat* deze snede geen
    blanke knoop doorsnijdt: `:Put_1` draagt zelf geen blanke knopen. Snijdt de grens er
    wel een door, dan is de hereniging niet meer isomorf -- zie de test hieronder.
    """
    geopend = lees_orox(MINI)
    grens = rdflib.URIRef("http://sparql.gwsw.nl/repositories/Mini#Put_1")
    binnen, buiten = [], []
    for quad in geopend.quads:
        (binnen if quad.subject.value == str(grens) else buiten).append(quad)

    schrijf_orox_quads(binnen, tmp_path / "binnen.ttl", prefixen=geopend.prefixen)
    schrijf_orox_quads(buiten, tmp_path / "buiten.ttl", prefixen=geopend.prefixen)

    samen = _graaf(tmp_path / "binnen.ttl") + _graaf(tmp_path / "buiten.ttl")
    assert len(_graaf(tmp_path / "binnen.ttl")) == 4
    assert isomorphic(samen, _graaf(MINI))


def test_snede_door_een_blanke_knoop_is_niet_meer_te_herenigen(tmp_path: Path) -> None:
    """Een snede dwars door een blanke knoop levert twee helften die niet meer passen.

    Blanke-knooplabels zijn documentgebonden: staat `:X gwsw:hasAspect _:b` in de ene
    helft en `_:b rdf:type gwsw:Punt` in de andere, dan mint elke lezer voor elk bestand
    zijn eigen knoop en is de hereniging een andere graaf dan de bron -- de triples zijn
    er alle 47 nog, maar de brug tussen de twee is weg. Dit is de eerlijke uitkomst en
    geen fout in de serializer; de afnemer (fase 3) moet elke bnode-sluiting aan één kant
    houden. Zie de moduledocstring van `schrijven`.
    """
    geopend = lees_orox(MINI)
    binnen, buiten = [], []
    for quad in geopend.quads:
        doel = binnen if isinstance(quad.subject, pyoxigraph.BlankNode) else buiten
        doel.append(quad)

    schrijf_orox_quads(binnen, tmp_path / "bnodes.ttl", prefixen=geopend.prefixen)
    schrijf_orox_quads(buiten, tmp_path / "rest.ttl", prefixen=geopend.prefixen)

    bron = _graaf(MINI)
    samen = _graaf(tmp_path / "bnodes.ttl") + _graaf(tmp_path / "rest.ttl")
    assert len(binnen) == 18 and len(buiten) == 29
    assert len(samen) == len(bron)  # geen triple zoekgeraakt ...
    assert not isomorphic(samen, bron)  # ... en toch niet dezelfde graaf.


def test_zonder_prefixen_blijft_de_graaf_gelijk(tmp_path: Path) -> None:
    """Prefixen zijn schrijfwijze: zonder dataset-basis komt dezelfde graaf terug."""
    doel = tmp_path / "kaal.ttl"
    schrijf_orox_quads(lees_orox(MINI).quads, doel)

    assert "@prefix : " not in doel.read_text(encoding="utf-8")
    assert isomorphic(_graaf(doel), _graaf(MINI))


def test_cp850_bron_komt_er_als_utf8_uit(tmp_path: Path) -> None:
    """Een export met MS-DOS-bytes gaat met dezelfde terugvalcodering als de leeslaag."""
    doel = tmp_path / "cp850_terug.ttl"
    schrijf_orox(CP850, doel, fallback_encoding="cp850")

    utf8_bron = tmp_path / "cp850_als_utf8.ttl"
    utf8_bron.write_text(CP850.read_bytes().decode("cp850"), encoding="utf-8")
    assert "cavaljéweg" in doel.read_text(encoding="utf-8")
    assert isomorphic(_graaf(doel), _graaf(utf8_bron))


def test_cp850_bron_zonder_terugval_noemt_de_codering_als_oorzaak(tmp_path: Path) -> None:
    """Zonder opgegeven codering is een niet-UTF-8-bron een fout -- met de juiste oorzaak.

    De parser struikelt over de bytes en niet over de syntaxis; "geen geldige Turtle"
    zou de lezer naar een niet-bestaande syntaxfout sturen terwijl er een
    `fallback_encoding` ontbreekt. De leeslaag zegt hier hetzelfde
    (`dataset._decode`), en dat is de formulering waar de afnemer op zoekt.
    """
    with pytest.raises(DatasetError, match="terugvalcodering"):
        schrijf_orox(CP850, tmp_path / "nooit.ttl")


def test_onbekende_terugvalcodering_is_een_dataseterror(tmp_path: Path) -> None:
    """Een codering die Python niet kent, meldt zich als DatasetError met de naam erin."""
    with pytest.raises(DatasetError, match="onbekende-codering"):
        schrijf_orox(CP850, tmp_path / "nooit.ttl", fallback_encoding="onbekende-codering")


def test_ontbrekende_bron_is_een_dataseterror(tmp_path: Path) -> None:
    """Een bron die er niet is, meldt zich als DatasetError en niet als OSError."""
    with pytest.raises(DatasetError, match="kan niet gelezen worden"):
        schrijf_orox(tmp_path / "bestaat_niet.ttl", tmp_path / "nooit.ttl")


def test_kapotte_turtle_is_een_dataseterror(tmp_path: Path) -> None:
    """Een syntaxfout onderweg komt als DatasetError boven, niet als pyoxigraph-fout."""
    stuk = tmp_path / "stuk.ttl"
    stuk.write_text("@prefix : <http://x#> .\n:a :b :c .\n:d :e\n", encoding="utf-8")

    with pytest.raises(DatasetError, match="geen geldige Turtle"):
        schrijf_orox(stuk, tmp_path / "nooit.ttl")


def test_onbeschrijfbaar_doel_is_een_dataseterror(tmp_path: Path) -> None:
    """Een doel dat niet te openen is (hier: een map), meldt zich als DatasetError."""
    doel = tmp_path / "een_map"
    doel.mkdir()

    with pytest.raises(DatasetError, match="kan niet geschreven worden"):
        schrijf_orox(MINI, doel)


def test_doelmap_die_geen_map_kan_zijn_is_een_dataseterror(tmp_path: Path) -> None:
    """Een bestand als ouder-map: ook het aanmaken van de doelmap belooft DatasetError."""
    bezet = tmp_path / "geen_map"
    bezet.write_text("ik ben een bestand", encoding="utf-8")

    with pytest.raises(DatasetError, match="kan niet geschreven worden"):
        schrijf_orox(MINI, bezet / "eronder.ttl")


def test_fout_halverwege_laat_geen_afgekapt_doel_achter(tmp_path: Path) -> None:
    """Breekt de bron halverwege af, dan komt er geen half bestand op `doel` te staan.

    De parser is lui: de syntaxfout komt pas boven als de serializer al aan het schrijven
    is. Wie daarna naar `doel` kijkt, moet het oude bestand zien of niets -- nooit een
    afgekapte export die zich als een hele voordoet. Er wordt daarom naar een tmp in
    dezelfde map geschreven en pas bij succes hernoemd.
    """
    stuk = tmp_path / "stuk.ttl"
    regels = ["@prefix : <http://x#> ."]
    regels += [f":s{n} :p :o{n} ." for n in range(20_000)]
    regels.append(":d :e\n")
    stuk.write_text("\n".join(regels), encoding="utf-8")
    doel = tmp_path / "uit" / "half.ttl"

    with pytest.raises(DatasetError, match="geen geldige Turtle"):
        schrijf_orox(stuk, doel)

    assert not doel.exists()
    assert list(doel.parent.iterdir()) == []


@pytest.mark.parametrize("sleutel", ["kapot prefix", "1abc", "met:dubbelepunt", "eindigt."])
def test_onbruikbare_prefixsleutel_is_een_dataseterror(tmp_path: Path, sleutel: str) -> None:
    """Een sleutel die geen PN_PREFIX is, wordt geweigerd in plaats van uitgeschreven.

    pyoxigraph controleert de sleutels niet: `{"kapot prefix": ...}` komt er als
    `@prefix kapot prefix: <...> .` uit en dat bestand is geen Turtle meer. De fout hoort
    bij het schrijven te vallen, niet bij de volgende lezer.
    """
    with pytest.raises(DatasetError, match="geen geldige Turtle-prefix"):
        schrijf_orox_quads(
            lees_orox(MINI).quads, tmp_path / "nooit.ttl", prefixen={sleutel: "http://x#"}
        )


def test_lege_prefixsleutel_is_de_dataset_basis(tmp_path: Path) -> None:
    """De dataset-basis `:` heeft een lege sleutel; die is geldig en moet blijven werken."""
    doel = tmp_path / "basis.ttl"
    schrijf_orox_quads(lees_orox(MINI).quads, doel, prefixen={"": "http://sparql.gwsw.nl/x#"})

    assert "@prefix : <http://sparql.gwsw.nl/x#> ." in doel.read_text(encoding="utf-8")


@pytest.mark.skipif(not JUINEN.exists(), reason="de Juinen-export ligt niet op deze machine")
def test_juinen_blijft_isomorf(tmp_path: Path) -> None:
    """De echte voorbeeldexport (119 kB) overleeft de heen-en-weerweg ongeschonden."""
    doel = tmp_path / "juinen_terug.ttl"
    schrijf_orox(JUINEN, doel)
    assert isomorphic(_graaf(JUINEN), _graaf(doel))


@pytest.mark.zwaar
@pytest.mark.skipif(not DEWOLDEN.exists(), reason="de 112 MB-export ligt niet op deze machine")
def test_dewoldenhoogeveen_houdt_tellingen_en_orde_van_grootte(tmp_path: Path) -> None:
    """De 112 MB-export: gelijke tellingen en een bestandsgrootte in dezelfde orde.

    De tellingen zijn de eis. De grootte is een sanity-band die alleen moet uitsluiten
    dat er stilletjes een groot deel verdwijnt of verdubbelt -- gemeten kwam de uitvoer
    op 0,911x de bron (102,7 MB tegen 112,8 MB) uit, en dat verschil is regel voor regel
    verklaard, niet zoekgeraakte inhoud:

    - de bron heeft CRLF-regeleinden, de uitvoer LF: 3.708.107 bytes minder;
    - de bron zet het subject op een eigen regel en het predicaat ingesprongen daaronder
      (3.708.107 regels voor 1.877.729 triples), de uitvoer schrijft één triple per
      regel: per saldo 1.830.262 bytes minder aan tabs en regeleinden;
    - de bron schrijft `rdf:type` voltuit, de uitvoer gebruikt de Turtle-korting `a`:
      650.470 typetriples maal 7 bytes = 4.553.290 bytes minder.

    Samen 10.091.659 van de 10.092.888 bytes verschil. De band staat daarom op ±15% en
    niet op de ±5% die het issue voorspelde; ±5% zou geen sanity-band zijn maar een eis
    aan de opmaak van de serializer.
    """
    doel = tmp_path / "dewoldenhoogeveen_terug.ttl"
    # Deze export is geen zuivere UTF-8 (cp850-bytes in een straatnaam); nlriochecker
    # leest hem met dezelfde terugvalcodering.
    schrijf_orox(DEWOLDEN, doel, fallback_encoding="cp850")

    bron_triples, bron_klassen = _tellingen(DEWOLDEN, fallback_encoding="cp850")
    doel_triples, doel_klassen = _tellingen(doel)
    bron_bytes = DEWOLDEN.stat().st_size
    doel_bytes = doel.stat().st_size
    print(
        f"\ntriples bron={bron_triples} doel={doel_triples}; "
        f"GWSW-klassen bron={len(bron_klassen)} doel={len(doel_klassen)}; "
        f"objecten met GWSW-type bron={sum(bron_klassen.values())} "
        f"doel={sum(doel_klassen.values())}; "
        f"bytes bron={bron_bytes} doel={doel_bytes} "
        f"({doel_bytes / bron_bytes:.3f}x)"
    )

    assert doel_triples == bron_triples
    assert doel_klassen == bron_klassen
    assert abs(doel_bytes - bron_bytes) / bron_bytes <= 0.15
