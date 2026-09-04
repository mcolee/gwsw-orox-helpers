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

import logging
from pathlib import Path

import pytest

from gwsw_orox_helpers import bestand
from gwsw_orox_helpers.bestand import _parse
from gwsw_orox_helpers.errors import TurtleError


def _geldige_bron(tmp_path: Path) -> Path:
    bron = tmp_path / "ok.ttl"
    bron.write_text("@prefix : <http://x#> .\n:a :b :c .\n", encoding="utf-8")
    return bron


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
