"""Uitzonderingen van gwsw-orox-helpers.

Twee lagen boven elkaar, en de bovenste twee zijn het contract: `OroxError` is wat een
afnemer van deze package vangt, `DatasetError` is de fout die zegt dat de bron er niet
doorheen komt. Nlriochecker vangt die breed en dat blijft zo -- geen van beide is sinds
hun eerste versie veranderd en dat is een Harde regel in `CLAUDE.md`.

Daaronder staan sinds issue #31 zeven **faalfamilies**. Ze zijn er omdat één klasse 29
raise-plekken dekte met wezenlijk andere oorzaken: een bestand dat niet open gaat, bytes
die geen tekst worden, Turtle die niet parseert, een dataset zonder objecten, een
grenslaag die geen knipinvoer is, een clip die niet rond komt, en een pyoxigraph buiten
de getoetste reeks. Wie alleen `DatasetError` zag, kon "de bron is kapot" niet van "de
clipdelen zijn incompleet" onderscheiden -- terwijl de remedie van die twee niets met
elkaar te maken heeft.

**Additief, en met opzet alleen dat.** Elke familie erft van `DatasetError`, dus elke
bestaande `except DatasetError` en elke `pytest.raises(DatasetError)` vangt ze nog steeds;
geen enkele bestaande meldtekst veranderde mee. Wie de fijnere indeling niet nodig heeft,
merkt er niets van.

**Ingedeeld naar de oorzaak, niet naar de invoer.** Een `OSError` op de grenslaag is
daarom een `BestandError` en geen `GrenslaagError`: het besturingssysteem gaf het bestand
niet, en dat is dezelfde soort fout als bij een TTL-bron. `GrenslaagError` gaat over wat
er in de grenslaag *staat*. Zo blijft de indeling voorspelbaar voor wie een nieuwe
raise-plek moet plaatsen: eerst de vraag "wat ging er stuk", pas daarna "waarin". De regel
heeft één naad, en die staat bij `GrenslaagError` uitgeschreven.

Welke module welke familie hoeveel keer gooit, staat per klasse hieronder en wordt door
`test_de_raise_plekken_staan_waar_de_docstrings_ze_beloven` (`tests/test_uitzonderingen.py`)
tegen de code aan gehouden -- anders zou een raise-plek erbij deze docstrings stilletjes
laten verlopen.

De basisklasse zelf wordt binnen de package nergens meer rechtstreeks gegooid. Ze blijft
staan als het vangnet van de afnemer en als de plek voor een toekomstige oorzaak die in
geen van de zeven families past; wie er een achtste bij zet, zet hem hieronder en niet
naast `DatasetError`.
"""


class OroxError(Exception):
    """Basisfout van de leeslaag; afnemers vangen deze."""


class DatasetError(OroxError):
    """De OroX-dataset ontbreekt, is onleesbaar of bevat geen toetsbare objecten."""


class BestandError(DatasetError):
    """Een bestand liet zich niet openen, lezen of schrijven.

    De fout komt van het besturingssysteem (`OSError`) en gaat dus niet over de inhoud:
    het pad bestaat niet, de rechten ontbreken, de schijf is vol, het doel ligt onder een
    bestand in plaats van onder een map. Geldt voor elk bestand dat deze package aanraakt
    -- de TTL-bron, het schrijfdoel, de GeoJSON-grenslaag en de bestanden die de
    cachesleutel hasht.

    Zes plekken: `bestand._parse`, `schrijven.lees_orox`, `schrijven._gecontroleerd`,
    `schrijven.schrijf_orox_quads`, `clip.grenzen._lees_grenzen` en `cache._bestandshash`.
    `cache._bestandshash` kwam er bij issue #48 bij: `laad_met_cache` hasht de
    invoerbestanden voor de sleutel vóór de eigenlijke lezing, en een onleesbaar bestand
    hoort daar dezelfde `BestandError` te geven als op de directe leesweg (auteursbeslissing
    04-09-2026, met een eigen CHANGELOG-regel). `schrijven._gecontroleerd` kwam er bij issue
    #49 bij: de streamende parser leest schijf pas al aflopend, dus een map als bron of een
    leesfout midden in de stroom valt daar en niet bij de constructie van de parser.
    """


class CoderingError(DatasetError):
    """De bytes van een bestand worden geen tekst.

    Turtle hoort UTF-8 te zijn en niet elke exporttool houdt zich daaraan. Deze fout valt
    als het bestand geen geldige UTF-8 is én er geen bruikbare terugvalcodering is: geen
    opgegeven (`fallback_encoding=None`), of een die Python niet kent, of een waarin de
    bytes evenmin passen. Welke codering een afwijkend bestand dan wel draagt, weet alleen
    de afnemer; dit is dus de fout die om een keuze van hém vraagt.

    Drie plekken: `codering.decodeer` (twee) en `schrijven._gecontroleerd`, die het
    oordeel van de streamende parser overneemt.
    """


class TurtleError(DatasetError):
    """De Turtle-grammatica wordt geschonden.

    De bytes zijn tekst geworden, maar wat erin staat is geen geldige Turtle -- of, aan de
    schrijfkant, een prefixsleutel die geen PN_PREFIX is en die het geschreven bestand
    onleesbaar zou maken. Onderscheiden van `CoderingError` omdat de remedie verschilt:
    daar is de codering van de bron het antwoord, hier de inhoud ervan.

    Drie plekken: `bestand._parse`, `schrijven._gecontroleerd` en de prefixcontrole in
    `schrijven.schrijf_orox_quads`.
    """


class InhoudError(DatasetError):
    """De lezing lukte, en toch is er geen bruikbaar antwoord.

    Niets aan het bestand is stuk: het ging open, het parseerde, en pas daarna blijkt de
    vraag niets te kunnen opleveren. Dat gebeurt van twee kanten. Van de bron: een export
    zonder een enkel knooppunt of streng is waarschijnlijk geen GWSW-OroX. En van de
    vraag: een rol die op een verbindingsklasse geconfigureerd is, kan op dít domeinmodel
    nooit een object opleveren, hoe rijk de dataset verder ook is.

    Wat die twee tot één familie maakt is niet waar de fout vandaan komt maar wat er
    zonder haar zou gebeuren -- allebei zouden ze een **stille nul** teruggeven, en die is
    niet te onderscheiden van een dataset die dit type nu eenmaal niet bevat. Op een
    geconfigureerde rol is dat het verschil tussen "niets gevonden" en "hier valt nooit
    iets te vinden".

    Twee plekken, allebei in `dataset`: `load_dataset` en `GwswDataset.of_class`.
    """


class GrenslaagError(DatasetError):
    """De GeoJSON-grenslaag deugt niet als knipinvoer.

    Het bestand ging open (anders was het een `BestandError`), maar wat erin staat kan de
    clip niet gebruiken: geen leesbare GeoJSON, geen features, een feature zonder de
    naamproperty of met een naam die al gebruikt is, een geometrie die niet te lezen is,
    of een geometrie die geen (multi)vlak is.

    **De ene naad in de indelingsregel hierboven.** "Geen leesbare GeoJSON" valt ook als
    de bytes van de grenslaag geen UTF-8 zijn, en naar de oorzaak gerekend was dat een
    `CoderingError`. Het blijft hier, want die `UnicodeDecodeError` deelt in
    `_lees_grenzen` zijn `except`-blok én zijn meldtekst met de JSON-fout, en die tekst is
    bevroren; twee families op één melding zou de afnemer een onderscheid beloven dat de
    boodschap niet draagt. Het scheelt hem bovendien niets: de terugvalcodering waar
    `CoderingError` om vraagt, kent de grenslaag niet -- GeoJSON *is* UTF-8.

    Zes plekken, alle in `clip.grenzen._lees_grenzen`.
    """


class KnipError(DatasetError):
    """Knippen of herenigen komt niet rond.

    De heen- en terugweg van de clip zijn één belofte -- wat `clip_orox` snijdt, moet
    `merge_orox` weer tot de bron maken -- en daarom deelt hun onvermogen één familie. Wat
    er dan misging: de bron draagt zelf al de knipstaart van de clip, een knippunt krijgt
    geen hoogte, er zijn geen delen opgegeven, een knipmerk is onvolledig, de stukken van
    een lijn komen uit verschillende knipbeurten of ze zijn niet compleet.

    Negen plekken, in `clip.plan`, `clip.knip` (twee), `clip.orkest` en `clip.merge`
    (vijf).
    """


class MotorError(DatasetError):
    """De RDF-motor onder deze package valt buiten de getoetste reeks.

    De enige familie die niet over invoer gaat maar over de installatie: pyoxigraph is
    pre-1.0 en mag tussen twee minors de parse- en serialize-aanroep breken, dus deze
    package weigert op een ongetoetste versie te draaien (zie `rdfmotor`). Voor de afnemer
    is dat de nuttigste scheiding van allemaal -- hier repareer je een omgeving en niet een
    bestand -- en daarom is het een eigen familie en niet de kale `DatasetError` die hij
    tot #31 was. Een `DatasetError` blijft het, want dat is wat elke bestaande `except`
    eromheen verwacht.

    Twee plekken, allebei in `rdfmotor.controleer_versie`.
    """
