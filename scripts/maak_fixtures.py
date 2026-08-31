#!/usr/bin/env python
"""Schrijft de TTL-fixtures onder tests/fixtures/ttl.

Elke fixture bevat precies een ingebouwd defect, met bovenaan in een DEFECT-regel
wat dat defect is. De prelude met de klassenhierarchie is voor alle fixtures gelijk;
die staat hier een keer in plaats van dertien keer in de bestanden.

Zes van de twintig fixtures in tests/fixtures/ttl zijn handwerk en staan hier niet:
`codering_cp850.ttl` (niet-UTF-8), `net001_bouwwerk_eindknoop.ttl`, `schoon.ttl`,
`top001_losliggende_put.ttl`, `mini_orox.ttl` en `juinen_voorbeeld_v1_6.ttl`. Die laatste
is het publieke GWSW-Voorbeeld van Stichting RIONED, byte-exact overgenomen: de
round-trip-tests plakken er tekst uit, dus er mag niets aan veranderen -- ook niet door
deze generator.

Gebruik:  uv run python scripts/maak_fixtures.py
"""

from pathlib import Path
from typing import Any

DOEL = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "ttl"

PRELUDE = """@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix geo:  <http://www.opengis.net/ont/geosparql#> .
@prefix gwsw: <http://data.gwsw.nl/1.6/totaal/> .
@prefix :     <http://example.org/toets#> .

# Minimale klassenhierarchie, zodat de fixture zonder de volle ontologie werkt.
gwsw:Inspectieput rdfs:subClassOf gwsw:Rioolput .
gwsw:LozePut rdfs:subClassOf gwsw:Rioolput .
gwsw:Lozingsput rdfs:subClassOf gwsw:Rioolput .
gwsw:Overstortput rdfs:subClassOf gwsw:Rioolput .
gwsw:Rioolput rdfs:subClassOf gwsw:Put .
gwsw:Putorientatie rdfs:subClassOf gwsw:Knooppunt .
gwsw:Compartimentorientatie rdfs:subClassOf gwsw:Knooppunt .
gwsw:Bouwwerkorientatie rdfs:subClassOf gwsw:Knooppunt .
gwsw:Leidingorientatie rdfs:subClassOf gwsw:Verbinding .
gwsw:GemengdRiool rdfs:subClassOf gwsw:VrijvervalRioolleiding .
gwsw:Hemelwaterriool rdfs:subClassOf gwsw:VrijvervalRioolleiding .
gwsw:Vuilwaterriool rdfs:subClassOf gwsw:VrijvervalRioolleiding .
gwsw:Infiltratieriool rdfs:subClassOf gwsw:VrijvervalRioolleiding .
gwsw:Overstortleiding rdfs:subClassOf gwsw:VrijvervalRioolleiding .
gwsw:VrijvervalRioolleiding rdfs:subClassOf gwsw:Rioolleiding .
gwsw:Rioolleiding rdfs:subClassOf gwsw:Leiding .
gwsw:Persleiding rdfs:subClassOf gwsw:MechanischeTransportleiding .
gwsw:MechanischeTransportleiding rdfs:subClassOf gwsw:Transportleiding .
gwsw:Transportleiding rdfs:subClassOf gwsw:Leiding .
gwsw:Rioolgemaal rdfs:subClassOf gwsw:Gemaal .
gwsw:Uitlaatconstructie rdfs:subClassOf gwsw:Bouwwerk .
gwsw:Bergbezinkbassin rdfs:subClassOf gwsw:Bouwwerk .
gwsw:Valput rdfs:subClassOf gwsw:Rioolput .
gwsw:Duiker rdfs:subClassOf gwsw:Leiding .
gwsw:Zinker rdfs:subClassOf gwsw:VrijvervalRioolleiding .
gwsw:Drain rdfs:subClassOf gwsw:VrijvervalRioolleiding .
gwsw:Sloot rdfs:subClassOf gwsw:Oppervlaktewater .
"""


def put(
    naam: str,
    label: str,
    x: float,
    y: float,
    klasse: str = "Inspectieput",
    extra: str = "",
    orientatie: str = "Putorientatie",
) -> str:
    return f''':{naam} rdf:type gwsw:{klasse} ; rdfs:label "{label}" ;
    gwsw:hasAspect :{naam}_ori .{extra}
:{naam}_ori rdf:type gwsw:{orientatie} ;
    gwsw:hasAspect [ rdf:type gwsw:Punt ;
        gwsw:hasValue "<gml:Point xmlns:gml=\\"http://www.opengis.net/gml\\"><gml:pos>{x} {y}</gml:pos></gml:Point>"^^geo:gmlLiteral ] .
'''


# Hulpstukken staan niet in de gedeelde prelude: alleen de fixtures van issue #60 hebben
# ze nodig, mét de functierestrictie waar TOP-022/TOP-023 het verwachte aantal leidingen
# uit lezen. Een fixture die dit blok opneemt krijgt ook de owl-prefix; een prefixregel
# mag in Turtle overal op statementniveau staan.
HULPSTUK_KLASSEN = (
    "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
    "# Hulpstukken, met de functierestrictie uit de GWSW-ontologie (issue #60).\n"
    "gwsw:Hulpstukorientatie rdfs:subClassOf gwsw:Knooppunt .\n"
    # Zoals in de echte ontologie draagt Verbindingsstuk zelf een functie zonder aantal;
    # T_stuk_Speciaal bestaat daar niet en staat hier om de overerving te toetsen: hij
    # heeft geen eigen restrictie en moet die van T_stuk krijgen, terwijl T_stuk zelf
    # zijn eigen restrictie houdt en niet die van Verbindingsstuk erft.
    "gwsw:Verbindingsstuk rdfs:subClassOf gwsw:Hulpstuk ,\n"
    "    [ a owl:Restriction ; owl:onProperty gwsw:functie ;"
    " owl:hasValue gwsw:VerbindenVanLeidingen ] .\n"
    "gwsw:Afsluitstuk rdfs:subClassOf gwsw:Hulpstuk ,\n"
    "    [ a owl:Restriction ; owl:onProperty gwsw:functie ;"
    " owl:hasValue gwsw:AfsluitenVanLeidingen ] .\n"
    "gwsw:T_stuk rdfs:subClassOf gwsw:Verbindingsstuk ,\n"
    "    [ a owl:Restriction ; owl:onProperty gwsw:functie ;"
    " owl:hasValue gwsw:VerbindenVanDrieLeidingen ] .\n"
    "gwsw:T_stuk_Speciaal rdfs:subClassOf gwsw:T_stuk .\n"
    "gwsw:Kruisstuk rdfs:subClassOf gwsw:Verbindingsstuk ,\n"
    "    [ a owl:Restriction ; owl:onProperty gwsw:functie ;"
    " owl:hasValue gwsw:VerbindenVanVierLeidingen ] .\n\n"
)


def hulpstuk(naam: str, label: str, x: float, y: float, klasse: str = "T_stuk") -> str:
    """Een hulpstuk: als een put, maar met een Hulpstukorientatie als knooppunt."""
    return put(naam, label, x, y, klasse=klasse, orientatie="Hulpstukorientatie")


def leiding(
    naam: str,
    label: str,
    punten: list[tuple[float, float]],
    begin: str | None,
    eind: str | None,
    klasse: str = "GemengdRiool",
    bob: tuple[float, float] | None = None,
    kenmerken: str = "",
    literal: str | None = None,
) -> str:
    poslist = " ".join(f"{x} {y}" for x, y in punten)
    meetkunde = literal or (
        f'<gml:LineString xmlns:gml=\\"http://www.opengis.net/gml\\">'
        f'<gml:posList srsDimension=\\"2\\">{poslist}</gml:posList></gml:LineString>'
    )
    bob_begin = (
        f"\n:{naam}_b gwsw:hasAspect [ rdf:type gwsw:BobBeginpuntLeiding ; gwsw:hasValue {bob[0]} ] ."
        if bob
        else ""
    )
    bob_eind = (
        f"\n:{naam}_e gwsw:hasAspect [ rdf:type gwsw:BobEindpuntLeiding ; gwsw:hasValue {bob[1]} ] ."
        if bob
        else ""
    )
    koppel_begin = f"\n:{naam}_b gwsw:hasConnection :{begin}_ori ." if begin else ""
    koppel_eind = f"\n:{naam}_e gwsw:hasConnection :{eind}_ori ." if eind else ""
    return f''':{naam} rdf:type gwsw:{klasse} ; rdfs:label "{label}" ;
    gwsw:hasAspect :{naam}_ori .{kenmerken}
:{naam}_ori rdf:type gwsw:Leidingorientatie ;
    gwsw:hasPart :{naam}_b , :{naam}_e ;
    gwsw:hasAspect [ rdf:type gwsw:Lijn ;
        gwsw:hasValue "{meetkunde}"^^geo:gmlLiteral ] .
:{naam}_b rdf:type gwsw:BeginpuntLeiding .
:{naam}_e rdf:type gwsw:EindpuntLeiding .{bob_begin}{bob_eind}{koppel_begin}{koppel_eind}
'''


def kenmerken(naam: str, **waarden: object) -> str:
    """Hangt kenmerken aan een object; `_ref`-suffix maakt er een hasReference van."""
    regels = []
    for sleutel, waarde in waarden.items():
        if waarde is None:
            continue
        soort = sleutel.removesuffix("_ref")
        if sleutel.endswith("_ref"):
            regels.append(f"[ rdf:type gwsw:{soort} ; gwsw:hasReference gwsw:{waarde} ]")
        elif isinstance(waarde, str):
            regels.append(f'[ rdf:type gwsw:{soort} ; gwsw:hasValue "{waarde}"^^xsd:date ]')
        else:
            regels.append(f"[ rdf:type gwsw:{soort} ; gwsw:hasValue {waarde} ]")
    if not regels:
        return ""
    return f"\n:{naam} gwsw:hasAspect " + " ,\n    ".join(regels) + " ."


def maaiveld(naam: str, hoogte: float, wijze: str | None = None) -> str:
    """Hangt een maaiveldorientatie met maaiveldhoogte aan een putorientatie.

    Met `wijze` krijgt de orientatie ook een puntgeometrie met inwinning erop, zoals
    de BrutIS-export van De Wolden en Hoogeveen die schrijft: de inwinningswijze hangt daar aan
    het Punt-aspect en niet aan de maaiveldhoogte zelf.
    """
    if wijze is None:
        return f"""
:{naam}_ori gwsw:hasConnection :{naam}_maa .
:{naam}_maa rdf:type gwsw:Maaiveldorientatie ;
    gwsw:hasAspect [ rdf:type gwsw:Maaiveldhoogte ; gwsw:hasValue {hoogte} ] .
"""
    return f"""
:{naam}_ori gwsw:hasConnection :{naam}_maa .
:{naam}_maa rdf:type gwsw:Maaiveldorientatie ;
    gwsw:hasAspect [ rdf:type gwsw:Maaiveldhoogte ; gwsw:hasValue {hoogte} ] ;
    gwsw:hasAspect :{naam}_maa_pun .
:{naam}_maa_pun rdf:type gwsw:Punt ;
    gwsw:hasValue "<gml:Point xmlns:gml=\\"http://www.opengis.net/gml\\"><gml:pos>0.0 0.0</gml:pos></gml:Point>"^^geo:gmlLiteral ;
    gwsw:hasAspect [ rdf:type gwsw:Inwinning ;
        gwsw:hasAspect [ rdf:type gwsw:WijzeVanInwinning ; gwsw:hasReference gwsw:{wijze} ] ] .
"""


def deksel(
    naam: str,
    niveau: float,
    wijze: str | None = None,
    datum: str | None = None,
    klasse: str = "Putdeksel",
) -> str:
    """Hangt een putdeksel met dekselniveau (en eventueel inwinning) aan een put.

    Met `klasse` een subklasse als `Putdeksel_ZwaarVerkeer`; de fixture moet die dan
    zelf als subklasse van Putdeksel declareren, want de prelude kent haar niet.
    """
    inwinning = ""
    if wijze or datum:
        delen = []
        if wijze:
            delen.append(f"[ rdf:type gwsw:WijzeVanInwinning ; gwsw:hasReference gwsw:{wijze} ]")
        if datum:
            delen.append(f'[ rdf:type gwsw:DatumInwinning ; gwsw:hasValue "{datum}"^^xsd:date ]')
        inwinning = (
            " ;\n        gwsw:hasAspect [ rdf:type gwsw:Inwinning ;\n            "
            "gwsw:hasAspect " + " ,\n            ".join(delen) + " ]"
        )
    return f"""
:{naam} gwsw:hasPart :{naam}_dek .
:{naam}_dek rdf:type gwsw:{klasse} ;
    gwsw:hasAspect :{naam}_dek_ori .
:{naam}_dek_ori rdf:type gwsw:Dekselorientatie ;
    gwsw:hasAspect [ rdf:type gwsw:Putdekselniveau ; gwsw:hasValue {niveau}{inwinning} ] .
"""


def drempel(put: str, naam: str, niveau: float | None = None, breedte: float | None = None) -> str:
    """Hangt een overstortdrempel als onderdeel aan een put."""
    aspecten = kenmerken(naam, Drempelniveau=niveau, Drempelbreedte=breedte)
    return f'''
:{put} gwsw:hasPart :{naam} .
:{naam} rdf:type gwsw:Overstortdrempel ; rdfs:label "{naam}" .{aspecten}
'''


def gemaal(naam: str, label: str, punt: tuple[float, float]) -> str:
    """Een rioolgemaal als afvoereindpunt in het netwerk (subklasse van Gemaal)."""
    return put(naam, label, punt[0], punt[1], klasse="Rioolgemaal")


def stelsel(naam: str, label: str, klasse: str, leden: list[str]) -> str:
    """Een geregistreerd stelselobject dat zijn leden via `hasPart` draagt (#17)."""
    delen = " , ".join(f":{lid}" for lid in leden)
    return f':{naam} rdf:type gwsw:{klasse} ; rdfs:label "{label}" ;\n    gwsw:hasPart {delen} .\n'


STANDAARDPUT: dict[str, object] = dict(
    BreedtePut=1000, LengtePut=1000, MateriaalPut_ref="Beton", HoogtePut=1500
)


def nette_put(
    naam: str, label: str, x: float, y: float, mv: float = 10.0, **extra_kenmerken: object
) -> str:
    """Een put met maatvoering, materiaal en maaiveldhoogte."""
    waarden = {**STANDAARDPUT, **extra_kenmerken}
    return put(naam, label, x, y, extra=kenmerken(naam, **waarden)) + maaiveld(naam, mv)


def nette_leiding(
    naam: str,
    label: str,
    punten: list[tuple[float, float]],
    begin: str | None,
    eind: str | None,
    # `Any` en niet `object`: `extra` is een heterogeen doorgeefluik naar `leiding`
    # (`klasse: str`, `bob: tuple[float, float]`, `literal: str | None`) waaruit vooraf een
    # `velden`-dict gevist wordt. Eén elementtype dat die vier tegelijk dekt en toch aan
    # `leiding` toewijsbaar blijft bestaat niet.
    **extra: Any,
) -> str:
    """Een leiding met materiaal, maatvoering, lengte en begindatum."""
    velden: dict[str, object] = {
        "BreedteLeiding": 300,
        "HoogteLeiding": 300,
        "MateriaalLeiding_ref": "Beton",
        "VormLeiding_ref": "Rond",
        "LengteLeiding": 50.0,
        "Begindatum": "1980-01-01",
    }
    velden.update(extra.pop("velden", {}))
    return leiding(naam, label, punten, begin, eind, kenmerken=kenmerken(naam, **velden), **extra)


def hoogteput(
    naam: str,
    label: str,
    punt: tuple[float, float],
    mv: float = 10.0,
    dek: float | None = 10.0,
    hoogte: float = 1500,
    mv_wijze: str | None = None,
    dek_wijze: str | None = None,
    **extra: object,
) -> str:
    """Een put met maaiveld, putdeksel en puthoogte.

    Met `dek=None` krijgt de put geen putdeksel. Zo ziet de De Wolden en Hoogeveen-export eruit:
    daarin komt `Putdekselniveau` geen enkele keer voor, zodat de hoogtechecks op de
    maaiveldhoogte terugvallen.
    """
    waarden: dict[str, object] = {**STANDAARDPUT, "HoogtePut": hoogte}
    waarden.update(extra)
    return (
        put(naam, label, punt[0], punt[1], extra=kenmerken(naam, **waarden))
        + maaiveld(naam, mv, mv_wijze)
        + (deksel(naam, dek, dek_wijze) if dek is not None else "")
    )


def hoogteleiding(
    naam: str,
    label: str,
    punten: list[tuple[float, float]],
    begin: str | None,
    eind: str | None,
    bob: tuple[float, float],
    **velden: object,
) -> str:
    """Een leiding met BOB's en standaardmaatvoering."""
    basis: dict[str, object] = {
        "BreedteLeiding": 300,
        "HoogteLeiding": 300,
        "MateriaalLeiding_ref": "Beton",
        "VormLeiding_ref": "Rond",
        "LengteLeiding": 50.0,
        "Begindatum": "1980-01-01",
    }
    basis.update(velden)
    return leiding(naam, label, punten, begin, eind, bob=bob, kenmerken=kenmerken(naam, **basis))


A = (1000.0, 2000.0)
B = (1050.0, 2000.0)
C = (1100.0, 2000.0)

FIXTURES: dict[str, tuple[str, str]] = {}

# Een compacte referentiedataset: de vormen die `dataset.py` op een echte OroX-export
# tegenkomt, in acht objecten. Put A draagt twee onvergelijkbare typen (Inspectieput
# onder Rioolput, VerdektePut rechtstreeks onder Put), put B een compartiment zonder
# puntgeometrie en een putdeksel met er wel een -- samen de twee helften van
# `structural_diff`. Streng 1 draagt beide BOB's, streng 2 geen enkele en koppelt aan
# het compartiment in plaats van aan de put. Doorlaat D1 is de derde verbinding: geen
# leiding maar een Onderdeelorientatie, zodat zichtbaar blijft dat de strengselectie de
# hele Verbinding-afsluiting neemt en niet alleen Leidingorientatie. Deze fixture hoort
# met de gebundelde ontologie geladen te worden; de klassen erin staan niet allemaal in
# de prelude.
DEKSEL_MET_PUNT = """
:PutB gwsw:hasPart :PutB_dek .
:PutB_dek rdf:type gwsw:Putdeksel ;
    gwsw:hasAspect :PutB_dek_ori .
:PutB_dek_ori rdf:type gwsw:Dekselorientatie ;
    gwsw:hasAspect [ rdf:type gwsw:Putdekselniveau ; gwsw:hasValue 9.95 ] ;
    gwsw:hasAspect [ rdf:type gwsw:Punt ;
        gwsw:hasValue "<gml:Point xmlns:gml=\\"http://www.opengis.net/gml\\"><gml:pos>1050.0 2000.0</gml:pos></gml:Point>"^^geo:gmlLiteral ] .
"""

COMPARTIMENT_ZONDER_PUNT = """
:PutB gwsw:hasPart :PutB_c1 .
:PutB_c1 rdf:type gwsw:Compartiment ; rdfs:label "B/c1" ;
    gwsw:hasAspect :PutB_c1_ori .
:PutB_c1_ori rdf:type gwsw:Compartimentorientatie .
"""

# Een doorlaat tussen put B en haar compartiment: een verbinding zonder leiding. De
# ontologie hangt de Onderdeelorientatie onder Verbinding (net als Leidingorientatie) en
# geeft haar eigen vertexklassen, BeginpuntOnderdeel en EindpuntOnderdeel. Ze draagt hier
# bewust een Lijn: zonder geometrie zou zij wel ontologisch maar niet structureel als
# streng gelden, en dat zet een `strengen_zonder_geometrie` in `structural_diff`.
ONDERDEELVERBINDING = """
:D1 rdf:type gwsw:Doorlaat ; rdfs:label "D1" ;
    gwsw:hasAspect :D1_ori .
:D1_ori rdf:type gwsw:Onderdeelorientatie ;
    gwsw:hasPart :D1_b , :D1_e ;
    gwsw:hasAspect [ rdf:type gwsw:Lijn ;
        gwsw:hasValue "<gml:LineString xmlns:gml=\\"http://www.opengis.net/gml\\"><gml:posList srsDimension=\\"2\\">1050.0 2000.0 1050.0 2001.0</gml:posList></gml:LineString>"^^geo:gmlLiteral ] .
:D1_b rdf:type gwsw:BeginpuntOnderdeel .
:D1_e rdf:type gwsw:EindpuntOnderdeel .
:D1_b gwsw:hasConnection :PutB_ori .
:D1_e gwsw:hasConnection :PutB_c1_ori .
"""

FIXTURES["dataset_voorbeeld.ttl"] = (
    "geen; een compacte referentiedataset met de vormen die een echte export draagt",
    put("PutA", "A", 1000.0, 2000.0)
    + ":PutA rdf:type gwsw:VerdektePut .\n"
    + put("PutB", "B", 1050.0, 2000.0)
    + DEKSEL_MET_PUNT
    + COMPARTIMENT_ZONDER_PUNT
    + ONDERDEELVERBINDING
    + gemaal("Gem", "G", (1100.0, 2000.0))
    + leiding(
        "L1",
        "1",
        [(1000.0, 2000.0), (1050.0, 2000.0)],
        "PutA",
        "PutB",
        bob=(8.60, 8.55),
    )
    + leiding("L2", "2", [(1050.0, 2000.0), (1100.0, 2000.0)], "PutB_c1", "Gem"),
)

# TOP-020: de lijn is tegen de administratieve richting in getekend.
FIXTURES["top020_omgekeerd_getekend.ttl"] = (
    "streng 1 is van B naar A getekend terwijl de administratie A naar B zegt",
    put("PutA", "A", 1000.0, 2000.0)
    + put("PutB", "B", 1050.0, 2000.0)
    + leiding("L1", "1", [(1050.0, 2000.0), (1000.0, 2000.0)], "PutA", "PutB"),
)

# ATTR-013: vulwaarden in hoogtekenmerken (issue #1). Put A heeft maaiveld 0,00 (en geen
# deksel), put B maaiveld 0,01, put C is schoon; streng 1 heeft een BOB van 0,000 aan het
# beginpunt.
FIXTURES["attr013_vulwaarde_hoogte.ttl"] = (
    "put A (maaiveld 0,00), put B (maaiveld 0,01) en streng 1 (BOB begin 0,000) "
    "dragen een vulwaarde",
    hoogteput("PutA", "A", A, mv=0.0, dek=None)
    + hoogteput("PutB", "B", B, mv=0.01, dek=None)
    + hoogteput("PutC", "C", C)
    + hoogteleiding("L1", "1", [A, B], "PutA", "PutB", bob=(0.0, 8.55))
    + hoogteleiding("L2", "2", [B, C], "PutB", "PutC", bob=(8.60, 8.55)),
)

# De subklassehierarchie van de stelselfamilie, inline: de gedeelde prelude kent haar niet.
STELSEL_HIERARCHIE = """gwsw:Vuilwaterstelsel rdfs:subClassOf gwsw:Rioolstelsel .
gwsw:GemengdStelsel rdfs:subClassOf gwsw:Rioolstelsel .
gwsw:Hemelwaterstelsel rdfs:subClassOf gwsw:Rioolstelsel .
gwsw:Rioolstelsel rdfs:subClassOf gwsw:Stelsel .
"""

# De geregistreerde stelselboom die #17 blootlegde: twee lokale stelsels met alleen
# strengen plus een gemeentebrede `_geb_0`-bucket die naast een streng ook putten bevat.
# `dataset.stelsel_leden` scheidt die twee.
FIXTURES["stelsels_registratie.ttl"] = (
    "geen; twee lokale stelsels met alleen strengen plus een gemeentebrede bucket met "
    "strengen en putten",
    STELSEL_HIERARCHIE
    + put("PutA", "A", 1000.0, 2000.0)
    + put("PutB", "B", 1050.0, 2000.0)
    + gemaal("Gem", "G", (1100.0, 2000.0))
    + put("PutC", "C", 1000.0, 2100.0)
    + put("PutD", "D", 1050.0, 2100.0)
    + put("PutE", "E", 1000.0, 2200.0)
    + leiding(
        "LV1", "V1", [(1000.0, 2000.0), (1050.0, 2000.0)], "PutA", "PutB", klasse="Vuilwaterriool"
    )
    + leiding(
        "LV2", "V2", [(1050.0, 2000.0), (1100.0, 2000.0)], "PutB", "Gem", klasse="Vuilwaterriool"
    )
    + leiding("LG1", "G1", [(1000.0, 2100.0), (1050.0, 2100.0)], "PutC", "PutD")
    + leiding(
        "LH1", "H1", [(1000.0, 2200.0), (1050.0, 2200.0)], "PutE", None, klasse="Hemelwaterriool"
    )
    + stelsel("stelV", "vuilwater-1", "Vuilwaterstelsel", ["LV1", "LV2"])
    + stelsel("stelG", "gemengd-1", "GemengdStelsel", ["LG1"])
    + stelsel("stelH", "hemelwater-bucket", "Hemelwaterstelsel", ["LH1", "PutE"]),
)

FIXTURES["adm007_overstort_met_drempel.ttl"] = (
    "geen; zelfde als adm007_overstort_zonder_functie maar put 'O' draagt een "
    "ingebouwde overstortdrempel",
    nette_put("PutA", "A", *A)
    + put("PutO", "O", B[0], B[1], klasse="Overstortput")
    + drempel("PutO", "DrempelO", niveau=9.00, breedte=2000.0)
    + nette_leiding("L1", "1", [A, B], "PutA", "PutO"),
)

# --- EXT en AHN ------------------------------------------------------------
#
# Deze fixture hoort bij het EXT-scenario van nlriochecker: het studiegebied loopt van
# (980, 1980) tot (1120, 2020) en het hoogteraster staat overal op 10,00 m NAP, met een
# nodata-vlek rond (1040, 2010).

EXT_A = (1000.0, 2000.0)
EXT_B = (1050.0, 2000.0)
EXT_C = (1090.0, 2000.0)
EXT_D = (2000.0, 2000.0)
EXT_E = (1000.0, 2010.0)
EXT_F = (1040.0, 2010.0)
# De duiker (streng 6) kruist water-2 op eigen hoogte, los van streng 3.
EXT_G = (1010.0, 2013.0)
EXT_H = (1030.0, 2013.0)

FIXTURES["ext_scenario.ttl"] = (
    "meerdere; deze fixture voedt de EXT- en AHN-checks tegelijk, zie de tests",
    # Put A: maaiveld en deksel gelijk aan het AHN.
    hoogteput("PutA", "A", EXT_A, mv=10.00, dek=10.00)
    # Put B: 0,10 m afwijking van het AHN, dus HGT-001. Zijn maaiveldhoogte komt
    # zelf uit het AHN; de vergelijking met het raster is voor deze put dus een
    # vergelijking van twee hoogtemodellen.
    + hoogteput("PutB", "B", EXT_B, mv=10.10, dek=10.10, mv_wijze="AHN2", dek_wijze="AHN2")
    # Put C: 0,50 m afwijking, dus HGT-002; en geen BGT-deksel in de buurt.
    + hoogteput("PutC", "C", EXT_C, mv=10.50, dek=10.50, mv_wijze="Inmeting", dek_wijze="Inmeting")
    # Put D ligt buiten het studiegebied en mag geen enkele uitslag krijgen.
    + hoogteput("PutD", "D", EXT_D, mv=99.00, dek=99.00)
    # Put F ligt op de nodata-vlek van het raster.
    # Put E heeft geen putdekselniveau, net als elke put in De Wolden en Hoogeveen. De hoogtechecks
    # vallen dan terug op de maaiveldhoogte, en die komt hier uit AHN2. Zijn afwijking
    # is 0,12 m, dus hij komt in HGT-001 terecht (vanaf 0,10 m, issue #63).
    + hoogteput("PutE", "E", EXT_E, mv=10.12, dek=None, mv_wijze="AHN2")
    + hoogteput("PutF", "F", EXT_F, mv=12.00, dek=12.00)
    # Lozingsput ver van het water; Lozingsput vlakbij water-1.
    + put("PutL1", "L1", 1005.0, 1990.0, klasse="Lozingsput")
    + put("PutL2", "L2", 1072.0, 2008.0, klasse="Lozingsput")
    # Streng 1 loopt door pand-1 heen: EXT-001.
    + hoogteleiding("L1", "1", [EXT_A, EXT_B], "PutA", "PutB", bob=(11.00, 9.50))
    # Streng 2 kruist water-1 en is geen duiker: EXT-002 en EXT-003.
    + hoogteleiding("L2", "2", [EXT_B, EXT_C], "PutB", "PutC", bob=(9.50, 6.30))
    # Streng 3 is een zinker die water-2 kruist: wel EXT-002, geen EXT-003. Een zinker
    # is in de ontologie een VrijvervalRioolleiding en zit dus in de populatie.
    + hoogteleiding("L3", "3", [EXT_E, EXT_F], "PutE", "PutF", bob=(9.60, 9.55)).replace(
        "gwsw:GemengdRiool", "gwsw:Zinker"
    )
    # Streng 6 is een duiker die water-2 kruist, net als streng 3, maar drie meter
    # noordelijker en op een eigen route: een duiker is geen rioolleiding (subklasse
    # van Leiding, niet van VrijvervalRioolleiding) en valt buiten de populatie van
    # EXT-002 en EXT-003; geen van beide meldt hem. Hij verbindt oppervlaktewater en
    # heeft dus geen rioolputten aan zijn uiteinden. Boven op streng 3 leverde hij
    # TOP-006 een samenvalmelding op; die check draait op alle leidingen.
    + leiding("L6", "6", [EXT_G, EXT_H], None, None, klasse="Duiker")
    # Streng 4 verbindt de lozingsputten met het net.
    + hoogteleiding("L4", "4", [EXT_C, (1072.0, 2008.0)], "PutC", "PutL2", bob=(9.40, 9.35))
    + "\n"
    # Put P, put Q en streng "4" liggen binnen het BGT-pand; EXT-001 moet ze als
    # "binnen" melden, in tegenstelling tot streng "1" die de gevel kruist. Ze
    # krijgen geen maaiveldhoogte, BOB of inwinning, zodat ze de HGT- en BTR-tests
    # niet raken -- vandaar `put`/`leiding` en niet `hoogteput`/`hoogteleiding`.
    + '# Put P, put Q en streng "4" liggen binnen het BGT-pand (1020, 1998)-(1030, 2002);\n'
    + '# EXT-001 moet ze als "binnen" melden, in tegenstelling tot streng "1" die de gevel\n'
    + "# kruist. Ze krijgen geen maaiveldhoogte, BOB of inwinning, zodat ze de HGT- en\n"
    + "# BTR-tests niet raken.\n"
    + put("PutP", "P", 1022.0, 2000.0)
    + put("PutQ", "Q", 1028.0, 2000.0)
    + leiding("L5", "4", [(1022.0, 2000.0), (1028.0, 2000.0)], "PutP", "PutQ")
    + "\n"
    # De grensgevallen van issue #59, allemaal in de vrije strook y 1982-1995. Kale
    # putten en strengen (geen hoogte, BOB of inwinning), zodat alleen de
    # kruisingschecks ze zien. Streng 7 eindigt in water-3: lozingspunt, geen
    # bevinding. Streng 8 ligt 0,5 m naast water-4: binnen de zoekstraal, snijdt
    # niet, geen bevinding. Streng 9 doorkruist de 0,3 m smalle greppel water-5:
    # echte doorkruising, wel een bevinding. Streng 10 loopt over de oostrand van
    # water-6 (x = 1103): tangentieel, geen bevinding.
    + "# Grensgevallen van issue #59: streng 7 eindigt in een waterdeel (lozingspunt),\n"
    + "# streng 8 ligt 0,5 m naast een waterdeel, streng 9 doorkruist een 0,3 m smalle\n"
    + "# greppel, streng 10 loopt over de rand van een waterdeel. Alleen 9 is een bevinding.\n"
    + put("PutR", "R", 1060.0, 1988.0)
    + put("PutS", "S", 1082.0, 1988.0)
    + leiding("L7", "7", [(1060.0, 1988.0), (1082.0, 1988.0)], "PutR", "PutS")
    + put("PutT", "T", 1088.0, 1992.5)
    + put("PutU", "U", 1097.0, 1992.5)
    + leiding("L8", "8", [(1088.0, 1992.5), (1097.0, 1992.5)], "PutT", "PutU")
    + put("PutV", "V", 1045.0, 1988.0)
    + put("PutW", "W", 1055.0, 1988.0)
    + leiding("L9", "9", [(1045.0, 1988.0), (1055.0, 1988.0)], "PutV", "PutW")
    + put("PutX", "X", 1103.0, 1984.0)
    + put("PutY", "Y", 1103.0, 1994.0)
    + leiding("L10", "10", [(1103.0, 1984.0), (1103.0, 1994.0)], "PutX", "PutY"),
)

# Issue #60: een streng die haar eindpunt aan een URI koppelt die niet bestaat, omdat de
# export de stam van de hulpstuk-URI aanvult met het achtervoegsel dat een put daar
# heet (in De Wolden `_put<n>`). Streng 1 heeft zo'n fantoomdoel en hoort na het herstel
# aan T1 te hangen. De andere drie zijn de tegenproeven: streng 2 koppelt netjes aan de
# orientatie, streng 3 wijst naar een stam die helemaal geen knoop is, en streng 4 naar
# `:PutB_put` -- put B bestaat en is een knoop, maar draagt een Putorientatie en geen
# Hulpstukorientatie. Zonder die vierde is de guard `stam in hulpstukken` niet te
# onderscheiden van een zwakkere `stam in nodes`.
FIXTURES["dataset_fantoomkoppeling.ttl"] = (
    "streng 1 koppelt haar eindpunt aan :T1_put, een URI die niet bestaat; de orientatie "
    "van T-stuk T1 heet :T1_ori (issue #60)",
    HULPSTUK_KLASSEN
    + put("PutA", "A", 1000.0, 2000.0)
    + hulpstuk("T1", "T1", 1050.0, 2000.0)
    + leiding("L1", "1", [(1000.0, 2000.0), (1050.0, 2000.0)], "PutA", None)
    + ":L1_e gwsw:hasConnection :T1_put .\n"
    + put("PutB", "B", 1100.0, 2000.0)
    + leiding("L2", "2", [(1050.0, 2000.0), (1100.0, 2000.0)], "T1", "PutB")
    + put("PutC", "C", 1050.0, 2050.0)
    + leiding("L3", "3", [(1050.0, 2050.0), (1050.0, 2000.0)], "PutC", None)
    + ":L3_e gwsw:hasConnection :Onbekend_put .\n"
    + put("PutD", "D", 1100.0, 2050.0)
    + leiding("L4", "4", [(1100.0, 2050.0), (1100.0, 2000.0)], "PutD", None)
    + ":L4_e gwsw:hasConnection :PutB_put .\n",
)


# TOP-022: T-stuk T1 heeft twee richtingen waar zijn functie er drie voorschrijft. De
# rest is in orde en mag niet melden: T3 heeft drie richtingen waarvan een dubbel gelegd
# (twee strengen naar put D, hartlijnen 5 cm uit elkaar), kruisstuk K1 heeft er vier
# en afsluitstuk A1 draagt geen functie met een aantal en valt buiten de toets.
FIXTURES["top022_hulpstuk_te_weinig.ttl"] = (
    "T-stuk T1 verbindt twee leidingen waar zijn GWSW-functie er drie voorschrijft; T3 "
    "(drie richtingen, een dubbel gelegd), kruisstuk K1 (vier) en afsluitstuk A1 zijn in "
    "orde (issue #60)",
    HULPSTUK_KLASSEN
    + put("PutA", "A", 1000.0, 2000.0)
    + put("PutB", "B", 1100.0, 2000.0)
    + hulpstuk("T1", "T1", 1050.0, 2000.0)
    + leiding("L1", "1", [(1000.0, 2000.0), (1050.0, 2000.0)], "PutA", "T1")
    + leiding("L2", "2", [(1050.0, 2000.0), (1100.0, 2000.0)], "T1", "PutB")
    + put("PutC", "C", 1000.0, 2100.0)
    + put("PutD", "D", 1100.0, 2100.0)
    + put("PutE", "E", 1050.0, 2150.0)
    + hulpstuk("T3", "T3", 1050.0, 2100.0)
    + leiding("L3", "3", [(1000.0, 2100.0), (1050.0, 2100.0)], "PutC", "T3")
    + leiding("L4a", "4a", [(1050.0, 2100.0), (1100.0, 2100.0)], "T3", "PutD")
    + leiding("L4b", "4b", [(1050.0, 2100.0), (1075.0, 2100.05), (1100.0, 2100.0)], "T3", "PutD")
    + leiding("L5", "5", [(1050.0, 2100.0), (1050.0, 2150.0)], "T3", "PutE")
    + put("PutF", "F", 1000.0, 2200.0)
    + put("PutG", "G", 1100.0, 2200.0)
    + put("PutH", "H", 1050.0, 2250.0)
    + put("PutI", "I", 1050.0, 2170.0)
    + hulpstuk("K1", "K1", 1050.0, 2200.0, klasse="Kruisstuk")
    + leiding("L6", "6", [(1000.0, 2200.0), (1050.0, 2200.0)], "PutF", "K1")
    + leiding("L7", "7", [(1050.0, 2200.0), (1100.0, 2200.0)], "K1", "PutG")
    + leiding("L8", "8", [(1050.0, 2200.0), (1050.0, 2250.0)], "K1", "PutH")
    + leiding("L9", "9", [(1050.0, 2170.0), (1050.0, 2200.0)], "PutI", "K1")
    + put("PutJ", "J", 1150.0, 2000.0)
    + hulpstuk("A1", "A1", 1200.0, 2000.0, klasse="Afsluitstuk")
    + leiding("L10", "10", [(1150.0, 2000.0), (1200.0, 2000.0)], "PutJ", "A1"),
)

# ---------------------------------------------------------------------------
# Vier vormen die de lader zelf moeten bijten. De Wolden en Hoogeveen kent ze geen van vieren,
# dus zonder deze fixtures is er geen dataset waarop de reparaties uit issue #36
# zichtbaar zijn. Ze dragen geen defect: ze zijn conform GWSW 1.6 geschreven en
# horen dus juist wél gelezen te worden.
# ---------------------------------------------------------------------------

FIXTURES["dataset_zwaarverkeerdeksel.ttl"] = (
    "geen; put B draagt een Putdeksel_ZwaarVerkeer in plaats van een kaal Putdeksel",
    "# De subklasse staat niet in de gedeelde prelude; alleen deze fixture heeft haar nodig.\n"
    "gwsw:Putdeksel_ZwaarVerkeer rdfs:subClassOf gwsw:Putdeksel .\n\n"
    + hoogteput("PutA", "A", A)
    + hoogteput("PutB", "B", B, dek=None)
    + deksel("PutB", 9.95, klasse="Putdeksel_ZwaarVerkeer")
    + hoogteleiding("L1", "1", [A, B], "PutA", "PutB", bob=(8.60, 8.55)),
)


def _twee_houders(straat_eerst: bool) -> str:
    """Een compartiment onder twee houders, in de gevraagde schrijfvolgorde.

    Het GWSW staat meer dan een houder toe en rdflib levert ze in schrijfvolgorde
    op. Staat de straat vooraan, dan loopt een wandeling die de eerste houder volgt
    dood: een `Straat` is geen knoop en draagt zelf geen houder.
    """
    houders = [":PutB gwsw:hasPart :PutB_c1 .", ":Straat1 gwsw:hasPart :PutB_c1 ."]
    if straat_eerst:
        houders.reverse()
    return (
        nette_put("PutA", "A", *A)
        + nette_put("PutB", "B", *B)
        + nette_leiding("L1", "1", [A, B], "PutA", "PutB_c1")
        + '\n:Straat1 rdf:type gwsw:Straat ; rdfs:label "Dorpsstraat" .\n'
        + "\n".join(houders)
        + '\n:PutB_c1 rdf:type gwsw:Compartiment ; rdfs:label "B/c1" ;\n'
        "    gwsw:hasAspect :PutB_c1_ori .\n"
        ":PutB_c1_ori rdf:type gwsw:Compartimentorientatie .\n"
    )


FIXTURES["dataset_twee_houders_put_eerst.ttl"] = (
    "geen; compartiment B/c1 hangt onder put B en onder een straat, put eerst geschreven",
    _twee_houders(straat_eerst=False),
)

FIXTURES["dataset_twee_houders_straat_eerst.ttl"] = (
    "geen; hetzelfde compartiment onder dezelfde twee houders, straat eerst geschreven",
    _twee_houders(straat_eerst=True),
)

# Dezelfde twee putten en streng als elders, maar met `isPartOf` en `isAspectOf`
# geschreven. Het GWSW declareert die als de inverse van `hasPart` en `hasAspect`,
# dus dit is een conforme export -- alleen een andere schrijfrichting.
FIXTURES["dataset_inverse_properties.ttl"] = (
    "geen; alle insluitingen staan als isPartOf/isAspectOf in plaats van hasPart/hasAspect",
    """:PutA rdf:type gwsw:Inspectieput ; rdfs:label "A" .
:PutA_ori rdf:type gwsw:Putorientatie ; gwsw:isAspectOf :PutA .
:PutA_pun rdf:type gwsw:Punt ; gwsw:isAspectOf :PutA_ori ;
    gwsw:hasValue "<gml:Point xmlns:gml=\\"http://www.opengis.net/gml\\"><gml:pos>1000.0 2000.0</gml:pos></gml:Point>"^^geo:gmlLiteral .
:PutB rdf:type gwsw:Inspectieput ; rdfs:label "B" .
:PutB_ori rdf:type gwsw:Putorientatie ; gwsw:isAspectOf :PutB .
:PutB_pun rdf:type gwsw:Punt ; gwsw:isAspectOf :PutB_ori ;
    gwsw:hasValue "<gml:Point xmlns:gml=\\"http://www.opengis.net/gml\\"><gml:pos>1050.0 2000.0</gml:pos></gml:Point>"^^geo:gmlLiteral .
:L1 rdf:type gwsw:GemengdRiool ; rdfs:label "1" .
:L1_ori rdf:type gwsw:Leidingorientatie ; gwsw:isAspectOf :L1 .
:L1_lij rdf:type gwsw:Lijn ; gwsw:isAspectOf :L1_ori ;
    gwsw:hasValue "<gml:LineString xmlns:gml=\\"http://www.opengis.net/gml\\"><gml:posList srsDimension=\\"2\\">1000.0 2000.0 1050.0 2000.0</gml:posList></gml:LineString>"^^geo:gmlLiteral .
:L1_b rdf:type gwsw:BeginpuntLeiding ; gwsw:isPartOf :L1_ori ; gwsw:hasConnection :PutA_ori .
:L1_b_bob rdf:type gwsw:BobBeginpuntLeiding ; gwsw:isAspectOf :L1_b ; gwsw:hasValue 8.60 .
:L1_e rdf:type gwsw:EindpuntLeiding ; gwsw:isPartOf :L1_ori ; gwsw:hasConnection :PutB_ori .
:L1_e_bob rdf:type gwsw:BobEindpuntLeiding ; gwsw:isAspectOf :L1_e ; gwsw:hasValue 8.55 .
""",
)

# Een export mag beide schrijfrichtingen naast elkaar zetten -- ze zeggen hetzelfde.
# Wie ze allebei leest zonder te ontdubbelen, telt het kenmerk en het onderdeel twee
# keer, en dat is precies het soort dubbeltelling dat nergens een melding oplevert.
FIXTURES["dataset_dubbele_schrijfrichting.ttl"] = (
    "geen; put B schrijft dezelfde twee relaties zowel voorwaarts als invers",
    nette_put("PutA", "A", *A)
    + nette_put("PutB", "B", *B)
    + nette_leiding("L1", "1", [A, B], "PutA", "PutB")
    + """
:PutB gwsw:hasAspect :PutB_bd .
:PutB_bd gwsw:isAspectOf :PutB .
:PutB_bd rdf:type gwsw:Begindatum ; gwsw:hasValue "1980-01-01"^^xsd:date .
:PutB gwsw:hasPart :PutB_c1 .
:PutB_c1 gwsw:isPartOf :PutB .
:PutB_c1 rdf:type gwsw:Compartiment ; rdfs:label "B/c1" ;
    gwsw:hasAspect :PutB_c1_ori .
:PutB_c1_ori rdf:type gwsw:Compartimentorientatie .
""",
)

# Een uitlaatconstructie die daarnaast als bouwwerk getypeerd is. Alfabetisch wint
# "Bouwwerk", maar dat is de algemenere van de twee: de ontologie zegt dat
# Uitlaatconstructie een subklasse van Bouwwerk is.
FIXTURES["dataset_meervoudig_objecttype.ttl"] = (
    "geen; bouwwerk U draagt zowel gwsw:Bouwwerk als gwsw:Uitlaatconstructie",
    put("Uitlaat1", "U", 1100.0, 2000.0, klasse="Uitlaatconstructie").replace(
        "gwsw:Putorientatie", "gwsw:Bouwwerkorientatie"
    )
    + ":Uitlaat1 rdf:type gwsw:Bouwwerk .\n",
)

# ---------------------------------------------------------------------------
# De overslag- en omwegtakken van de lezers (issue #16). Elk van de zeven vormen
# hieronder komt in geen enkele andere fixture voor, en `inlezen.py` heeft er een
# tak voor: een kenmerk met een sub-aspect dat geen Inwinning is, een kenmerk van
# de juiste klasse zonder waarde, een geometrie-aspect zonder literaal, een
# putdekselniveau langs de twee omwegen, en een object met twee orientaties. Ze
# zijn geen van alle een defect in de GWSW-zin -- ze zijn conform en horen gelezen
# te worden zoals hier vastligt -- maar zonder deze fixture blijft een refactor die
# er een stilzet groen.
# ---------------------------------------------------------------------------

# Put A: het kenmerk Begindatum draagt een sub-aspect dat geen Inwinning is.
# `_read_inwinning` loopt de sub-aspecten van elk kenmerk af en moet deze overslaan
# in plaats van hem als herkomst te lezen.
KENMERK_MET_VREEMD_SUBASPECT = """
:PutA gwsw:hasAspect :PutA_bd .
:PutA_bd rdf:type gwsw:Begindatum ; gwsw:hasValue "1980-01-01"^^xsd:date ;
    gwsw:hasAspect [ rdf:type gwsw:Toelichting ; gwsw:hasValue "geschat" ] .
"""

# Put B: een maaiveldorientatie met een Maaiveldhoogte zonder `hasValue`. Een
# kenmerk zonder waarde is geen meting; het telt als afwezig.
MAAIVELDHOOGTE_ZONDER_WAARDE = """
:PutB_ori gwsw:hasConnection :PutB_maa .
:PutB_maa rdf:type gwsw:Maaiveldorientatie ;
    gwsw:hasAspect [ rdf:type gwsw:Maaiveldhoogte ] .
"""

# Put C: het putdekselniveau hangt rechtstreeks aan de put, zonder Putdeksel-onderdeel
# en zonder Dekselorientatie. Dat is de eerste van de twee omwegen in `_deksel_kenmerk`.
DEKSELNIVEAU_AAN_DE_PUT = """
:PutC gwsw:hasAspect [ rdf:type gwsw:Putdekselniveau ; gwsw:hasValue 9.80 ] .
"""

# Put D: het putdeksel is er wel, maar het niveau hangt aan het onderdeel zelf en niet
# aan een Dekselorientatie. Dat is de tweede omweg.
DEKSELNIVEAU_AAN_HET_ONDERDEEL = """
:PutD gwsw:hasPart :PutD_dek .
:PutD_dek rdf:type gwsw:Putdeksel ;
    gwsw:hasAspect [ rdf:type gwsw:Putdekselniveau ; gwsw:hasValue 9.70 ] .
"""

# Put E: de orientatie draagt wel een Punt-aspect maar geen literaal. De put blijft een
# knoop -- haar orientatie is een Putorientatie -- alleen zonder geometrie.
PUNT_ZONDER_LITERAAL = """:PutE rdf:type gwsw:Inspectieput ; rdfs:label "E" ;
    gwsw:hasAspect :PutE_ori .
:PutE_ori rdf:type gwsw:Putorientatie ;
    gwsw:hasAspect [ rdf:type gwsw:Punt ] .
"""

# Put F en streng 1 dragen elk twee orientaties. Het GWSW verbiedt dat niet, en een
# export die het doet mag geen dubbele knoop of dubbele streng opleveren.
TWEEDE_PUTORIENTATIE = """
:PutF gwsw:hasAspect :PutF_ori2 .
:PutF_ori2 rdf:type gwsw:Putorientatie ;
    gwsw:hasAspect [ rdf:type gwsw:Punt ;
        gwsw:hasValue "<gml:Point xmlns:gml=\\"http://www.opengis.net/gml\\"><gml:pos>1200.0 2005.0</gml:pos></gml:Point>"^^geo:gmlLiteral ] .
"""

TWEEDE_LEIDINGORIENTATIE = """
:L1 gwsw:hasAspect :L1_ori2 .
:L1_ori2 rdf:type gwsw:Leidingorientatie ;
    gwsw:hasPart :L1_b2 , :L1_e2 ;
    gwsw:hasAspect [ rdf:type gwsw:Lijn ;
        gwsw:hasValue "<gml:LineString xmlns:gml=\\"http://www.opengis.net/gml\\"><gml:posList srsDimension=\\"2\\">1000.0 2001.0 1050.0 2001.0</gml:posList></gml:LineString>"^^geo:gmlLiteral ] .
:L1_b2 rdf:type gwsw:BeginpuntLeiding .
:L1_e2 rdf:type gwsw:EindpuntLeiding .
"""

FIXTURES["dataset_rommelige_export.ttl"] = (
    "geen; zeven conforme maar ongebruikelijke vormen die de lezers moeten overslaan "
    "of langs een tweede weg moeten vinden (issue #16)",
    put("PutA", "A", 1000.0, 2000.0)
    + KENMERK_MET_VREEMD_SUBASPECT
    + put("PutB", "B", 1050.0, 2000.0)
    + MAAIVELDHOOGTE_ZONDER_WAARDE
    + put("PutC", "C", 1100.0, 2000.0)
    + DEKSELNIVEAU_AAN_DE_PUT
    + put("PutD", "D", 1150.0, 2000.0)
    + DEKSELNIVEAU_AAN_HET_ONDERDEEL
    + PUNT_ZONDER_LITERAAL
    + put("PutF", "F", 1200.0, 2000.0)
    + TWEEDE_PUTORIENTATIE
    + leiding("L1", "1", [(1000.0, 2000.0), (1050.0, 2000.0)], "PutA", "PutB")
    + TWEEDE_LEIDINGORIENTATIE,
)

# De inwinningsdatum, het enige veld van `Inwinning` dat geen enkele fixture droeg
# (issue #16). Put A draagt een volledige inwinning op haar dekselniveau, put B alleen
# een datum -- die tweede is de tegenproef dat `Inwinning.__bool__` ook zonder wijze
# waar is en de herkomst dus niet stilletjes wegvalt.
FIXTURES["dataset_inwinningsdatum.ttl"] = (
    "geen; het putdekselniveau van put A draagt wijze en datum van inwinning, dat van "
    "put B alleen een datum",
    put("PutA", "A", *A)
    + deksel("PutA", 9.85, wijze="Inmeting", datum="2019-05-17")
    + put("PutB", "B", *B)
    + deksel("PutB", 9.75, datum="2020-11-02"),
)


def render(defect: str, inhoud: str) -> str:
    """De volledige tekst van een fixture: de prelude, de DEFECT-regel en de inhoud.

    Staat apart van `main` zodat `tests/test_fixtures.py` dezelfde regel gebruikt om te
    bewaken dat de bestanden op schijf nog bij dit script passen. Zou de test de opmaak
    overschrijven, dan bewaakte hij zijn eigen kopie.
    """
    return f"{PRELUDE}\n# DEFECT: {defect}\n\n{inhoud}"


def main() -> None:
    DOEL.mkdir(parents=True, exist_ok=True)
    for naam, (defect, inhoud) in FIXTURES.items():
        (DOEL / naam).write_text(render(defect, inhoud), encoding="utf-8")
        print(naam)


if __name__ == "__main__":
    main()
