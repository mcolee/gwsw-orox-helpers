"""Tests voor het lezen van een OroX-export die geen geldige UTF-8 is."""

from __future__ import annotations

from pathlib import Path

import pytest

from gwsw_orox_helpers import codering
from gwsw_orox_helpers.dataset import load_dataset
from gwsw_orox_helpers.errors import CoderingError, DatasetError

TTL_DIR = Path(__file__).parent / "fixtures" / "ttl"
MINI = TTL_DIR / "mini_orox.ttl"
CP850 = TTL_DIR / "codering_cp850.ttl"


def test_utf8_bestand_meldt_geen_terugval() -> None:
    dataset = load_dataset(TTL_DIR / "schoon.ttl", ontology_paths=[])

    assert dataset.decode_fallback is None


def test_utf8_bom_leest_gelijk_aan_zonder_bom(tmp_path: Path) -> None:
    """Een UTF-8-BOM vooraan maakt een verder geldige export niet onleesbaar (issue #53).

    Sommige exporttools (Windows-editors) schrijven een BOM; die hoort geen `TurtleError`
    op te leveren. `utf-8-sig` in `codering.decodeer` accepteert UTF-8 mét en zonder BOM,
    dus leest de dataset met BOM dezelfde knopen en strengen als zonder, en er valt niets
    terug te melden.
    """
    bom = tmp_path / "mini_bom.ttl"
    bom.write_bytes(b"\xef\xbb\xbf" + MINI.read_bytes())

    zonder = load_dataset(MINI, ontology_paths=[])
    met = load_dataset(bom, ontology_paths=[])

    assert len(met.nodes) == len(zonder.nodes) == 2
    assert len(met.conduits) == len(zonder.conduits)
    assert zonder.decode_fallback is None
    assert met.decode_fallback is None


def test_decodeer_accepteert_utf8_met_en_zonder_bom() -> None:
    """De gedeelde decodeerregel: `utf-8-sig` is een superset van `utf-8` op BOM-loze invoer.

    Dit is het ene punt dat beide paden dekt -- `bestand._decode` (leesweg) en
    `schrijven.lees_orox` via `codering.hercodeerstroom` (schrijfweg) delen deze regel. De
    BOM verdwijnt uit de tekst en er is niets teruggevallen (`None`); zonder BOM verandert
    er niets.
    """
    pad = Path("mem.ttl")

    assert codering.decodeer(pad, b"\xef\xbb\xbf:a :b :c .", None) == (":a :b :c .", None)
    assert codering.decodeer(pad, b":a :b :c .", None) == (":a :b :c .", None)


def test_bom_loze_terugval_geeft_hetzelfde_verslag() -> None:
    """De terugvalcodering-tak blijft ongewijzigd op een BOM-loze latin-1-bron (issue #53).

    `utf-8-sig` raakt alleen een leidende BOM; een BOM-loze cp850-bron valt nog net zo terug
    als voorheen -- zelfde codering, zelfde afwijkende byte in het verslag.
    """
    rauw = CP850.read_bytes()

    tekst, gebruikt = codering.decodeer(CP850, rauw, "cp850")
    verslag = codering.terugvalverslag(CP850, rauw, "cp850")

    assert gebruikt == "cp850"
    assert "cavaljéweg" in tekst
    assert verslag.encoding == "cp850"
    assert verslag.byte_count == 1
    assert any("cavaljéweg" in sample for sample in verslag.samples)


def test_bom_foutpositie_telt_de_bom_mee() -> None:
    """Met BOM meldt de CoderingError de bestand-positie, BOM incluis (issue #53).

    `utf-8-sig` rapporteert `error.start` relatief aan de BOM-gestripte tekst; de melding
    hoort de positie te geven die een gebruiker in een hex-editor ziet -- inclusief de drie
    BOM-bytes. De foute byte 0x81 staat op bestand-positie 9, niet op 6.
    """
    rauw = b"\xef\xbb\xbf:a :b " + bytes([0x81]) + b" :c ."

    with pytest.raises(CoderingError, match=r"byte 0x81 op positie 9"):
        codering.decodeer(Path("x.ttl"), rauw, None)


def test_bom_loze_foutpositie_blijft_ongewijzigd() -> None:
    """Zonder BOM verschuift de gemelde positie niet: byte 0x81 op positie 6 (issue #53)."""
    rauw = b":a :b " + bytes([0x81]) + b" :c ."

    with pytest.raises(CoderingError, match=r"byte 0x81 op positie 6"):
        codering.decodeer(Path("x.ttl"), rauw, None)


def test_bom_foutpositie_ook_als_terugval_faalt() -> None:
    """Ook de terugval-faalt-tak meldt de bestand-positie inclusief BOM (issue #53)."""
    rauw = b"\xef\xbb\xbf:a :b " + bytes([0x81]) + b" :c ."

    with pytest.raises(CoderingError, match=r"byte 0x81 op positie 9.*ook niet te lezen als ascii"):
        codering.decodeer(Path("x.ttl"), rauw, "ascii")


def test_cp850_bestand_wordt_gelezen_en_vastgelegd() -> None:
    # Turtle hoort UTF-8 te zijn; de BrutIS-export van De Wolden en Hoogeveen is dat niet.
    # De package kent geen standaardcodering: de afnemer geeft er zelf een op.
    dataset = load_dataset(
        TTL_DIR / "codering_cp850.ttl", ontology_paths=[], fallback_encoding="cp850"
    )
    fallback = dataset.decode_fallback

    assert fallback is not None
    assert fallback.encoding == "cp850"
    assert fallback.byte_count == 1
    assert any("cavaljéweg" in sample for sample in fallback.samples)
    # De rest van de dataset is gewoon bruikbaar.
    assert len(dataset.conduits) == 1


def test_eigen_terugvalcodering(tmp_path: Path) -> None:
    # Met cp1252 levert dezelfde byte een ander teken op; de keuze is expliciet.
    dataset = load_dataset(
        TTL_DIR / "codering_cp850.ttl", ontology_paths=[], fallback_encoding="cp1252"
    )

    assert dataset.decode_fallback.encoding == "cp1252"
    assert not any("cavaljéweg" in sample for sample in dataset.decode_fallback.samples)


def test_onleesbare_codering_geeft_dataseterror(tmp_path: Path) -> None:
    stuk = tmp_path / "stuk.ttl"
    stuk.write_bytes(b"@prefix : <http://x#> .\n:a :b \x82 .\n")

    with pytest.raises(DatasetError, match="geen geldige UTF-8"):
        load_dataset(stuk, fallback_encoding="onbekende-codering")


def _stroombytes(pad: Path, fallback_encoding: str | None) -> bytes:
    """De hele hercodeerstroom uitgelezen -- wat de motor via `input=` te zien krijgt."""
    with codering.hercodeerstroom(pad, fallback_encoding) as stroom:
        return stroom.read()


def test_hercodeerstroom_van_utf8_levert_de_bronbytes() -> None:
    """Een zuivere UTF-8-bron: de stroom is de bron zelf, byte voor byte (oracle: decodeer)."""
    verwacht = codering.decodeer(MINI, MINI.read_bytes(), None)[0].encode("utf-8")

    assert _stroombytes(MINI, None) == verwacht
    assert _stroombytes(MINI, "cp850") == verwacht  # UTF-8 wint van de terugval


def test_hercodeerstroom_van_cp850_hercodeert_naar_utf8() -> None:
    """Een cp850-bron: de stroom levert dezelfde UTF-8-bytes als de niet-streamende weg.

    `decodeer` is het onafhankelijke ijkpunt van de coderingsregel; de incrementele
    variant hoort er byte voor byte gelijk aan te zijn (issue #66).
    """
    verwacht = codering.decodeer(CP850, CP850.read_bytes(), "cp850")[0].encode("utf-8")
    gekregen = _stroombytes(CP850, "cp850")

    assert gekregen == verwacht
    assert "cavaljéweg".encode() in gekregen


def test_hercodeerstroom_van_bom_bron_strip_de_bom(tmp_path: Path) -> None:
    """Een UTF-8-BOM-bron zonder terugval: de stroom is de tekst zónder BOM (utf-8-sig)."""
    bom = tmp_path / "mini_bom.ttl"
    bom.write_bytes(b"\xef\xbb\xbf" + MINI.read_bytes())
    verwacht = codering.decodeer(bom, bom.read_bytes(), None)[0].encode("utf-8")

    gekregen = _stroombytes(bom, None)

    assert gekregen == verwacht
    assert not gekregen.startswith(b"\xef\xbb\xbf")


def test_hercodeerstroom_kiest_pas_na_de_hele_bron_de_codering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """De valkuil: een bron die pas ná het eerste blok een niet-UTF-8-byte draagt.

    Een blokgewijze decoder mag niet halverwege van codering wisselen: het eerste blok is
    zuiver UTF-8, maar verderop staat een cp850-byte. De keuze moet over de héle bron gaan
    (net als `decodeer`, die het hele bestand weegt), dus valt de bron in zijn geheel op de
    terugval terug -- niet blok 1 als UTF-8 en blok 2 als cp850. Bewijs: byte-gelijk aan
    `decodeer`, dat de cp850-byte als 'é' leest en niet als een gehalveerd UTF-8-teken.
    """
    monkeypatch.setattr(codering, "_LEESBLOK", 8)
    bron = tmp_path / "laat.ttl"
    # Ruim voorbij byte 8 een losse 0x82 (cp850 'é'), ingebed in een literaal zodat de tekst
    # geldig blijft; als UTF-8 is 0x82 een losse vervolgbyte en dus ongeldig.
    bron.write_bytes(b'@prefix : <http://x#> .\n:a :b "cavalj\x82weg" .\n')
    verwacht = codering.decodeer(bron, bron.read_bytes(), "cp850")[0].encode("utf-8")

    gekregen = _stroombytes(bron, "cp850")

    assert gekregen == verwacht
    assert "cavaljéweg".encode() in gekregen


def test_hercodeerstroom_zonder_terugval_is_een_coderingerror() -> None:
    """Geen geldige UTF-8 en geen terugval: dezelfde CoderingError als `decodeer`."""
    with pytest.raises(CoderingError, match="geen terugvalcodering"):
        codering.hercodeerstroom(CP850, None)


def test_hercodeerstroom_onbekende_codering_is_een_coderingerror() -> None:
    """Een terugval die Python niet kent: CoderingError met de naam erin, als `decodeer`."""
    with pytest.raises(CoderingError, match="onbekende-codering"):
        codering.hercodeerstroom(CP850, "onbekende-codering")


def test_hercodeerstroom_terugval_faalt_is_een_coderingerror(tmp_path: Path) -> None:
    """Een terugval die de bytes toch niet leest: CoderingError 'ook niet te lezen als'.

    Anders dan de twee gevallen hierboven -- geen terugval, en een onbekende codec, die
    allebei vóór het streamen te zien zijn -- blijkt een terugval die de bytes wél als
    tekst begint maar onderweg struikelt pas bij het lezen. De fout komt dan uit `readinto`
    en hoort dezelfde canonieke `CoderingError` te zijn (via `decodeer`), niet een rauwe
    `UnicodeDecodeError` die de motor-vangst als `TurtleError` zou labelen.
    """
    stuk = tmp_path / "stuk.ttl"
    stuk.write_bytes(b"@prefix : <http://x#> .\n:a :b \x82 .\n")

    with pytest.raises(CoderingError, match="ook niet te lezen als ascii"):
        with codering.hercodeerstroom(stuk, "ascii") as stroom:
            stroom.read()
