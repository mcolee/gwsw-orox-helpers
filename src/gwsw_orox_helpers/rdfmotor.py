"""De ene plek waar deze package pyoxigraph aanroept: ontleden, serialiseren, versiepoort.

pyoxigraph is de motor onder allebei de paden door deze package -- de leesweg
(`bestand._parse`, die de quadstroom in een `GraafIndex` giet) en de schrijfweg
(`schrijven.lees_orox` naar `schrijf_orox_quads`, die de stroom rechtstreeks doorgeeft).
Die twee paden blijven verschillend, want ze stellen verschillende vragen (zie
`docs/architectuur.md`); wat ze deelden was de **aanroep** van de motor, en die stond tot
nu toe op vier plekken uitgeschreven. Hier staat hij één keer.

Dat maakt een minor-bump van pyoxigraph een een-naadswijziging. De motor is pre-1.0: 0.3
naar 0.4 brak de parse-signatuur al eens, en 0.5 naar 0.6 mag dat weer. Zonder deze naad
zou zo'n bump zich melden als een `TypeError` diep in de quadstroom, op de plek waar de
eerste quad opgehaald wordt en niet op de plek waar de aanroep staat.

**Dun, en met opzet niet meer dan dat.** Alleen ontleden en serialiseren gaan hierlangs.
Ontleden heeft sinds issue #66 drie ingangen -- `ontleed_turtle` (bytes of str in het
geheugen), `ontleed_turtle_bestand` (een pad, de motor opent en streamt zelf) en
`ontleed_turtle_stroom` (een binaire file-like, `input=`) -- en geen typeswitch daarop:
`path=` en `input=` doen iets anders (zie de docstrings hieronder en
`docs/architectuur.md`), dus een `str`-pad zou in de inhoudstak stil de padtekst lezen.
De term-fabrieken (`NamedNode`, `BlankNode`, `Literal`, `Quad`, `Triple`) worden
*niet* omwikkeld: die staan op tientallen plekken in `clip/` en in `graaf`, ze zijn
sinds 0.3 niet veranderd, en een wrapper eromheen zou een laag zijn zonder werk.
Wie ze nodig heeft, importeert pyoxigraph rechtstreeks -- dat is geen omissie maar de
grens van deze module. Dat de naad er ook echt één blijft, is geen belofte in deze
docstring maar een test: `test_alleen_rdfmotor_roept_de_motor_aan` loopt de AST van elke
module in de package af en laat een vijfde `pyoxigraph.parse` niet toe.

**De versiepoort staat naast de cap in `pyproject.toml` en niet in plaats daarvan.** De
cap (`pyoxigraph>=0.5,<0.6`) voorkomt dat een verse install een ongetoetste minor trekt;
hij kan omzeild worden (`pip install --no-deps`, een conda-omgeving, een handmatige
upgrade in een bestaande venv) en dan is er niets meer dat waarschuwt. De poort hieronder
is die waarschuwing. Ze staat **bij het importeren van deze module en niet per aanroep**,
om twee redenen. Ze kost dan niets in de hete lus. En ze valt vóór het eerste bestand:
een `MotorError` zit niet in de smalle vangst van `bestand._parse` (`MOTORFOUTEN` plus
`TypeError`) en zou per aanroep dus rauw naar buiten komen op de plek waar de eerste quad
opgehaald wordt in plaats van waar de aanroep staat. Bij het importeren valt de poort
vóór dat alles en blijft daarom de juiste plek.
`ONDERSTEUNDE_REEKS` en de cap worden aan elkaar geknoopt door
`test_de_reeks_is_dezelfde_als_de_cap_in_pyproject`, zodat ze niet uit elkaar lopen.

De fout is sinds issue #31 een `MotorError`, en dat is een *subklasse* van `DatasetError`
en geen soort ernaast. Dat onderscheid draagt de hele keuze: `DatasetError` is wat deze
package voor "de bron komt er niet doorheen" belooft en wat haar afnemers vangen, dus een
type dat daar niet onder hangt zou langs elke bestaande `except DatasetError` glippen.
Eronder hangen mag wel, en hier is het de moeite: dit is de enige fout van de package die
niet over invoer gaat maar over de installatie eronder, en wie hem apart wil herkennen
repareert een omgeving en geen bestand.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import IO, Final

import pyoxigraph

from gwsw_orox_helpers.errors import MotorError

# Deze package leest en schrijft Turtle en verder niets; de andere RDF-formaten die de
# motor kan, komen in een OroX-uitwisseling niet voor.
_TURTLE: Final = pyoxigraph.RdfFormat.TURTLE

# De getoetste reeks, als (major, minor). Ondergrens erbij, bovengrens eraf -- dezelfde
# vorm als de cap in `pyproject.toml`.
ONDERSTE_VERSIE: Final[tuple[int, int]] = (0, 5)
EERSTE_ONGETOETSTE_VERSIE: Final[tuple[int, int]] = (0, 6)
ONDERSTEUNDE_REEKS: Final = (
    f">={ONDERSTE_VERSIE[0]}.{ONDERSTE_VERSIE[1]},"
    f"<{EERSTE_ONGETOETSTE_VERSIE[0]}.{EERSTE_ONGETOETSTE_VERSIE[1]}"
)

# `major.minor` aan het begin van de versietekst; wat erachter komt (`.9`, `rc1`, een
# lokale suffix) doet voor de reeks niet ter zake.
_VERSIEKOP: Final = re.compile(r"\A(\d+)\.(\d+)")


def controleer_versie(versie: str) -> None:
    """Weigert een pyoxigraph buiten de getoetste reeks, met een leesbare boodschap.

    Een versie die niet als `major.minor` te lezen is, wordt óók geweigerd. Doorgaan op
    een motor die zich niet laat identificeren is precies wat deze poort moet voorkomen:
    de uitkomst zou dan alsnog een rauwe fout in de quadstroom zijn, en dan met een
    versie erbij waar niemand iets aan heeft.
    """
    kop = _VERSIEKOP.match(versie)
    if kop is None:
        raise MotorError(
            f"pyoxigraph meldt versie {versie!r}; daar is geen major.minor uit te lezen, dus "
            f"is niet te zeggen of hij binnen de getoetste reeks {ONDERSTEUNDE_REEKS} valt. "
            "De reeks staat in `gwsw_orox_helpers.rdfmotor` en als cap in pyproject.toml."
        )
    gevonden = (int(kop.group(1)), int(kop.group(2)))
    if ONDERSTE_VERSIE <= gevonden < EERSTE_ONGETOETSTE_VERSIE:
        return
    raise MotorError(
        f"pyoxigraph {versie} valt buiten de reeks {ONDERSTEUNDE_REEKS} waarop "
        "gwsw-orox-helpers getoetst is. pyoxigraph is pre-1.0 en mag tussen twee minors "
        "de parse- en serialize-aanroep breken, dus deze package weigert erop te draaien. "
        "Installeer een pyoxigraph binnen de reeks; is de nieuwe versie wél getoetst, werk "
        "dan `gwsw_orox_helpers.rdfmotor` en de cap in pyproject.toml samen bij."
    )


def ontleed_turtle(bron: bytes | str) -> pyoxigraph.QuadParser:
    """Ontleedt Turtle die al in het geheugen staat, als luie quadstroom.

    De leeslaag komt hier langs met de UTF-8-bytes van de al gedecodeerde tekst, de
    schrijfweg met die tekst zelf zodra er een `fallback_encoding` in het spel is. Wie
    een bestand van schijf wil laten stromen, neemt `ontleed_turtle_bestand`.

    Wat eruit komt is het parserobject zelf en niet een kale iterator: `lees_orox` heeft
    naast de stroom ook `parser.prefixes` nodig, dat pas gevuld is als de kop gelezen is.

    Er wordt hier **niets afgevangen**: een syntaxfout onderweg komt er als de fout van de
    motor uit. `bestand._parse` en `schrijven._gecontroleerd` maken daar hun eigen
    `TurtleError` van, elk met de formulering die hun afnemers kennen.
    """
    return pyoxigraph.parse(bron, format=_TURTLE)


def ontleed_turtle_bestand(pad: Path) -> pyoxigraph.QuadParser:
    """Ontleedt een Turtle-bestand streamend van schijf, als luie quadstroom.

    Een eigen ingang en geen `isinstance`-tak in `ontleed_turtle`, want het verschil is
    niet cosmetisch: `path=` laat de motor het bestand zelf openen en regel voor regel
    lezen -- dat is wat een export van honderden megabytes buiten het geheugen houdt --
    terwijl dezelfde waarde als `input` de *padtekst* als Turtle zou ontleden. Eén functie
    met een typeswitch zou dat verschil aan `isinstance(bron, Path)` ophangen en een
    `str`-pad stilzwijgend als inhoud lezen; hier kan dat niet.

    Net als bij `ontleed_turtle` wordt er niets afgevangen. Een ontbrekend of onleesbaar
    bestand komt er als `OSError` uit -- `lees_orox` vangt die zelf en maakt er "bestand
    kan niet gelezen worden" van -- en een syntaxfout onderweg pas bij de quad waar hij
    staat, waar `schrijven._gecontroleerd` hem oppikt.
    """
    return pyoxigraph.parse(path=pad, format=_TURTLE)


def ontleed_turtle_stroom(io: IO[bytes]) -> pyoxigraph.QuadParser:
    """Ontleedt Turtle uit een geopende binaire file-like, als luie quadstroom.

    De derde ingang, naast `ontleed_turtle(bytes | str)` en `ontleed_turtle_bestand(pad)`,
    en geen typeswitch daarop -- om dezelfde reden dat die twee gescheiden zijn (zie boven
    en `docs/architectuur.md`): `path=` laat de motor het bestand zelf openen, `input=`
    ontleedt de inhoud die eruit stroomt. Deze ingang geeft altijd de file-like als
    `input=` door en de motor leest hem blokgewijs -- hij houdt de inhoud dus niet als
    `str` of `bytes` in het geheugen (issue #66).

    Wie hem gebruikt: `schrijven.lees_orox` zodra er een terugvalcodering of een BOM in
    het spel is, met een hercodeerstroom (`codering.hercodeerstroom`) die de bron
    blokgewijs van de terugvalcodering naar UTF-8 hercodeert. Zo blijft de schrijfweg ook
    op die tak streamend in plaats van de hele bron als `str` in het geheugen te zetten.

    Net als bij de twee andere ingangen wordt er **niets afgevangen**: een syntaxfout
    onderweg komt er als de fout van de motor uit, en `schrijven._gecontroleerd` maakt er
    zijn eigen `TurtleError` van. De aanroeper opent en sluit de file-like zelf; de motor
    leest hem enkel.
    """
    return pyoxigraph.parse(io, format=_TURTLE)


# De fouttaxonomie van de motor, op één plek. `bestand._parse` en `schrijven._gecontroleerd`
# vertalen deze fouten naar hun eigen `DatasetError`-familie; wat de motor daarbuiten laat
# ontsnappen (`MemoryError`, `RecursionError`, een bug in eigen code) hoort niet als "geen
# geldige Turtle" verpakt te worden en komt bij die aanroepers rauw naar buiten. Deze tuple
# is de ene plek waar `SyntaxError` als motor-fouttype staat; de AST-sweep in
# `tests/test_rdfmotor.py` weert hem buiten deze module.
MOTORFOUTEN: Final = (SyntaxError, ValueError)


def is_coderingsfout(fout: Exception) -> bool:
    """Of een motorfout in werkelijkheid over de bytecodering gaat en niet over de syntaxis.

    pyoxigraph meldt niet-UTF-8-bytes met "Invalid UTF-8" in de tekst van de fout. De
    leeslaag en de schrijfweg onderscheiden dat van een echte syntaxfout, want de remedie
    verschilt: daar is een terugvalcodering het antwoord, hier de inhoud van de bron. De
    tekstmatch woont hier zodat beide aanroepers hetzelfde oordeel delen.
    """
    return "Invalid UTF-8" in str(fout)


def prefixen_van(parser: pyoxigraph.QuadParser) -> dict[str, str]:
    """De prefixdeclaraties die de parser tot nu toe uit de kop las.

    Alleen gevuld nadat de kop gelezen is (in de praktijk na de eerste quad). `bestand._parse`
    leidt er de GWSW-basis uit af, `schrijven.lees_orox` bouwt er de prefixkop mee. Dat die
    lezing hierlangs loopt, houdt `parser.prefixes` -- net als parse en serialize -- binnen de
    ene motor-naad; `test_de_foutvertaling_en_de_prefixen_wonen_alleen_in_rdfmotor` bewaakt dat.
    """
    return parser.prefixes


def serialiseer_turtle(
    quads: Iterable[pyoxigraph.Quad] | Iterable[pyoxigraph.Triple],
    doel: IO[bytes],
    *,
    prefixen: dict[str, str],
) -> None:
    """Schrijft `quads` als Turtle naar een geopend binair bestand.

    De enige `pyoxigraph.serialize` van deze package. `doel` is met opzet een geopend
    bestand en geen pad: `schrijf_orox_quads` schrijft naar een tijdelijk bestand naast
    het doel en hernoemt pas na de laatste quad, en dat mag deze laag niet kunnen
    overslaan.

    `quads` mag lui zijn en wordt al schrijvend afgelopen; breekt hij halverwege af, dan
    komt die fout hier onveranderd doorheen. `prefixen` gaat ongewijzigd door naar de
    kop -- de geldigheid van de sleutels bewaakt `schrijf_orox_quads` zelf, want de motor
    doet dat niet.
    """
    pyoxigraph.serialize(quads, doel, _TURTLE, prefixes=prefixen)


# De poort, één keer, bij het importeren van deze module. Onderaan, zodat een reload met
# een verzette versie (de test) de definities hierboven wel bijwerkt.
controleer_versie(pyoxigraph.__version__)
