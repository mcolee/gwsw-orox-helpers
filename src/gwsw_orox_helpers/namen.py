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


def _uri(naam: str) -> str:
    """Maakt van een korte klassenaam een volledige GWSW-URI."""
    return naam if naam.startswith("http") else f"{GWSW}{naam}"


def _short(uri: str) -> str:
    """De korte klassenaam achter de laatste scheidingstekens van een URI."""
    return uri.rsplit("/", 1)[-1].rsplit("#", 1)[-1]
