"""De IRI's die meer dan een laag van deze package deelt.

Drie lagen schrijven GWSW-IRI's uit: de leeslaag (`dataset` en wat eronder hangt), de
schrijflaag (`schrijven`) en de cliplaag (`clip`). Stond de basis-IRI in elk van die
drie, dan zou een GWSW-versiesprong er twee kunnen bijwerken en de derde vergeten -- en
dat levert geen fout op maar een stille lege uitkomst: een `hasAspect` op 1.6 vindt niets
in een graaf op 1.7. Hier staat hij een keer. Welke versie leidend is, is een
projectafspraak en staat in `CLAUDE.md`.

Sinds issue #29 staat hier ook het *spellen zelf*: `_uri` schrijft een korte klassenaam
uit tot een GWSW-IRI en `_short` leest hem er weer uit terug. Ze stonden in `klassen`, en
dat liet het spellen van `inlezen` en `dataset` langs de klassenlaag lopen -- `inlezen`
haalt met `_short` de korte naam van een soort, een referentie of een klasse. Het zijn
twee `rsplit`-en op een string: ze horen bij de IRI's die ze uit elkaar halen, niet bij de
afsluitingen.

Alleen tekst -- die twee `rsplit`-en meegerekend -- en geen enkele import. De lagen rekenen
in verschillende munteenheden -- de leeslaag in rdflib-termen, de schrijf- en cliplaag in
pyoxigraph-termen -- en die
vertaling hoort bij de laag die haar nodig heeft (`inlezen` maakt er `URIRef`-en van,
`clip` `NamedNode`-en). Zouden de termen hier al gemaakt worden, dan bond deze module
elke laag aan de bibliotheek van de andere.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

# De naamruimten.
GWSW: Final = "http://data.gwsw.nl/1.6/totaal/"
RDF: Final = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS: Final = "http://www.w3.org/2000/01/rdf-schema#"
OWL: Final = "http://www.w3.org/2002/07/owl#"
XSD: Final = "http://www.w3.org/2001/XMLSchema#"
SKOS: Final = "http://www.w3.org/2004/02/skos/core#"
GEO: Final = "http://www.opengis.net/ont/geosparql#"

# De GWSW-properties waar meer dan een laag op leest of schrijft. Het GWSW declareert
# `isPartOf owl:inverseOf hasPart` en `isAspectOf owl:inverseOf hasAspect`, dus een
# conforme export mag de inverse schrijven; wie een van beide leest, leest ze allebei.
HAS_ASPECT: Final = f"{GWSW}hasAspect"
HAS_PART: Final = f"{GWSW}hasPart"
IS_ASPECT_OF: Final = f"{GWSW}isAspectOf"
IS_PART_OF: Final = f"{GWSW}isPartOf"
HAS_CONNECTION: Final = f"{GWSW}hasConnection"
HAS_VALUE: Final = f"{GWSW}hasValue"
HAS_REFERENCE: Final = f"{GWSW}hasReference"

# Het datatype van een geometrieliteraal (de leeslaag herkent haar aan het aspecttype, de
# cliplaag aan dit datatype) en dat van een gewone string (`graaf.naar_rdflib`).
GML_LITERAL: Final = f"{GEO}gmlLiteral"
XSD_STRING: Final = f"{XSD}string"


def _uri(naam: str, basis: str = GWSW) -> str:
    """Maakt van een korte klassenaam een volledige GWSW-URI in de gegeven basis.

    `basis` is standaard de gepinde 1.6-naamruimte (`GWSW`), zodat de bestaande aanroepvorm
    `_uri(naam)` letterlijk hetzelfde blijft doen. Sinds issue #32 kan een aanroeper een
    andere gedetecteerde basis meegeven (`namen.basis_uit_prefixen`), zodat een
    subklasse-afsluiting op een 1.7-graaf de 1.7-IRI opbouwt in plaats van de 1.6-.
    """
    return naam if naam.startswith("http") else f"{basis}{naam}"


def _short(uri: str) -> str:
    """De korte klassenaam achter de laatste scheidingstekens van een URI."""
    return uri.rsplit("/", 1)[-1].rsplit("#", 1)[-1]


# --------------------------------------------------------------------------------------
# De versie-afgeleide termenset (issue #32)
# --------------------------------------------------------------------------------------
#
# De module-constanten hierboven blijven letterlijk 1.6: ze zijn het bevroren contract dat
# nlriochecker via `dataset` importeert (`tests/test_publieke_api.py`). Wat hier bij komt is
# een termenset *per gedetecteerde basis*, zodat de lees- en cliplaag hun predicaten uit de
# bron kunnen afleiden in plaats van uit de vaste 1.6-string. 1.6 blijft de default en de
# terugval; de detectie kiest 1.7 alleen wanneer de bron dat vraagt.

# De basis-IRI van een GWSW-deelmodel Totaal: `http://data.gwsw.nl/<versie>/totaal/`. De
# groep vangt de versie (`1.6`, `1.7`). Zowel de leeslaag (`bestand`) als de cliplaag leidt
# hier haar basis mee af uit de `gwsw:`-prefix of, bij een export zonder die declaratie, uit
# de IRI's in de graaf.
_BASIS_PATROON: Final = re.compile(r"http://data\.gwsw\.nl/(\d+\.\d+)/totaal/")


@dataclass(frozen=True)
class Termen:
    """De GWSW-properties van één basis, als tekst.

    Dezelfde zeven properties die de module-constanten `HAS_*` op 1.6 spellen, maar dan voor
    een gedetecteerde basis. `termen_voor` bouwt hem; `TERMEN_16` is de default. De lezers
    maken er hun eigen munteenheid van (rdflib-`URIRef`, pyoxigraph-`NamedNode`), net als bij
    de constanten -- deze module blijft alleen tekst.
    """

    basis: str
    has_aspect: str
    has_part: str
    is_aspect_of: str
    is_part_of: str
    has_connection: str
    has_value: str
    has_reference: str


def termen_voor(basis: str) -> Termen:
    """De termenset van een basis-IRI (`http://data.gwsw.nl/<versie>/totaal/`)."""
    return Termen(
        basis=basis,
        has_aspect=f"{basis}hasAspect",
        has_part=f"{basis}hasPart",
        is_aspect_of=f"{basis}isAspectOf",
        is_part_of=f"{basis}isPartOf",
        has_connection=f"{basis}hasConnection",
        has_value=f"{basis}hasValue",
        has_reference=f"{basis}hasReference",
    )


# De default en terugval: de gepinde 1.6-termen, hier als termenset. De waarden zijn per
# constructie gelijk aan `HAS_ASPECT`..`HAS_REFERENCE` hierboven.
TERMEN_16: Final = termen_voor(GWSW)


def basis_voor_versie(versie: str) -> str:
    """De basis-IRI van een versienummer, bijvoorbeeld `"1.7"` -> `.../1.7/totaal/`."""
    return f"http://data.gwsw.nl/{versie}/totaal/"


def versie_van_basis(basis: str) -> str | None:
    """De versie in een basis-IRI (`.../1.7/totaal/` -> `"1.7"`), of None."""
    match = _BASIS_PATROON.fullmatch(basis)
    return match.group(1) if match is not None else None


def basis_uit_iri(iri: str) -> str | None:
    """De GWSW-basis waarin deze IRI valt, of None als het geen GWSW-IRI is.

    Voor de terugval-scan over de IRI's in een graaf (een export zonder `gwsw:`-prefix is
    geldig Turtle): een predicaat als `.../1.7/totaal/hasAspect` of een klasse-IRI als
    `.../1.7/totaal/Knooppunt` levert `.../1.7/totaal/`.
    """
    match = _BASIS_PATROON.match(iri)
    return match.group(0) if match is not None else None


def basis_uit_prefixen(prefixen: Mapping[str, str]) -> str | None:
    """De GWSW-basis uit de `gwsw:`-prefixdeclaratie, of None als die er niet (herkenbaar) is.

    De eerste en goedkoopste detectieweg: pyoxigraph levert `parser.prefixes` al. Draagt de
    bron geen `gwsw:`-prefix (geldig Turtle), of wijst hij naar iets buiten het patroon, dan
    geeft dit None en valt de aanroeper terug op een scan over de IRI's zelf.
    """
    gwsw = prefixen.get("gwsw")
    if gwsw is None:
        return None
    return gwsw if _BASIS_PATROON.fullmatch(gwsw) is not None else None
