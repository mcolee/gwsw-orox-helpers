"""Tests voor de GML-parser."""

from __future__ import annotations

import math

import pytest
from shapely.geometry import LineString, Point, Polygon

from gwsw_orox_helpers.geometry import (
    GeometryError,
    coordinaattokens,
    is_multipart_literal,
    parse_gml,
    parse_gml_met_z,
    parse_gml_z,
    tokens_per_punt,
    vervang_coordinaten,
)

PUNT_3D = '<gml:Point xmlns:gml="g"><gml:pos>168462.01 442691.30 22.45</gml:pos></gml:Point>'
PUNT_2D = '<gml:Point xmlns:gml="g"><gml:pos>168462.51 442691.30</gml:pos></gml:Point>'
LIJN_3D = (
    '<gml:LineString xmlns:gml="g"><gml:posList srsDimension="3">'
    "1 2 30 4 5 60</gml:posList></gml:LineString>"
)
LIJN_2D = (
    '<gml:LineString xmlns:gml="g"><gml:posList srsDimension="2">'
    "1 2 4 5</gml:posList></gml:LineString>"
)
RING = (
    '<gml:Polygon xmlns:gml="g"><gml:exterior><gml:LinearRing><gml:posList srsDimension="2">'
    "0 0 0 1 1 1 0 0</gml:posList></gml:LinearRing></gml:exterior></gml:Polygon>"
)


def test_punt_met_hoogte() -> None:
    assert parse_gml(PUNT_3D) == Point(168462.01, 442691.30)
    assert parse_gml_z(PUNT_3D) == [22.45]


def test_punt_zonder_hoogte() -> None:
    # gml:pos draagt in de GWSW-export nooit een srsDimension; het aantal
    # waarden bepaalt dan de dimensie.
    assert parse_gml(PUNT_2D) == Point(168462.51, 442691.30)
    assert parse_gml_z(PUNT_2D) == [None]


def test_lijn_driedimensionaal() -> None:
    assert parse_gml(LIJN_3D) == LineString([(1, 2), (4, 5)])
    assert parse_gml_z(LIJN_3D) == [30.0, 60.0]


def test_lijn_tweedimensionaal() -> None:
    assert parse_gml(LIJN_2D) == LineString([(1, 2), (4, 5)])
    assert parse_gml_z(LIJN_2D) == [None, None]


def test_polygoon_uit_linearring() -> None:
    vlak = parse_gml(RING)

    assert isinstance(vlak, Polygon)
    assert vlak.area == pytest.approx(0.5)


@pytest.mark.parametrize(
    ("literal", "melding"),
    [
        ("<gml:Kromme>1 2</gml:Kromme>", "GML-soort"),
        ('<gml:Point xmlns:gml="g"></gml:Point>', "gml:pos"),
        ('<gml:Point xmlns:gml="g"><gml:pos>een twee</gml:pos></gml:Point>', "niet-numeriek"),
        (
            '<gml:LineString xmlns:gml="g"><gml:posList srsDimension="3">1 2 3 4'
            "</gml:posList></gml:LineString>",
            "srsDimension",
        ),
    ],
)
def test_onbruikbare_geometrie(literal: str, melding: str) -> None:
    with pytest.raises(GeometryError, match=melding):
        parse_gml(literal)


def test_is_multipart_literal_herkent_beide_vormen() -> None:
    """Een expliciete Multi-verpakking en twee posLists naast elkaar tellen allebei.

    De parser leest alleen het eerste deel, dus zonder deze signalering blijft het
    verschil tussen een streng en een streng met een los tweede stuk onzichtbaar.
    """
    multi = (
        '<gml:MultiCurve xmlns:gml="g"><gml:curveMember><gml:LineString>'
        '<gml:posList srsDimension="2">1 2 4 5</gml:posList></gml:LineString>'
        "</gml:curveMember></gml:MultiCurve>"
    )
    twee_lijsten = (
        '<gml:LineString xmlns:gml="g"><gml:posList srsDimension="2">1 2 4 5</gml:posList>'
        '<gml:posList srsDimension="2">7 8 9 0</gml:posList></gml:LineString>'
    )

    assert is_multipart_literal(multi) is True
    assert is_multipart_literal(twee_lijsten) is True
    assert is_multipart_literal(LIJN_2D) is False


def test_dimensie_valt_terug_op_een_even_aantal_waarden() -> None:
    """`gml:pos` draagt nooit een srsDimension; vier waarden zijn twee 2D-punten."""
    literal = '<gml:LineString xmlns:gml="g"><gml:pos>1 2 4 5</gml:pos></gml:LineString>'

    assert parse_gml_z(literal) == [None, None]


def test_dimensie_valt_terug_op_een_drievoud_waarden() -> None:
    """Negen waarden zijn niet in tweeen te delen maar wel in drieen: drie 3D-punten."""
    literal = '<gml:LineString xmlns:gml="g"><gml:pos>1 2 3 4 5 6 7 8 9</gml:pos></gml:LineString>'

    assert parse_gml_z(literal) == [3.0, 6.0, 9.0]


def test_een_ondeelbaar_aantal_waarden_is_een_leesfout() -> None:
    literal = '<gml:LineString xmlns:gml="g"><gml:pos>1 2 3 4 5</gml:pos></gml:LineString>'

    with pytest.raises(GeometryError, match="niet te duiden"):
        parse_gml_z(literal)


def test_vlak_geeft_zijn_coordinaten_via_de_buitenring() -> None:
    """Een put met een vlak als geometrie moet op eindige coordinaten te toetsen zijn.

    `hasattr(polygon, "coords")` roept de property aan, en die gooit bij shapely een
    NotImplementedError -- geen AttributeError, dus hasattr vangt hem niet op. Een
    afnemer die de coordinaten van een vlak wil, gaat dus via de ringen. Vlakken horen
    niet in een GWSW-export thuis, maar ze komen er wel in voor.
    """
    eindig = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    oneindig = Polygon([(0, 0), (float("inf"), 0), (1, 1), (0, 1)])

    with pytest.raises(NotImplementedError):
        _ = eindig.coords

    assert all(math.isfinite(w) for x, y in eindig.exterior.coords for w in (x, y))
    assert not all(math.isfinite(w) for x, y in oneindig.exterior.coords for w in (x, y))


def test_lijn_met_een_enkel_punt_is_een_leesfout() -> None:
    """GEOS gooit hier zijn eigen fout, en die erft niet van `ValueError`.

    Zonder de expliciete tak brak deze literaal het inlezen van de hele export af.
    Het bedoelde gedrag is dat het object als onleesbaar geteld wordt en de rest
    gewoon doorgaat.
    """
    literal = (
        '<gml:LineString xmlns:gml="g"><gml:posList srsDimension="2">'
        "1000.0 2000.0</gml:posList></gml:LineString>"
    )
    with pytest.raises(GeometryError, match="onbruikbare LineString-geometrie"):
        parse_gml(literal)


# --------------------------------------------------------------------------------------
# De eenpaslezer: dezelfde uitkomst als de twee losse lezers, in een gang
# --------------------------------------------------------------------------------------

# Elk paar is (literaal, of de oude weg een GeometryError gaf). De vlag is geen
# gemak maar de helft van de vraag: de gelijkwaardigheid moet blijken op de
# geslaagde *en* op de mislukte literalen, en zonder haar zou een corpus dat stil
# helemaal naar de fouttak schuift er nog steeds groen uitzien.
GELIJKWAARDIG = [
    pytest.param(PUNT_3D, False, id="punt-3d"),
    pytest.param(PUNT_2D, False, id="punt-2d-zonder-srsdimension"),
    pytest.param(LIJN_3D, False, id="lijn-3d"),
    pytest.param(LIJN_2D, False, id="lijn-2d"),
    pytest.param(RING, False, id="linearring-als-polygoon"),
    pytest.param(
        '<gml:LineString xmlns:gml="g"><gml:pos>1 2 4 5</gml:pos></gml:LineString>',
        False,
        id="dimensie-uit-even-aantal",
    ),
    pytest.param(
        '<gml:LineString xmlns:gml="g"><gml:pos>1 2 3 4 5 6 7 8 9</gml:pos></gml:LineString>',
        False,
        id="dimensie-uit-drievoud",
    ),
    pytest.param(
        '<gml:LineString xmlns:gml="g"><gml:posList srsDimension="4">'
        "1 2 3 4 5 6 7 8</gml:posList></gml:LineString>",
        False,
        id="vier-getallen-per-punt",
    ),
    pytest.param(
        '<gml:MultiCurve xmlns:gml="g"><gml:curveMember><gml:LineString>'
        '<gml:posList srsDimension="2">1 2 4 5</gml:posList></gml:LineString>'
        "</gml:curveMember></gml:MultiCurve>",
        False,
        id="multi-leest-het-eerste-deel",
    ),
    pytest.param(
        '<gml:LineString xmlns:gml="g"><gml:posz>1 2 4 5</gml:pos></gml:LineString>',
        False,
        id="misvormde-openingstag",
    ),
    pytest.param("<gml:Kromme>1 2</gml:Kromme>", True, id="fout-geen-gml-soort"),
    pytest.param('<gml:Point xmlns:gml="g"></gml:Point>', True, id="fout-geen-gml-pos"),
    # Het geval waar de herordening op aankomt: de eenpaslezer leest de getallen vóór de
    # srsDimension, de oude weg andersom. Draagt de literaal wél een srsDimension maar
    # geen `gml:pos`, dan sloeg de oude weg `_values` in de dimensiestap over en liep hij
    # er meteen daarna alsnog tegenaan. Beide horen dus dezelfde melding te geven.
    pytest.param(
        '<gml:Point srsDimension="3" xmlns:gml="g"></gml:Point>',
        True,
        id="fout-srsdimension-zonder-lijst",
    ),
    pytest.param(
        '<gml:Point xmlns:gml="g"><gml:pos>een twee</gml:pos></gml:Point>',
        True,
        id="fout-niet-numeriek",
    ),
    pytest.param(
        '<gml:LineString xmlns:gml="g"><gml:posList srsDimension="3">1 2 3 4'
        "</gml:posList></gml:LineString>",
        True,
        id="fout-rest-op-srsdimension",
    ),
    pytest.param(
        '<gml:LineString xmlns:gml="g"><gml:pos>1 2 3 4 5</gml:pos></gml:LineString>',
        True,
        id="fout-niet-te-duiden",
    ),
    pytest.param(
        '<gml:LineString xmlns:gml="g"><gml:posList srsDimension="2">'
        "1000.0 2000.0</gml:posList></gml:LineString>",
        True,
        id="fout-shapelyerror-lijn-met-een-punt",
    ),
    pytest.param(
        '<gml:Polygon xmlns:gml="g"><gml:exterior><gml:LinearRing>'
        '<gml:posList srsDimension="2">0 0 1 1</gml:posList>'
        "</gml:LinearRing></gml:exterior></gml:Polygon>",
        True,
        id="fout-shapelyerror-vlak-met-twee-punten",
    ),
    pytest.param(
        '<gml:LineString xmlns:gml="g"><gml:posList srsDimension="2"></gml:posList>'
        "</gml:LineString>",
        True,
        id="fout-lege-lijst-met-srsdimension",
    ),
    pytest.param(
        '<gml:LineString xmlns:gml="g"><gml:posList></gml:posList></gml:LineString>',
        True,
        id="fout-lege-lijst-zonder-srsdimension",
    ),
    pytest.param(
        '<gml:LineString xmlns:gml="g"><gml:posList srsDimension="0">1 2'
        "</gml:posList></gml:LineString>",
        True,
        id="fout-srsdimension-nul",
    ),
    pytest.param(
        '<gml:LineString xmlns:gml="g"><gml:posList srsDimension="1">1 2'
        "</gml:posList></gml:LineString>",
        True,
        id="fout-srsdimension-een",
    ),
    pytest.param(
        '<gml:Point xmlns:gml="g"><gml:pos srsDimension="3">1 2</gml:pos></gml:Point>',
        True,
        id="fout-punt-mist-een-waarde",
    ),
]


def _langs_de_twee_lezers(literal: str) -> tuple[object, list[float | None]]:
    """Wat `inlezen._geometry` vroeger deed: eerst `parse_gml`, daarna `parse_gml_z`."""
    return parse_gml(literal), parse_gml_z(literal)


def _uitkomst(lezer, literal: str) -> tuple[object, ...]:
    """De volledige waarneembare uitkomst: de geometrie, de z-lijst, of de fout.

    De geometrie als WKT en niet als object, zodat een verschil in soort of in
    coordinaten in de vergelijking zichtbaar wordt en niet in een `__eq__` verdwijnt.
    """
    try:
        geometrie, z = lezer(literal)
    except GeometryError as fout:
        return ("GeometryError", str(fout))
    return ("geometrie", geometrie.wkt, z)


@pytest.mark.parametrize(("literal", "geeft_fout"), GELIJKWAARDIG)
def test_parse_gml_met_z_is_gelijkwaardig_aan_de_twee_losse_lezers(
    literal: str, geeft_fout: bool
) -> None:
    """De eenpaslezer geeft precies wat `parse_gml` en `parse_gml_z` samen gaven.

    Inclusief de foutpaden: dezelfde `GeometryError` met dezelfde melding, ook op de
    ShapelyError-tak (een lijn met een enkel punt laat GEOS zelf struikelen). De oude
    weg is hier de maatstaf; hij blijft bevroren omdat de clip en nlriochecker hem
    rechtstreeks aanroepen.
    """
    oud = _uitkomst(_langs_de_twee_lezers, literal)
    nieuw = _uitkomst(parse_gml_met_z, literal)

    assert nieuw == oud
    assert (oud[0] == "GeometryError") is geeft_fout


@pytest.mark.parametrize(
    ("literal", "oud"),
    [(LIJN_2D, 2), (LIJN_3D, 2), (PUNT_3D, 4), (PUNT_2D, 5)],
    ids=["lijn-2d", "lijn-3d", "punt-3d", "punt-2d"],
)
def test_parse_gml_met_z_converteert_de_getallen_een_keer(
    literal: str, oud: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """De reden dat de functie bestaat: een float-conversie in plaats van twee tot vijf.

    Deze test kijkt met opzet naar binnen -- naar `geometry._values`, de plek waar de
    coordinatenlijst getallen wordt. De winst is niet aan de uitkomst te zien (die is
    per contract identiek, zie de gelijkwaardigheidstest hierboven), dus zonder deze
    telling is 'een pass' een bewering en geen eigenschap. Wie de indeling van de module
    verandert, hoort langs deze test te komen.
    """
    from gwsw_orox_helpers import geometry

    tellingen: list[str] = []
    echte_values = geometry._values

    def geteld(tekst: str) -> list[float]:
        tellingen.append(tekst)
        return echte_values(tekst)

    monkeypatch.setattr(geometry, "_values", geteld)

    parse_gml(literal)
    parse_gml_z(literal)
    assert len(tellingen) == oud

    tellingen.clear()
    parse_gml_met_z(literal)

    assert len(tellingen) == 1


# --------------------------------------------------------------------------------------
# De tekstkant: de coordinatenlijst als tekst, en wat er per punt op gaat
# --------------------------------------------------------------------------------------


def test_coordinaattokens_geeft_de_getallen_als_tekst() -> None:
    """De tokens zijn de brontekst en geen floats: `168462.30` blijft `168462.30`.

    Dat is de hele reden dat de knip ze nodig heeft -- een float-omweg zou er
    `168462.3` van maken en de hereniging niet meer byte-gelijk laten zijn.
    """
    literal = (
        '<gml:LineString xmlns:gml="g"><gml:posList srsDimension="3">'
        "168462.30 442691.00 22.450 168470.00 442700.50 22.40"
        "</gml:posList></gml:LineString>"
    )

    assert coordinaattokens(literal) == [
        "168462.30",
        "442691.00",
        "22.450",
        "168470.00",
        "442700.50",
        "22.40",
    ]


def test_coordinaattokens_leest_een_los_punt_en_wetenschappelijke_notatie() -> None:
    """`gml:pos` telt net zo goed als `gml:posList`, en een exponent is een token."""
    assert coordinaattokens(PUNT_2D) == ["168462.51", "442691.30"]
    assert coordinaattokens(
        '<gml:Point xmlns:gml="g"><gml:pos>1.68462e5 4.4269130E5</gml:pos></gml:Point>'
    ) == ["1.68462e5", "4.4269130E5"]


def test_coordinaattokens_negeert_de_scheiders_tussen_de_getallen() -> None:
    """Dubbele spaties, newlines en randspaties leveren dezelfde tokens op.

    De tokens zijn de getallen; wie de *scheiders* nodig heeft (de knip, om te zien of
    hij de tekst letterlijk kan terugleggen) vergelijkt de literaal en niet de tokens.
    """
    ruim = (
        '<gml:LineString xmlns:gml="g"><gml:posList srsDimension="2">\n'
        "  1 2\n  4 5\n</gml:posList></gml:LineString>"
    )

    assert coordinaattokens(ruim) == ["1", "2", "4", "5"]


def test_coordinaattokens_van_een_lege_of_ontbrekende_lijst_is_leeg() -> None:
    """Geen getallen en geen gml:pos leveren allebei een lege lijst, geen fout.

    Anders dan `parse_gml` oordeelt deze functie niet: de knip beslist zelf wat hij met
    een literaal zonder bruikbare coordinatenlijst doet (hij laat hem heel).
    """
    leeg = '<gml:LineString xmlns:gml="g"><gml:posList srsDimension="2"></gml:posList>'
    leeg += "</gml:LineString>"

    assert coordinaattokens(leeg) == []
    assert coordinaattokens('<gml:Point xmlns:gml="g"></gml:Point>') == []
    assert coordinaattokens("dit is geen GML") == []


def test_de_tekstkant_leest_dezelfde_lijst_als_de_lezerskant() -> None:
    """Tokens en `parse_gml` volgen hetzelfde `COORDINATEN_PATROON`, ook op een vormvariant.

    Dit is de winst van het ontdubbelen en meteen de enige plek waar de clip zich nu
    anders gedraagt dan vroeger. De knip droeg een eigen, striktere regex (met een `\\b`
    achter `pos`/`posList`) en zag deze misvormde openingstag niet, terwijl de lezer hem
    wel las: de knip verdeelde dan nul tokens over twee punten en `merge._stapgrootte`
    kwam op stap 0 uit -- de hereniging snoeide niets. Nu lezen beide kanten dezelfde
    lijst en klopt de verhouding weer. Zulke literalen komen niet uit een GWSW-export en
    niet uit de clip zelf, maar wel eventueel uit een deel van elders.
    """
    variant = '<gml:LineString xmlns:gml="g"><gml:posz>1 2 4 5</gml:pos></gml:LineString>'

    assert coordinaattokens(variant) == ["1", "2", "4", "5"]
    assert parse_gml(variant) == LineString([(1, 2), (4, 5)])
    assert tokens_per_punt(variant, 2) == 2


def test_vervang_coordinaten_laat_alles_buiten_de_lijst_staan() -> None:
    """Alleen de inhoud gaat eruit; srsName, srsDimension en de soort blijven letterlijk."""
    literal = (
        '<gml:LineString xmlns:gml="http://www.opengis.net/gml" srsName="EPSG:28992">'
        '<gml:posList srsDimension="3">1 2 30 4 5 60</gml:posList></gml:LineString>'
    )

    assert vervang_coordinaten(literal, "7 8 90") == (
        '<gml:LineString xmlns:gml="http://www.opengis.net/gml" srsName="EPSG:28992">'
        '<gml:posList srsDimension="3">7 8 90</gml:posList></gml:LineString>'
    )


def test_vervang_coordinaten_raakt_alleen_de_eerste_lijst() -> None:
    """Bij twee posLists naast elkaar blijft de tweede ongemoeid.

    De knip raakt zo'n literaal niet aan (`is_multipart_literal` houdt hem tegen), maar
    zou deze functie alle lijsten vervangen dan zou een fout daar een tweede geometrie
    stilzwijgend overschrijven in plaats van zichtbaar mis te gaan.
    """
    twee = (
        '<gml:LineString xmlns:gml="g"><gml:posList srsDimension="2">1 2 4 5</gml:posList>'
        '<gml:posList srsDimension="2">7 8 9 0</gml:posList></gml:LineString>'
    )

    assert vervang_coordinaten(twee, "3 3 3 3") == (
        '<gml:LineString xmlns:gml="g"><gml:posList srsDimension="2">3 3 3 3</gml:posList>'
        '<gml:posList srsDimension="2">7 8 9 0</gml:posList></gml:LineString>'
    )


def test_vervang_coordinaten_zonder_lijst_laat_de_literaal_staan() -> None:
    """Valt er niets te vervangen, dan komt de literaal ongewijzigd terug."""
    assert vervang_coordinaten("dit is geen GML", "1 2") == "dit is geen GML"


def test_vervang_coordinaten_met_de_eigen_tokens_is_de_identiteit() -> None:
    """De aanname onder de knip: een genormaliseerde lijst komt letterlijk terug.

    De hereniging schrijft `vervang_coordinaten(sjabloon, " ".join(tokens))`. Staat de
    bron al met enkele spaties geschreven, dan is dat dezelfde tekst als de bron -- en
    dat is precies de vraag die de knip stelt voordat hij aan een lijn begint. Draagt de
    bron andere scheiders, dan is het antwoord nee.
    """
    ruim = (
        '<gml:LineString xmlns:gml="g"><gml:posList srsDimension="2">1 2  4 5'
        "</gml:posList></gml:LineString>"
    )

    assert vervang_coordinaten(LIJN_2D, " ".join(coordinaattokens(LIJN_2D))) == LIJN_2D
    assert vervang_coordinaten(ruim, " ".join(coordinaattokens(ruim))) != ruim


def test_tokens_per_punt_telt_en_leest_de_srsdimension_niet() -> None:
    """De verhouding tussen de tokens en de punten, en met opzet niet de srsDimension.

    Dat is de keuze waar de knip en zijn omkering op rusten: allebei tellen ze, dus
    allebei komen ze op hetzelfde uit -- ook als de literaal een srsDimension draagt die
    niet klopt met wat erin staat. Zou de een de srsDimension lezen en de ander tellen,
    dan zou de hereniging per punt op de verkeerde plaats snoeien.
    """
    liegt = (
        '<gml:LineString xmlns:gml="g"><gml:posList srsDimension="3">1 2 4 5'
        "</gml:posList></gml:LineString>"
    )

    assert tokens_per_punt(LIJN_3D, 2) == 3
    assert tokens_per_punt(LIJN_2D, 2) == 2
    assert tokens_per_punt(liegt, 2) == 2


def test_tokens_per_punt_kent_ook_een_vierde_getal_per_punt() -> None:
    """Vier getallen op een punt is een geldig antwoord; wie er niets mee kan, zegt dat zelf.

    De knip weigert alles buiten 2 en 3, maar dat is zijn eis en niet die van de teller.
    """
    vier = (
        '<gml:LineString xmlns:gml="g"><gml:posList srsDimension="4">'
        "1 2 3 4 5 6 7 8</gml:posList></gml:LineString>"
    )

    assert tokens_per_punt(vier, 2) == 4


def test_tokens_per_punt_geeft_niets_als_de_verhouding_niet_rondkomt() -> None:
    """Vijf getallen op twee punten, nul punten, een lege lijst: niets af te lezen.

    `None` en geen gok: het aaneen naaien snoeit per punt van de tokenreeks, dus een
    stap van 2 waar de bron er 3 bedoelde levert stilzwijgend een geometrie op die
    niemand ooit geschreven heeft.
    """
    scheef = '<gml:LineString xmlns:gml="g"><gml:posList>1 2 3 4 5</gml:posList></gml:LineString>'
    leeg = '<gml:LineString xmlns:gml="g"><gml:posList></gml:posList></gml:LineString>'

    assert tokens_per_punt(scheef, 2) is None
    assert tokens_per_punt(LIJN_3D, 0) is None
    assert tokens_per_punt(leeg, 2) is None
    assert tokens_per_punt("dit is geen GML", 2) is None
