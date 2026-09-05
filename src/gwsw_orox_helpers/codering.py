"""De codering van een TTL-bestand: UTF-8, en anders de terugval van de afnemer.

Turtle hoort volgens de spec UTF-8 te zijn, maar niet elke exporttool houdt zich daaraan:
de BrutIS-export van De Wolden en Hoogeveen draagt een handvol cp850-bytes in een
straatnaam (`"cavaljeweg"`). Twee lagen lopen daar tegenaan -- de leeslaag die er een
domeinmodel van maakt (`bestand._parse`) en de schrijflaag die hem terugschrijft
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

import codecs
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import IO, TYPE_CHECKING, Final

from gwsw_orox_helpers.errors import CoderingError

if TYPE_CHECKING:
    from _typeshed import WriteableBuffer

# Elke byte die geen ASCII is; het zoeken ernaar gebeurt zo in C en niet per byte in
# Python. Zie `_fallback_samples`.
_NIET_ASCII: Final = re.compile(rb"[\x80-\xff]")

# De bron wordt bij het hercoderen blokgewijs gelezen; een blok van 1 MiB houdt de
# decode-encode-lus in C en het geheugen laag (zie `hercodeerstroom`).
_LEESBLOK: Final = 1 << 20


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

    UTF-8 wordt met `utf-8-sig` gelezen: een strikt ruimere superset die een verder geldig
    bestand mét of zonder een leidende UTF-8-BOM (`U+FEFF`) leest en die BOM uit de tekst
    haalt. Zonder de BOM zou pyoxigraph over dat teken struikelen als eerste subject
    (issue #53); op BOM-loze invoer is `utf-8-sig` gelijk aan `utf-8`. De terugvaltak raakt
    dit niet: een BOM-loze bron die geen UTF-8 is, valt net als voorheen op de opgegeven
    codering terug (die de ruwe bytes leest, BOM incluis als die er exotisch genoeg is).
    """
    try:
        return rauw.decode("utf-8-sig"), None
    except UnicodeDecodeError as error:
        # De uitzondering bestaat niet meer buiten dit blok; leg de feiten nu vast.
        # `utf-8-sig` strip een leidende BOM en telt `error.start` vanaf de gestripte
        # tekst; tel de BOM-lengte erbij op zodat de positie het bestand-offset is (wat de
        # gebruiker in een hex-editor ziet), en `rauw` op de juiste byte wijst (issue #53).
        bom_verschuiving = len(codecs.BOM_UTF8) if rauw.startswith(codecs.BOM_UTF8) else 0
        eerste_positie = error.start + bom_verschuiving
        eerste_byte = rauw[eerste_positie]

    if fallback_encoding is None:
        raise CoderingError(
            f"{pad}: geen geldige UTF-8 (byte {eerste_byte:#04x} op positie "
            f"{eerste_positie}) en er is geen terugvalcodering opgegeven."
        )

    try:
        tekst = rauw.decode(fallback_encoding)
    except (UnicodeDecodeError, LookupError) as fout:
        raise CoderingError(
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
    """De regels waarin de niet-ASCII-bytes staan, ter controle door de gebruiker.

    Twee dingen houden dit weg van een Python-lus over alle bytes. Het zoeken naar de
    volgende afwijkende byte doet `_NIET_ASCII.search` in C -- een `for byte in rauw`
    over de 112 MB van De Wolden en Hoogeveen kostte 4,8 van de 27 seconden van
    `load_dataset`, en dat voor vijf voorbeeldregels. En na een regel springt de scan
    over de rest van die regel heen: elke verdere afwijkende byte erin zou dezelfde
    tekst opleveren, en die staat er dan al in.
    """
    voorbeelden: list[str] = []
    einde = len(rauw)
    positie = 0
    while (treffer := _NIET_ASCII.search(rauw, positie)) is not None:
        index = treffer.start()
        start = rauw.rfind(b"\n", 0, index) + 1
        eind = rauw.find(b"\n", index)
        regel = rauw[start : eind if eind != -1 else einde]
        tekst = regel.decode(encoding, "replace").strip()
        if tekst not in voorbeelden:
            voorbeelden.append(tekst)
        if len(voorbeelden) >= limiet:
            break
        positie = eind + 1 if eind != -1 else einde
    return voorbeelden


def hercodeerstroom(pad: Path, fallback_encoding: str | None) -> IO[bytes]:
    """Een streamende file-like die de bron blokgewijs als UTF-8-bytes levert.

    De incrementele tegenhanger van `decodeer`, voor de schrijfweg (`schrijven.lees_orox`,
    issue #66): waar `decodeer` het hele bestand als bytes én als `str` in het geheugen zet,
    leest deze weg per blok, decodeert met een incrementele decoder en encodeert naar UTF-8,
    zodat de motor (`rdfmotor.ontleed_turtle_stroom`) de inhoud via `input=` binnenstroomt
    zonder een kopie van de hele bron. Op de cp850-export van De Wolden en Hoogeveen scheelt
    dat per passage honderden MiB.

    **Dezelfde coderingsregel als `decodeer`, alleen incrementeel.** Eerst UTF-8 (via
    `utf-8-sig`, dat een leidende BOM eruit haalt), en pas als de bron dat niet blijkt de
    terugval. Die keuze gaat over de **hele bron**: `_zuiver_utf8` weegt het bestand
    blokgewijs, zodat een bron die pas ná het eerste blok een niet-UTF-8-byte draagt niet
    half als UTF-8 en half als terugval gelezen wordt (de valkuil van een blokgewijze
    decoder). Slaagt UTF-8, dan streamt de bron als `utf-8-sig`; anders de terugval.

    De foutmeldingen zijn die van `decodeer` -- letterlijk, want op een foutpad laat deze
    functie `decodeer` de `CoderingError` gooien (dat pad leest de bron alsnog als bytes,
    maar het is een foutpad en geen hete lus): geen geldige UTF-8 en geen terugval, een
    terugval die Python niet kent, of een terugval die de bytes toch niet leest. Een
    `OSError` (ontbrekende bron, een map) propageert naar `lees_orox`, dat er dezelfde
    `BestandError` van maakt als voorheen.
    """
    if _zuiver_utf8(pad):
        codering = "utf-8-sig"
    elif fallback_encoding is None:
        # Geen geldige UTF-8 en geen terugval: `decodeer` gooit de canonieke CoderingError.
        decodeer(pad, pad.read_bytes(), None)
        raise AssertionError("onbereikbaar: decodeer had moeten falen")  # pragma: no cover
    else:
        try:
            codecs.getincrementaldecoder(fallback_encoding)
        except LookupError:
            # Onbekende codec: `decodeer` gooit de CoderingError met de naam erin.
            decodeer(pad, pad.read_bytes(), fallback_encoding)
            raise AssertionError("onbereikbaar") from None  # pragma: no cover
        codering = fallback_encoding
    return io.BufferedReader(_Hercodeerder(pad, codering, fallback_encoding), _LEESBLOK)


def _zuiver_utf8(pad: Path) -> bool:
    """Of de hele bron blokgewijs als `utf-8-sig` te decoderen is (BOM toegestaan).

    Streamend, zodat een grote bron niet in het geheugen hoeft, en over het héle bestand:
    een niet-UTF-8-byte -- waar dan ook -- geeft False, zodat de terugval aan zet is (de
    valkuil van `hercodeerstroom`). Een leidende BOM telt als geldig; `utf-8-sig` haalt hem
    eruit, net als `decodeer`. Een `OSError` propageert naar de aanroeper.
    """
    decoder = codecs.getincrementaldecoder("utf-8-sig")()
    with open(pad, "rb") as bron:
        blok = bron.read(_LEESBLOK)
        try:
            while blok:
                decoder.decode(blok)
                blok = bron.read(_LEESBLOK)
            decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            return False
    return True


class _Hercodeerder(io.RawIOBase):
    """Leest `pad` blokgewijs, decodeert met `codering` en levert UTF-8-bytes.

    De file-like die `hercodeerstroom` teruggeeft. `codering` is `utf-8-sig` (dan is de
    stroom de bron zonder BOM) of de terugval; `fallback_encoding` reist mee zodat een
    decodeerfout onderweg -- alleen mogelijk als de gekozen terugval de bron toch niet
    volledig leest -- via `decodeer` dezelfde `CoderingError` krijgt als de niet-streamende
    weg, in plaats van als rauwe `UnicodeDecodeError` (een `ValueError`) door de
    motor-vangst als `TurtleError` verkeerd gelabeld te worden.
    """

    def __init__(self, pad: Path, codering: str, fallback_encoding: str | None) -> None:
        super().__init__()
        self._pad = pad
        self._fallback_encoding = fallback_encoding
        self._decoder = codecs.getincrementaldecoder(codering)()
        self._rest = b""
        self._bestand: IO[bytes] | None = None
        self._bestand = open(pad, "rb")

    def readable(self) -> bool:
        return True

    def readinto(self, doel: WriteableBuffer) -> int:
        assert self._bestand is not None
        while not self._rest:
            blok = self._bestand.read(_LEESBLOK)
            try:
                self._rest = self._decoder.decode(blok, final=not blok).encode("utf-8")
            except UnicodeDecodeError as fout:
                # De gekozen terugval leest de bron toch niet volledig; laat `decodeer` de
                # canonieke CoderingError gooien (dezelfde die de niet-streamende weg gaf).
                decodeer(self._pad, self._pad.read_bytes(), self._fallback_encoding)
                raise AssertionError("onbereikbaar") from fout  # pragma: no cover
            if not blok and not self._rest:
                return 0
        uitzicht = memoryview(doel).cast("B")
        n = min(len(uitzicht), len(self._rest))
        uitzicht[:n] = self._rest[:n]
        self._rest = self._rest[n:]
        return n

    def close(self) -> None:
        try:
            if self._bestand is not None:
                self._bestand.close()
        finally:
            super().close()
