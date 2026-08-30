"""Een OroX-dataset ruimtelijk verdelen en de delen weer verliesloos herenigen.

`clip_orox` knipt een OroX-export langs een grenslaag (GeoJSON, N vlakken) in N
OroX-bestanden; `merge_orox` maakt daar weer het origineel van. "Weer het origineel"
is hier geen benadering maar de eis: `merge(clip(bron))` parseert naar dezelfde
RDF-graaf als `bron` -- dezelfde triples, dezelfde literalen tot op de byte, dezelfde
blanke-knoopstructuur.

**Eigen pad, net als `schrijven`.** Deze laag raakt `dataset.py` en `graaf.py` niet
aan en bouwt geen domeinmodel: ze leest de bron met `schrijven.lees_orox` als
quadstroom en schrijft de delen met `schrijven.schrijf_orox_quads` weg. Gedeeld met de
leeslaag zijn alleen de GML-lezers uit `geometry` -- de knip moet dezelfde coordinaten
zien als de leeslaag -- en de IRI's uit `namen`, want een `hasAspect` die hier anders
gespeld werd dan daar zou de verkeerde helft van de graaf verdelen zonder ergens te
klagen.

## De fasen, elk in een eigen submodule

Dit bestand draagt het verhaal en de her-export; het werk staat per fase apart. `A -> B`
betekent weer "A importeert B", en elke pijl wijst naar een regel *boven* zich --
`tests/test_publieke_api.py` (`test_de_clipsubmodules_houden_de_importrichting`) houdt die
richting aan de broncode bij, samen met de regel dat geen enkele fase de leeslaag ziet.
Dezelfde tekening staat in `docs/architectuur.md`, waar ze naast die van de leeslaag hoort;
loopt er ooit een uit elkaar, dan is de test de scheidsrechter.

```
termen    <- blad binnen clip/: de knip-naamruimte, de vaste termen, de stuknamen
grenzen   <- blad binnen clip/: de GeoJSON-vlakken en hun bestandsnaam
knip      -> grenzen                          (geometrie plaatsen en doorknippen; `_Stuk`)
plan      -> grenzen, knip, termen            (de analyseronde; `_Plan`, `_maak_plan`)
stroom    -> knip, plan, termen               (de gefilterde quadstroom per deel)
merge     -> termen                           (de delen weer aaneen)
bereik    -> grenzen, termen                  (de opt-in bereikcontrole; naast de fasen)
orkest    -> grenzen, plan, stroom, merge, bereik, termen  (`clip_orox`, `merge_orox`)
__init__  -> orkest
```

`bereik` staat in die rij achteraan en niet in het midden: hij is geen stap van de knip maar
de controle ernaast (zie hieronder), en alleen `orkest` roept hem aan.

De vier stappen hieronder zijn `plan`; "de knip en zijn omkering" is `knip` plus `merge`.

## Wat er verdeeld wordt

De graaf valt uiteen in **blokken**: een blok is een benoemd subject met al zijn
triples, plus de blanke knopen die eraan hangen (en die aan die knopen hangen). Blanke
knopen zijn documentgebonden -- zie de moduledocstring van `schrijven` -- dus een blok
gaat altijd in zijn geheel naar een deel en wordt nooit doormidden gesneden. Moet een
blok in meer dan een deel staan (gedeelde structuur, of een leiding die de grens
kruist), dan draagt **elk deel zijn eigen volledige kopie** en ontdubbelt `merge_orox`
op inhoud.

De toewijzing van blokken aan vlakken gaat in vier stappen:

1. **Geometrie zaait.** De geometrie zit niet op het object maar op een
   orientatie-aspect (`gwsw:Punt` / `gwsw:Lijn` met `gwsw:hasValue
   "<gml...>"^^geo:gmlLiteral`, zie `inlezen._geometry`). Een punt gaat naar het vlak
   waarin het valt; een lijn die binnen een vlak blijft ook; een lijn die de grens
   kruist wordt doorgeknipt (zie hieronder). Een vlakgeometrie (`gwsw:Buitengrens`)
   wordt niet geknipt maar op haar representatieve punt toegewezen.
2. **Omhoog.** Elke houder (via `hasPart`/`hasAspect`, in beide schrijfrichtingen)
   krijgt de vereniging van de vlakken van zijn afstammelingen. Zo staat de gedeelde
   structuur -- de wortel, het `Rioleringsgebied`, het stelsel, de straat -- in elk
   deel dat een afstammeling bevat.
3. **Omlaag.** Wat dan nog geen vlak heeft (een onderdeel zonder eigen geometrie: een
   drempel, een hulpstuk, een BOB-kenmerk) erft de vlakken van zijn houders. Zit de
   houder aan beide kanten van de grens -- een doorgeknipte leiding -- dan versmalt
   het **aanhechtingspunt** de keuze: de `gwsw:hasConnection` van het onderdeel wijst
   naar een orientatie die zelf wel een vlak heeft, en dat vlak wint.
4. **Rest.** Wat nergens aan hangt (de ontologiekop) gaat naar elk deel.

**De terugval op het dichtstbijzijnde vlak, en wanneer die tegen je werkt.** Een geometrie
die in geen enkel vlak valt gaat naar het vlak dat er het dichtst bij ligt
(`knip._vlak_van`), zodat er nooit een object buiten de boot valt: een grenslaag dekt zelden
precies alles wat een export bevat, en wat nergens heen kan zou bij de hereniging ontbreken.
Diezelfde terugval maakt de gemeenste gebruikersfout van de clip onzichtbaar. Staat de
grenslaag in een ander coordinaatstelsel dan de bron -- WGS84-graden tegen de RD-meters die
de GML-literalen impliciet laten -- dan valt *geen enkel* punt in een vlak en schuiven ze
allemaal naar hetzelfde dichtstbijzijnde vlak. Wat eruit komt is een deel dat de hele bron
draagt en N-1 delen met alleen de ontologiekop, en de hereniging klopt nog steeds: er is geen
fout te zien. `clip_orox(..., bereikcontrole=True)` legt daarom op verzoek de omhullende van
de grenslaag naast die van de bron en waarschuwt als de twee niet bij elkaar kunnen horen;
`clip.bereik` draagt dat oordeel en de reden waarom het een waarschuwing is en geen
weigering. Standaard staat de controle uit, en dan gedraagt de clip zich als hiervoor.

Daarna gaat stap 2 nog een keer, zodat de vlakken van een houder altijd die van zijn
onderdelen omvatten -- voor elke `hasPart`/`hasAspect`-rand. Die insluiting is wat elk
deel zelfdekkend maakt: zo'n rand wordt namelijk naar de vlakken van het *onderdeel*
geschreven, en die zitten dan altijd ook in de houder.

**Wat wel over de grens mag wijzen.** Een `gwsw:hasConnection` van een geknipte
leiding naar de put aan de overkant blijft staan. Dat is geen weesverwijzing die op te
lossen valt maar de knip zelf: de put in het andere deel halen zou hem verdubbelen en
de objecttelling per deel onbruikbaar maken. Het is ook precies de verwijzing die na
`merge_orox` weer klopt.

Datzelfde geldt voor een verwijzing *naar* een geknipte geometrieknoop uit een vlak waar
die geen enkel stuk heeft. Voor `hasPart`/`hasAspect` valt zo'n rand hier weg -- die
wordt naar de vlakken van het onderdeel geschreven en staat daar wel -- maar elk ander
predicaat heeft die tweede thuisbasis niet. Zo'n triple blijft dus staan en wijst naar de
*ongeknipte* naam: de naam die na de hereniging weer bestaat. Stil overslaan zou hem uit
de hereniging laten verdwijnen, en dat is precies wat deze module belooft niet te doen.

## De knip en zijn omkering

Een lijn die de grens kruist wordt op de kruispunten in stukken gedeeld. Elk stuk
komt op een eigen knoop te staan -- `<origineel>__knip<k>`, met dezelfde soort en
dezelfde overige triples als het origineel -- en draagt daarnaast zijn knipmerken:

- `knip:herkomst` -- de sleutel van de oorspronkelijke geometrieknoop;
- `knip:volgnummer` en `knip:aantal` -- de plaats in het origineel;
- `knip:ingevoegdEinde` -- of het laatste punt van dit stuk een ingevoegd knippunt is.

`merge_orox` naait ze per herkomst weer aaneen: van elk stuk na het eerste vervalt het
eerste punt (dat herhaalt het laatste punt van het vorige stuk) en van elk stuk met
`knip:ingevoegdEinde` vervalt het laatste punt (dat is het ingevoegde knippunt).

Daarnaast krijgt de **houder** van een geknipte geometrie het merk `knip:geknipt`. Dat
merk leest `merge_orox` niet -- het gaat met de rest van de `knip:`-naamruimte weg -- het
is er voor de afnemer van een deel. Wie een deel op zichzelf leest, ziet daar een leiding
met een geometrie die korter is dan haar lengtekenmerk en die niet meer in haar
eindpunten aankomt; `knip:geknipt` op de orientatie is het antwoord op de vraag of dat
een fout in de data is of het gevolg van de knip. Het staat op de orientatie en niet op
het stuk, want dat is de knoop waar een controle op geometrie en aanhechting kijkt.

**Twee stukken in dezelfde helft.** Een leiding die de grens heen en weer kruist, laat in
een helft meer dan een stuk na. Die stukken sluiten nooit op elkaar aan: tussen twee
stukken van dezelfde helft ligt per constructie een stuk van een andere (`_segmenten`
voegt gelijke buren samen), dus er valt in die helft geen enkele lijn van te maken. Wat
de helft draagt is dan een leiding met een **meerdelige** geometrie, en dat is precies wat
meer dan een `gwsw:Lijn`-aspect onder een orientatie in OroX betekent. De leeslaag leest
het ook zo: `load_dataset` zet `Conduit.multipart` aan (`inlezen._is_multipart`), dus er
komt geen halve leiding uit die zich als een hele voordoet. De stukken een eigen
orientatie geven zou het alternatief zijn, maar dat vraagt om een kopie van het hele
orientatieblok inclusief zijn blanke knopen en om het terugvouwen daarvan bij de
hereniging -- meer risico voor de exactheid dan de meerdelige geometrie kost.

**Waarom dat exact is en geen float-tolerantie nodig heeft.** De stukken worden niet
uit shapely-coordinaten teruggeschreven maar uit de **tekst** van de bron: de
coordinatenlijst van de GML-literaal wordt op tokens gesplitst
(`geometry.coordinaattokens`) en de stukken krijgen plakjes van diezelfde tokens, die met
`geometry.vervang_coordinaten` in het omhulsel van de bron terugkomen -- de knip heen en
de hereniging terug met dezelfde twee functies, zodat een GML-vormvariant aan beide kanten
hetzelfde gelezen wordt. Alleen het knippunt is een nieuw geschreven getal. Wat
er na het snoeien overblijft is dus letterlijk de oorspronkelijke tekst, tot en met de
`233000.00` die een float-omweg als `233000.0` zou hebben teruggegeven. Het issue nam
aan dat het knippunt aan zijn collineariteit herkend moest worden, met een tolerantie
die bros kon blijken; dat is hier niet nodig -- welk punt ingevoegd is staat
opgeschreven. Een tolerantie speelt alleen bij het *zoeken* van de kruispunten
(`_TOLERANTIE`, 1 micrometer): valt een kruispunt op een bestaande vertex, dan wordt
er geen punt ingevoegd en blijft die vertex gewoon staan.

**Niet geknipt** wordt een multi-geometrie, en dat is `geometry.is_multipart_literal`
zijn definitie: meer dan een GML-literaal op de knoop, *of* een literaal die er zelf meer
dan een deel in draagt (een `gml:MultiCurve`, of twee `gml:posList`-en naast elkaar). Van
zo'n literaal leest de shapely-lezer alleen het eerste deel, dus knippen zou een
tekstplakje uit dat eerste deel snijden en de rest ongemoeid in beide delen laten staan.
Niet geknipt wordt verder een lijn met een andere verhouding dan 2 of 3 getallen per punt
(`geometry.tokens_per_punt`, dat telt en de `srsDimension` met opzet niet leest), en een
lijn waarvan de coordinatentekst niet al genormaliseerd is -- dubbele spaties, newlines of
randspaties in de posList. De stukken zijn tekstplakjes en de hereniging zet ze met een
enkele spatie aaneen; van een bron met andere scheiders zouden de getallen wel exact
terugkomen maar de tekst eromheen niet, en dan is `merge(clip(bron))` niet meer
byte-gelijk aan `bron`. Zo'n knoop gaat ongeknipt naar elk vlak dat hij raakt (van een
multi-geometrie: elk vlak dat het gelezen deel raakt); de hereniging blijft daarmee
exact, alleen staat de hele geometrie dan in beide delen.

## Blanke knopen krijgen een vaste naam

pyoxigraph verzint bij elke lezing nieuwe namen voor blanke knopen -- twee lezingen
van hetzelfde bestand leveren andere labels op. De clip leest de bron een keer per
vlak en moet in elk deel dezelfde knoop dezelfde naam geven, anders is er na de
hereniging geen brug meer tussen de delen. Daarom krijgt elke blanke knoop hier een
naam naar zijn plaats in de stroom (`b0`, `b1`, ...); de leesvolgorde van een bestand
ligt vast, dus die naam is bij elke lezing dezelfde. `merge_orox` leest de namen weer
uit de delen terug en gebruikt ze als identiteit -- dat pyoxigraph labels van blanke
knopen bij het schrijven en lezen ongemoeid laat, is een eigenschap waar deze module
op leunt en die `tests/test_clip.py` apart vastlegt.
"""

from __future__ import annotations

from gwsw_orox_helpers.clip.orkest import clip_orox, merge_orox

__all__ = ["clip_orox", "merge_orox"]
