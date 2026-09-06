"""De smalle vangst van `bestand._parse` rond de motor en het vullen van de index.

Sinds issue #50 vangt `_parse` alleen nog de fouten die de motor en `graaf.naar_rdflib`
legitiem gooien -- `rdfmotor.MOTORFOUTEN` (`SyntaxError`, `ValueError`) plus de `TypeError`
uit `naar_rdflib` op een termsoort die niet in een Turtle-parse hoort -- en vertaalt die
naar de contractvaste `TurtleError`. Alles daarbuiten (`MemoryError`, `RecursionError`, een
bug in eigen code) komt rauw naar buiten in plaats van als een misleidende "geen geldige
Turtle ()" met een lege oorzaak. Vóór #50 ving de brede `except Exception` ze allemaal, en
een `MemoryError` bij het vullen van de index kwam als lege `TurtleError` naar buiten op een
bron die niets mankeerde (de meting in het issue: `RLIMIT_AS` krap, `load_dataset` op de
gebundelde ontologie).
"""

from __future__ import annotations

import codecs
import logging
from pathlib import Path

import pytest

from gwsw_orox_helpers import bestand, rdfmotor
from gwsw_orox_helpers.bestand import _parse
from gwsw_orox_helpers.errors import BestandError, CoderingError, TurtleError

_INHOUD = '@prefix : <http://x#> .\n:a :b :c .\n:d :naam "café" .\n'


def _geldige_bron(tmp_path: Path) -> Path:
    bron = tmp_path / "ok.ttl"
    bron.write_text("@prefix : <http://x#> .\n:a :b :c .\n", encoding="utf-8")
    return bron


class _MotorSpion:
    """Telt welke van de twee ontleedingangen van `rdfmotor` `_parse` aanroept.

    De streamende tak (issue #60) leest een zuivere UTF-8-bron met
    `ontleed_turtle_bestand` (de motor opent het bestand zelf) in plaats van met
    `ontleed_turtle` op de gehercodeerde bytes. De spion delegeert naar de echte functie,
    zodat de parse echt gebeurt en de graaf te vergelijken blijft.
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.bestand = 0
        self.geheugen = 0
        echt_bestand = rdfmotor.ontleed_turtle_bestand
        echt_geheugen = rdfmotor.ontleed_turtle

        def stream(pad: Path) -> object:
            self.bestand += 1
            return echt_bestand(pad)

        def geheugen(bron: bytes | str) -> object:
            self.geheugen += 1
            return echt_geheugen(bron)

        monkeypatch.setattr(bestand.rdfmotor, "ontleed_turtle_bestand", stream)
        monkeypatch.setattr(bestand.rdfmotor, "ontleed_turtle", geheugen)


def _bron(tmp_path: Path, naam: str, rauw: bytes) -> Path:
    pad = tmp_path / naam
    pad.write_bytes(rauw)
    return pad


def test_een_zuivere_utf8_bron_gaat_langs_de_streamende_ingang(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Een zuivere UTF-8-bron zonder BOM leest de motor streamend van schijf (issue #60).

    Geen `read_bytes` + `decode` + `encode` met drie buffers naast elkaar; alleen de
    chunksgewijze validatie en daarna `ontleed_turtle_bestand`. Er valt niets terug te
    melden.
    """
    bron = _bron(tmp_path, "utf8.ttl", _INHOUD.encode("utf-8"))
    spion = _MotorSpion(monkeypatch)

    index, fallback = _parse(bron, None)

    assert spion.bestand == 1
    assert spion.geheugen == 0
    assert fallback is None
    assert len(index) == 2


def test_een_cp850_bron_gaat_langs_de_gedecodeerde_weg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Een niet-UTF-8-bron kan niet streamen; hij gaat langs de terugvalcodering (issue #60)."""
    bron = _bron(tmp_path, "cp850.ttl", _INHOUD.encode("cp850"))
    spion = _MotorSpion(monkeypatch)

    index, fallback = _parse(bron, "cp850")

    assert spion.bestand == 0
    assert spion.geheugen == 1
    assert fallback is not None
    assert fallback.encoding == "cp850"
    assert len(index) == 2


def test_een_bom_bron_streamt_niet_maar_meldt_geen_terugval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Een UTF-8-BOM is geldig UTF-8 maar breekt de streamende motor (issue #53/#60).

    De bron gaat daarom langs de gedecodeerde weg (`utf-8-sig` haalt de BOM eruit), maar
    er is niets teruggevallen: `decode_fallback` blijft None.
    """
    bron = _bron(tmp_path, "bom.ttl", codecs.BOM_UTF8 + _INHOUD.encode("utf-8"))
    spion = _MotorSpion(monkeypatch)

    index, fallback = _parse(bron, None)

    assert spion.bestand == 0
    assert spion.geheugen == 1
    assert fallback is None
    assert len(index) == 2


def test_een_niet_benodigde_terugvalcodering_leest_toch_streamend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Een opgegeven terugval die niet nodig blijkt, houdt de streamende weg (issue #60).

    Is de bron feitelijk zuiver UTF-8 zonder BOM, dan stroomt hij van schijf ook al gaf de
    afnemer een `fallback_encoding` op; er valt dan immers niets terug te melden.
    """
    bron = _bron(tmp_path, "utf8.ttl", _INHOUD.encode("utf-8"))
    spion = _MotorSpion(monkeypatch)

    index, fallback = _parse(bron, "cp850")

    assert spion.bestand == 1
    assert spion.geheugen == 0
    assert fallback is None
    assert len(index) == 2


def test_de_streamende_en_de_gedecodeerde_tak_geven_dezelfde_graaf(tmp_path: Path) -> None:
    """Dezelfde inhoud levert dezelfde graaf, langs welke tak dan ook (issue #60).

    De UTF-8-bron stroomt (fallback None), de cp850-bron valt terug (fallback gezet), maar
    de triples zijn identiek -- de tak is een interne optimalisatie, geen andere lezing.
    """
    utf8 = _bron(tmp_path, "utf8.ttl", _INHOUD.encode("utf-8"))
    cp850 = _bron(tmp_path, "cp850.ttl", _INHOUD.encode("cp850"))

    stroom_index, stroom_fallback = _parse(utf8, "cp850")
    terugval_index, terugval_fallback = _parse(cp850, "cp850")

    assert len(stroom_index) == len(terugval_index)
    assert stroom_index._spo.keys() == terugval_index._spo.keys()
    assert stroom_fallback is None
    assert terugval_fallback is not None


def test_een_niet_utf8_bron_zonder_terugval_blijft_een_coderingsfout(tmp_path: Path) -> None:
    """Zonder terugvalcodering blijft een niet-UTF-8-bron een `CoderingError` (issue #60).

    De streamende validatie faalt op de niet-UTF-8-byte, de gedecodeerde weg neemt het
    over, en `codering.decodeer` meldt de ontbrekende terugval -- ongewijzigd gedrag.
    """
    bron = _bron(tmp_path, "cp850.ttl", _INHOUD.encode("cp850"))

    with pytest.raises(CoderingError, match="geen geldige UTF-8"):
        _parse(bron, None)


def test_een_leesfout_in_de_streamende_tak_wordt_een_bestanderror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """De streamende parser leest schijf al aflopend; een `OSError` onderweg is `BestandError`.

    Net als een map als bron of een weggevallen share aan de schrijfkant (issue #49): een
    leesfout terwijl `vul_uit` de streamende parser aftapt, hoort dezelfde "kan niet gelezen
    worden" te geven als `read_bytes` in de gedecodeerde tak (issue #60).
    """
    bron = _bron(tmp_path, "utf8.ttl", _INHOUD.encode("utf-8"))

    def geen_schijf(self: object, quads: object) -> None:
        raise OSError("leesfout op de share")

    monkeypatch.setattr(bestand.GraafIndex, "vul_uit", geen_schijf)
    with pytest.raises(BestandError, match="kan niet gelezen worden"):
        _parse(bron, None)


def test_een_typefout_in_de_gedecodeerde_tak_wordt_een_turtleerror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """De smalle vangst van de gedecodeerde tak vertaalt de `TypeError` uit `naar_rdflib`.

    Een cp850-bron gaat niet streamend; hij loopt langs `ontleed_turtle` op de gedecodeerde
    tekst, waar dezelfde smalle vangst als vanouds een `TypeError` uit `graaf.naar_rdflib`
    tot `TurtleError` maakt (issue #50/#60).
    """
    bron = _bron(tmp_path, "cp850.ttl", _INHOUD.encode("cp850"))

    def verkeerde_term(self: object, quads: object) -> None:
        raise TypeError("onverwachte termsoort in een Turtle-parse")

    monkeypatch.setattr(bestand.GraafIndex, "vul_uit", verkeerde_term)
    with pytest.raises(TurtleError, match="geen geldige Turtle"):
        _parse(bron, "cp850")


def test_een_memoryerror_bij_het_vullen_komt_rauw_naar_buiten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Een `MemoryError` uit `vul_uit` is geen Turtle-fout en wordt niet als zodanig verpakt.

    Dit is de meting van issue #50: onder een krappe geheugengrens gaf `vul_uit` een
    `MemoryError` die de brede `except Exception` als "geen geldige Turtle ()" presenteerde
    -- een lege syntaxfout op een correcte bron. De smalle vangst laat hem doorlopen.
    """
    bron = _geldige_bron(tmp_path)

    def geen_geheugen(self: object, quads: object) -> None:
        raise MemoryError("geheugen op")

    monkeypatch.setattr(bestand.GraafIndex, "vul_uit", geen_geheugen)
    with pytest.raises(MemoryError):
        _parse(bron, None)


def test_een_typefout_uit_naar_rdflib_wordt_wel_een_turtleerror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`naar_rdflib` gooit `TypeError` op een termsoort die niet in Turtle hoort.

    Die valt wél binnen de smalle vangst -- ze komt uit het vullen van de index, niet uit
    eigen bugcode -- en wordt de contractvaste `TurtleError`.
    """
    bron = _geldige_bron(tmp_path)

    def verkeerde_term(self: object, quads: object) -> None:
        raise TypeError("onverwachte termsoort in een Turtle-parse")

    monkeypatch.setattr(bestand.GraafIndex, "vul_uit", verkeerde_term)
    with pytest.raises(TurtleError, match="geen geldige Turtle"):
        _parse(bron, None)


def test_een_echte_syntaxfout_blijft_een_turtleerror_met_regelnummer(tmp_path: Path) -> None:
    """De smalle vangst laat een echte Turtle-syntaxfout onveranderd `TurtleError` blijven.

    Met het regelnummer dat de motor in zijn melding zet ("line 4"), zodat de smalle vangst
    de leesbaarheid van de foutmelding niet inruilt voor de correctheid van de taxonomie.
    """
    stuk = tmp_path / "stuk.ttl"
    stuk.write_text("@prefix : <http://x#> .\n:a :b :c .\n:d :e\n", encoding="utf-8")

    with pytest.raises(TurtleError) as fout:
        _parse(stuk, None)

    boodschap = str(fout.value)
    assert "geen geldige Turtle" in boodschap
    assert "line 4" in boodschap


def test_quiet_rdflib_dempt_alleen_bij_een_ongezet_niveau() -> None:
    """Zonder eigen niveau (NOTSET) dempt de contextmanager, en herstelt in de finally.

    De meegeleverde ontologie draagt een `xsd:date "20210830"` zonder streepjes; rdflib logt
    daar een traceback bij die niet in de CLI-uitvoer thuishoort. Een afnemer die zelf geen
    niveau op `rdflib.term` zette, hoort die demping als vanouds te krijgen.
    """
    logger = logging.getLogger("rdflib.term")
    origineel = logger.level
    try:
        logger.setLevel(logging.NOTSET)
        with bestand._quiet_rdflib():
            assert logger.level == logging.ERROR  # gedempt tijdens de parse
        assert logger.level == logging.NOTSET  # en in de finally hersteld
    finally:
        logger.setLevel(origineel)


def test_quiet_rdflib_laat_een_eigen_niveau_met_rust() -> None:
    """Een afnemer die `rdflib.term` op DEBUG zette, houdt dat niveau tijdens en na de parse.

    De demping is procesbreed en `rdflib.term` is niet van ons: een afnemer die zijn eigen
    niveau koos (bv. DEBUG om die waarschuwingen juist te zien, of om ze in een parallelle
    thread niet te missen) hoort dat niveau niet ongevraagd naar ERROR te zien springen
    (issue #55).
    """
    logger = logging.getLogger("rdflib.term")
    origineel = logger.level
    try:
        logger.setLevel(logging.DEBUG)
        with bestand._quiet_rdflib():
            assert logger.level == logging.DEBUG  # de afnemer houdt zijn niveau tijdens de parse
        assert logger.level == logging.DEBUG  # en erna ook
    finally:
        logger.setLevel(origineel)
