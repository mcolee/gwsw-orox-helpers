"""De afgeleide eigenschappen van `Aspect`, `Node` en `Conduit`.

Het zijn kleine afleidingen op de dataclasses zelf -- een kenmerk opzoeken, een
millimetermaat naar meters brengen, een verval uitrekenen -- en ze worden hier
rechtstreeks getoetst in plaats van via een geladen fixture. Zo staat er bij een
verkeerde uitkomst geen lader tussen die de oorzaak kan zijn.
"""

from __future__ import annotations

from datetime import date

import pytest
from shapely.geometry import LineString, Point

from gwsw_orox_helpers.dataset import Aspect, Conduit, Node

KENMERKEN = (
    Aspect("HoogtePut", value="1500"),
    Aspect("MateriaalPut", reference="Beton"),
    Aspect("Begindatum", value="1980-01-01"),
)


def _node(**extra) -> Node:
    """Een knoop met de drie kenmerken hierboven; `extra` overschrijft de velden."""
    velden: dict = {
        "uri": "http://example.org/toets#PutA",
        "label": "A",
        "types": frozenset(),
        "orientation": None,
        "orientation_types": frozenset(),
        "point": Point(1000.0, 2000.0),
        "z": None,
        "parents": (),
        "aspects": KENMERKEN,
    }
    velden.update(extra)
    return Node(**velden)


def _conduit(**extra) -> Conduit:
    """Een streng zonder kenmerken; `extra` vult ze aan."""
    velden: dict = {
        "uri": "http://example.org/toets#L1",
        "label": "1",
        "types": frozenset(),
        "line": LineString([(1000.0, 2000.0), (1050.0, 2000.0)]),
        "start_node": None,
        "end_node": None,
    }
    velden.update(extra)
    return Conduit(**velden)


# --- Aspect ----------------------------------------------------------------


def test_aspect_number_leest_een_getal() -> None:
    assert Aspect("HoogtePut", value="1500").number == 1500.0


def test_aspect_number_zonder_waarde_is_none() -> None:
    assert Aspect("HoogtePut").number is None


def test_aspect_number_bij_een_niet_numerieke_waarde_is_none() -> None:
    """Een export mag tekst in een getalveld zetten; dat is geen leesfout maar niets."""
    assert Aspect("HoogtePut", value="onbekend").number is None


@pytest.mark.parametrize(
    ("waarde", "verwacht"),
    [
        ("1980-01-01", date(1980, 1, 1)),
        ("1980-01-01T00:00:00", date(1980, 1, 1)),
        # Een kaal jaartal telt als 1 januari.
        ("1980", date(1980, 1, 1)),
        # ISO-vorm, maar februari heeft geen dertigste.
        ("1980-02-30", None),
        # Jaartalvorm, maar jaar 0 bestaat niet in `datetime.date`.
        ("0000", None),
        ("geen datum", None),
        (None, None),
    ],
)
def test_aspect_date(waarde: str | None, verwacht: date | None) -> None:
    assert Aspect("Begindatum", value=waarde).date == verwacht


# --- de kenmerklezers op een object ----------------------------------------


def test_aspect_zoekt_op_klassenaam() -> None:
    gevonden = _node().aspect("MateriaalPut")

    assert gevonden is not None
    assert gevonden.reference == "Beton"


def test_aspect_dat_er_niet_is_levert_none() -> None:
    assert _node().aspect("BreedtePut") is None


def test_number_reference_en_date_lezen_het_gevonden_kenmerk() -> None:
    knoop = _node()

    assert knoop.number("HoogtePut") == 1500.0
    assert knoop.reference("MateriaalPut") == "Beton"
    assert knoop.date("Begindatum") == date(1980, 1, 1)


def test_number_reference_en_date_zwijgen_over_een_ontbrekend_kenmerk() -> None:
    knoop = _node()

    assert knoop.number("BreedtePut") is None
    assert knoop.reference("VormPut") is None
    assert knoop.date("Einddatum") is None


# --- Node ------------------------------------------------------------------


def test_hoogte_m_rekent_millimeters_naar_meters() -> None:
    assert _node().hoogte_m == 1.5


def test_hoogte_m_zonder_puthoogte_is_none() -> None:
    assert _node(aspects=()).hoogte_m is None


def test_bovenkant_kiest_het_deksel_boven_het_maaiveld() -> None:
    knoop = _node(
        maaiveld_aspect=Aspect("Maaiveldhoogte", value="10.00"),
        deksel_aspect=Aspect("Putdekselniveau", value="9.95"),
    )

    assert knoop.maaiveld == 10.00
    assert knoop.dekselniveau == 9.95
    assert knoop.bovenkant == 9.95


def test_bovenkant_valt_terug_op_het_maaiveld() -> None:
    knoop = _node(maaiveld_aspect=Aspect("Maaiveldhoogte", value="10.00"))

    assert knoop.dekselniveau is None
    assert knoop.bovenkant == 10.00


def test_bodem_is_de_bovenkant_min_de_puthoogte() -> None:
    knoop = _node(deksel_aspect=Aspect("Putdekselniveau", value="9.95"))

    assert knoop.bodem == pytest.approx(8.45)


@pytest.mark.parametrize("aspecten", [(), KENMERKEN])
def test_bodem_ontbreekt_zonder_bovenkant_of_puthoogte(aspecten: tuple[Aspect, ...]) -> None:
    """Zonder puthoogte of zonder bovenkant is de bodem onbekend, niet nul."""
    zonder_hoogte = _node(aspects=(), deksel_aspect=Aspect("Putdekselniveau", value="9.95"))
    zonder_bovenkant = _node(aspects=aspecten)

    assert zonder_hoogte.bodem is None
    assert zonder_bovenkant.bodem is None


# --- Conduit ---------------------------------------------------------------


def test_z_waarden_van_de_uiteinden() -> None:
    streng = _conduit(z_values=(8.60, 8.55, 8.50))

    assert streng.z_start == 8.60
    assert streng.z_end == 8.50


def test_zonder_z_waarden_zwijgen_de_uiteinden() -> None:
    streng = _conduit()

    assert streng.z_start is None
    assert streng.z_end is None


def test_bob_verval_is_begin_min_eind() -> None:
    streng = _conduit(
        bob_start_aspect=Aspect("BobBeginpuntLeiding", value="8.60"),
        bob_end_aspect=Aspect("BobEindpuntLeiding", value="8.55"),
    )

    assert streng.bob_start == 8.60
    assert streng.bob_end == 8.55
    assert streng.bob_verval == pytest.approx(0.05)


def test_bob_verval_ontbreekt_met_maar_een_bob() -> None:
    streng = _conduit(bob_start_aspect=Aspect("BobBeginpuntLeiding", value="8.60"))

    assert streng.bob_end is None
    assert streng.bob_verval is None


def test_maatvoering_en_materiaal_van_een_streng() -> None:
    streng = _conduit(
        aspects=(
            Aspect("BreedteLeiding", value="300"),
            Aspect("HoogteLeiding", value="300"),
            Aspect("LengteLeiding", value="50.0"),
            Aspect("MateriaalLeiding", reference="Beton"),
            Aspect("VormLeiding", reference="Rond"),
            Aspect("Begindatum", value="1980-01-01"),
        )
    )

    assert streng.breedte_mm == 300.0
    assert streng.hoogte_mm == 300.0
    assert streng.lengte_m == 50.0
    assert streng.materiaal == "Beton"
    assert streng.vorm == "Rond"
    assert streng.begindatum_jaar == 1980


def test_een_streng_zonder_kenmerken_zwijgt_over_alles() -> None:
    streng = _conduit()

    assert streng.breedte_mm is None
    assert streng.hoogte_mm is None
    assert streng.lengte_m is None
    assert streng.materiaal is None
    assert streng.vorm is None
    assert streng.begindatum_jaar is None
