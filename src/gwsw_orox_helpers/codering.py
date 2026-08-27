"""De codering van een TTL-bestand: UTF-8, en anders de terugval van de afnemer.

Turtle hoort volgens de spec UTF-8 te zijn, maar niet elke exporttool houdt zich daaraan:
de BrutIS-export van De Wolden en Hoogeveen draagt een handvol cp850-bytes in een
straatnaam (`"cavaljeweg"`). Twee lagen lopen daar tegenaan -- de leeslaag die er een
domeinmodel van maakt (`inlezen._parse`) en de schrijflaag die hem terugschrijft
(`schrijven.lees_orox`) -- en ze moeten hem allebei op precies dezelfde manier lezen.
Stond de regel op twee plaatsen, dan zou een verschil erin niet als fout opvallen maar
als een dataset die aan de ene kant anders leest dan aan de andere.

Wat er hier *niet* staat is de keuze welke codering dat dan is: die is van de afnemer en
niet van deze package (Harde regel in `CLAUDE.md`). `fallback_encoding=None` betekent
"geen terugval" en is een eigen keuze, geen ontbrekende waarde.

Het verslag (`DecodeFallback`) staat er los van, want het is niet gratis: het telt de
afwijkende bytes en zoekt de regels waarin ze staan, en dat is een tweede gang over het
hele bestand. Wie een bestand terugschrijft heeft dat verslag niet nodig en hoort er ook
niet voor te betalen; wie een lezing rapporteert wel.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gwsw_orox_helpers.errors import DatasetError


@dataclass(frozen=True)
class DecodeFallback:
    """Vastlegging dat een bestand niet als UTF-8 gelezen kon worden."""

    path: Path
    encoding: str
    byte_count: int
    samples: list[str]


def decodeer(pad: Path, rauw: bytes, fallback_encoding: str | None) -> tuple[str, str | None]:
    """Decodeert de inhoud als UTF-8, of anders met de terugvalcodering.

    Turtle hoort UTF-8 te zijn, maar niet elke exporttool houdt zich daaraan. Wijkt een
    bestand af, dan hoort dat vastgelegd en gerapporteerd te worden; stilzwijgend
    vervangen van tekens zou de inhoud ongemerkt veranderen. Zonder terugvalcodering
    (`None`) is er niets om op terug te vallen en is de afwijking een fout: welke codering
    een afwijkend bestand dan wel draagt, weet alleen de afnemer.

    De tweede uitkomst is de codering waarmee teruggevallen is, of `None` als het bestand
    gewoon UTF-8 was. Daarmee weet de aanroeper of er iets te rapporteren valt zonder de
    tekst nog een keer te hoeven wegen; `terugvalverslag` maakt er dan het verslag bij.
    """
    try:
        return rauw.decode("utf-8"), None
    except UnicodeDecodeError as error:
        # De uitzondering bestaat niet meer buiten dit blok; leg de feiten nu vast.
        eerste_byte, eerste_positie = rauw[error.start], error.start

    if fallback_encoding is None:
        raise DatasetError(
            f"{pad}: geen geldige UTF-8 (byte {eerste_byte:#04x} op positie "
            f"{eerste_positie}) en er is geen terugvalcodering opgegeven."
        )

    try:
        tekst = rauw.decode(fallback_encoding)
    except (UnicodeDecodeError, LookupError) as fout:
        raise DatasetError(
            f"{pad}: geen geldige UTF-8 (byte {eerste_byte:#04x} op positie "
            f"{eerste_positie}) en ook niet te lezen als {fallback_encoding} ({fout})."
        ) from fout
    return tekst, fallback_encoding


def terugvalverslag(pad: Path, rauw: bytes, encoding: str) -> DecodeFallback:
    """Legt vast hoeveel bytes er van UTF-8 afweken en in welke regels ze stonden."""
    # De niet-ASCII-bytes tellen zonder een Python-lus over alle 112 MB: `translate`
    # verwijdert in C alle bytes 0x00-0x7F, en wat overblijft zijn er precies de bytes
    # groter dan 0x7F.
    byte_count = len(rauw.translate(None, bytes(range(0x80))))
    return DecodeFallback(
        path=pad,
        encoding=encoding,
        byte_count=byte_count,
        samples=_fallback_samples(rauw, encoding),
    )


def _fallback_samples(rauw: bytes, encoding: str, limiet: int = 5) -> list[str]:
    """De regels waarin de niet-ASCII-bytes staan, ter controle door de gebruiker."""
    voorbeelden: list[str] = []
    for index, byte in enumerate(rauw):
        if byte <= 0x7F:
            continue
        start = rauw.rfind(b"\n", 0, index) + 1
        eind = rauw.find(b"\n", index)
        regel = rauw[start : eind if eind != -1 else len(rauw)]
        tekst = regel.decode(encoding, "replace").strip()
        if tekst not in voorbeelden:
            voorbeelden.append(tekst)
        if len(voorbeelden) >= limiet:
            break
    return voorbeelden
