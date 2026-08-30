# Architectuur van gwsw-orox-helpers

De package doet drie dingen met een GWSW-OroX-TTL: hem **lezen** tot een toetsbaar
domeinmodel (`load_dataset`), hem **terugschrijven** (`schrijf_orox`) en hem ruimtelijk
**verdelen en herenigen** (`clip_orox` / `merge_orox`). Die drie zijn in drie fasen
gegroeid en hebben elk een eigen pad door pyoxigraph. Dit document zegt welke lagen er
zijn, wie wat importeert, en waar de kennis woont die meer dan één laag nodig heeft.

## De lagen

Wie wat importeert, binnen de package. `A -> B` betekent "A importeert B"; elke pijl
wijst naar een regel *boven* zich en nooit andersom. Na te lopen met
`grep -rn "^from gwsw_orox_helpers" src/gwsw_orox_helpers/` -- `-r` en geen `*.py`-glob,
want `clip` is een submap en die mist een glob op de wortel. Dit zijn alle randen die er
zijn.

```
errors   voortgang   bronnen   namen   geometry   domein    <- bladeren: geen import
                                                               binnen de package

graaf      -> namen
codering   -> errors
rdfmotor   -> errors
ontologie  -> graaf, namen
klassen    -> graaf, namen, ontologie
inlezen    -> codering, domein, errors, geometry, graaf, klassen, namen, rdfmotor
dataset    -> bronnen, codering, domein, errors, geometry, graaf, inlezen, klassen,
              namen, voortgang
cache      -> codering, dataset, domein, geometry, graaf, inlezen, klassen, namen,
              ontologie, rdfmotor, voortgang

schrijven  -> codering, errors, namen, rdfmotor
clip/      -> errors, geometry, namen, schrijven   (een package; zie hieronder)
__init__   -> clip, schrijven
```

`rdfmotor` ligt naast `codering`: allebei bladeren op `errors` na, en allebei door de
leesweg én de schrijfweg gebruikt. De cliplaag komt er niet langs -- die parseert en
serialiseert niet zelf maar leent `lees_orox` / `schrijf_orox_quads` van `schrijven` --
en `CLIP_MAG_IMPORTEREN` in `tests/test_publieke_api.py` laat `rdfmotor` dus met opzet
niet toe -- die lijst noemt hem bij de bewust geweerde modules. De term-fabrieken die
`clip/` wél rechtstreeks bij pyoxigraph haalt (`NamedNode`, `BlankNode`, `Literal`,
`Quad`, `Triple`) gaan niet door de adapter; zie hieronder.

`clip` is sinds de hersnit geen bestand maar een package met zeven fasen, en dezelfde
regel geldt daarbinnen nog een keer: elke pijl wijst naar een regel boven zich. Dezelfde
tekening staat in de docstring van `gwsw_orox_helpers.clip`, voor wie het package opent
in plaats van dit document; `test_de_clipsubmodules_houden_de_importrichting` toetst
allebei tegen de echte imports, dus stille drift blijft niet stil.

```
clip.termen     <- blad binnen clip/: de knip-naamruimte, de vaste termen, de stuknamen
                   (alleen `namen` van buiten het package)
clip.grenzen    <- blad binnen clip/: de GeoJSON-vlakken en hun bestandsnaam

clip.knip       -> clip.grenzen                          (+ errors, geometry)
clip.plan       -> clip.grenzen, clip.knip, clip.termen  (+ errors, geometry, namen,
                                                            schrijven)
clip.stroom     -> clip.knip, clip.plan, clip.termen     (+ geometry, namen)
clip.merge      -> clip.termen                           (+ errors, geometry, namen,
                                                            schrijven)
clip.orkest     -> clip.grenzen, clip.plan, clip.stroom, clip.merge, clip.termen
                                                         (+ errors, schrijven)
clip.__init__   -> clip.orkest
```

Het `__init__.py` is dun: het draagt het verhaal (de docstring van 135 regels, die de
vier stappen van de toewijzing, de knip en zijn omkering en de vaste namen voor blanke
knopen uitlegt) en her-exporteert `clip_orox` en `merge_orox`. Voor een afnemer verandert
er niets: `from gwsw_orox_helpers.clip import clip_orox, merge_orox` doet wat het deed.

Twee dingen die de tekening makkelijk verkeerd om zet. `domein` is een blad: de
waardeobjecten rekenen alleen met wat ze zelf dragen, dus ze importeren niets uit de
package -- `inlezen` is degene die ze *vult* en dus naar `domein` wijst, samen met de zes
andere modules die hij nodig heeft. En de cliplaag hangt aan de schrijflaag en niet
andersom: `clip` leest en schrijft met `schrijven.lees_orox` / `schrijf_orox_quads`, en
`schrijven` weet van `clip` niets. Dat `cache` zoveel randen heeft, is geen verstrengeling
maar de cachesleutel: hij hasht de broncode van elke leeslaagmodule (zie hieronder).

Elke module beantwoordt één vraag; in deze volgorde heeft niets ooit iets van later nodig:

| Module | Vraag die hij beantwoordt |
|---|---|
| `errors` | Welke uitzondering krijgt de afnemer? (`OroxError`, `DatasetError`) |
| `voortgang` | Hoe meldt een lange stap zich? (protocol; `NUL_VOORTGANG` doet niets) |
| `bronnen` | Waar liggen de meegeleverde ontologie en vocabulaire-index? |
| `namen` | Hoe spellen we een IRI? (alleen tekst, geen imports) |
| `geometry` | Wat staat er in een GML-literaal? (shapely; z apart van xy of allebei in een gang; en de coordinatentekst zelf, voor wie hem letterlijk moet terugleggen) |
| `graaf` | Hoe vraag je een graaf iets? (`GraafIndex`: twee dicts, rdflib-termen) |
| `codering` | Hoe worden de bytes van een TTL tekst? (UTF-8 met terugval) |
| `rdfmotor` | Hoe roepen we pyoxigraph aan? (`ontleed_turtle`, `serialiseer_turtle`, plus de poort op de ondersteunde versiereeks) |
| `ontologie` | Wat zegt een `owl:Restriction` over een klasse of kenmerk? (op allebei de graafvormen; zie hieronder) |
| `klassen` | Wat volgt daaruit? (subklasse-afsluiting, `kenmerk_property`, functies) |
| `domein` | Wat *is* een knoop of streng? (waardeobjecten, zonder graaf) |
| `inlezen` | Hoe vul je die objecten uit een graaf? (parsen, hasPart/hasAspect, lezers) |
| `dataset` | Wat kun je een ingelezen dataset vragen? (`GwswDataset`, `load_dataset`) |
| `cache` | Hoe sla je die lezing over? (pickle, sleutel op inhoud én broncode) |
| `schrijven` | Hoe komt een quadstroom er als OroX-Turtle weer uit? |
| `clip` | Hoe verdeel je die stroom over vlakken, en hoe draai je dat terug? (package) |

## De ontologielezers nemen allebei de graafvormen

`ontologie` is de enige module die met twee soorten grafen te maken heeft, en dat is geen
losse eindje maar de vorm van de leesweg. `load_dataset` parseert de ontologiebestanden in
een `GraafIndex` en geeft die als `restrictiebron` door aan `klassen`, dat er
`verwachte_property` en `functie_van_klasse` mee aanroept. Een rdflib-`Graph` komt er in de
package nergens meer uit een parse — die vorm bestaat alleen nog in tests en bij een
afnemer die zelf iets geparst heeft.

Tot issue #19 hing daar een scheur in: `facetbereik`, `datatype_van_kenmerk` en
`kenmerkbereik` — de "ontbrekende schakel" die de gedeclareerde waardebereiken uit de
ontologie haalt — liepen via `rdflib.collection.Collection` over de
`owl:withRestrictions`-lijst, en `Collection` itereert via `Graph.items` en eist dus een
echte `Graph`. Die drie functies draaiden daardoor **alleen in tests**; op de leesweg
liepen ze op een `AttributeError` stuk. `ontologie.lijstitems` wandelt de
`rdf:first`/`rdf:rest`-ketting nu zelf, met niets anders dan de `value` die allebei de
vormen aanbieden, en alle vijf de lezers nemen `Graph | GraafIndex`.

Dat is meteen de reden dat `GraafIndex` geen collectie-bewerking aanbiedt: een RDF-lijst
is met `value` te wandelen, dus het leescontract in de docstring van `graaf` blijft de
handvol bewerkingen die het was. En het is de naad waar issue #21 een
`GraafLezer`-protocol overheen kan leggen: de vijf lezers gebruiken precies dezelfde
bewerkingen, dus dat protocol vervangt straks alleen de naam van het type in de
handtekening.

## Twee paden door pyoxigraph, en dat blijft zo

Er zijn twee wegen van een TTL-bestand naar triples, en ze zijn met opzet verschillend:

- **De leesweg** (`inlezen._parse`) decodeert het bestand, parseert het en giet de quads
  in een `GraafIndex` met rdflib-termen. Wie leest, moet daarna kunnen opzoeken; die
  index kost tijd en geheugen en is precies wat de checks nodig hebben. Over die hele
  lezing -- ook over de klassenafleiding en de objectopbouw ná het vullen van de index --
  ligt de cyclische GC van het proces stil (`inlezen._gc_uit`, aangeroepen vanuit
  `dataset.load_dataset`, dat het neveneffect in zijn docstring toezegt en de oude stand
  in een `finally` herstelt).
- **De schrijfweg** (`schrijven.lees_orox` → `schrijf_orox_quads`) laat de quads van de
  parser rechtstreeks naar de serializer stromen. Wie terugschrijft heeft geen index
  nodig en zou hem op een export van honderden megabytes ook niet willen betalen; de
  cliplaag hangt in diezelfde stroom en filtert hem per vlak.

Ze samenvoegen zou de ene helft opzadelen met wat de andere nodig heeft: de leesweg is
gretig (de index is er pas als alles gelezen is), de schrijfweg is lui (een syntaxfout op
regel 900.000 komt pas boven als de serializer daar is). Wat ze wél delen is de kennis
die anders uit elkaar loopt, en die staat één keer:

| Gedeelde kennis | Woont in | Gelezen door |
|---|---|---|
| De aanroep van de motor zelf: `pyoxigraph.parse` en `pyoxigraph.serialize` op Turtle, plus de reeks pyoxigraph-versies waarop de package getoetst is | `rdfmotor` | `inlezen._parse` (bytes), `schrijven.lees_orox` (een pad, of tekst bij een terugvalcodering) en `schrijven.schrijf_orox_quads` (de serializer) |
| De IRI's: `GWSW` en de naamruimten, `hasAspect`/`hasPart`/`hasConnection`, `geo:gmlLiteral` | `namen` (tekst) | `inlezen` (als `URIRef`), `clip.termen` (als `NamedNode`), `clip.plan`/`clip.stroom`/`clip.merge` (als tekst), `schrijven` (prefixkop), `graaf` (`xsd:string`), `ontologie`, `klassen` (`GWSW`, voor de korte namen), `dataset` (`GWSW`, en het exporteert hem) |
| De prefixkop van een OroX-export | `schrijven.STANDAARD_PREFIXEN`, opgebouwd uit `namen` | `schrijven`, `clip.orkest` (krijgt ze via `lees_orox` en vult `knip:` aan) |
| UTF-8 met terugvalcodering, inclusief beide foutmeldingen | `codering.decodeer` | `inlezen._decode`, `schrijven._gedecodeerd` |
| Het verslag van zo'n terugval (`DecodeFallback`) | `codering.terugvalverslag` | alleen `inlezen` |
| De GML-lezers | `geometry` | `inlezen` (`parse_gml_met_z`), `clip.knip`, `clip.plan`, `clip.merge` (`parse_gml` / `parse_gml_z`), `dataset` (doorgeefluik) |
| De tekstkant van diezelfde literaal: de coordinatenlijst als tokens, het terugleggen ervan in het omhulsel, en hoeveel getallen er op een punt gaan (`coordinaattokens`, `vervang_coordinaten`, `tokens_per_punt`) | `geometry` | `clip.knip` (de knip), `clip.stroom` (het stuk wegschrijven), `clip.merge` (de omkering) |
| De `knip:`-naamruimte en de stuknamen (`<origineel>__knip<k>`) | `clip.termen` | `clip.plan`, `clip.stroom`, `clip.merge`, `clip.orkest` |

Dat laatste onderscheid is opzettelijk: het verslag telt de afwijkende bytes en zoekt de
regels waarin ze staan, en dat is een tweede gang over het hele bestand. Een lezing wordt
gerapporteerd (`GwswDataset.decode_fallback`), een terugschrijving niet — dus betaalt de
schrijfweg er ook niet voor.

**De motor heeft één naad, de paden blijven twee.** De eerste rij van die tabel is de
jongste: `pyoxigraph.parse` en `pyoxigraph.serialize` stonden op vier plekken
uitgeschreven en staan nu één keer, in `rdfmotor`. Dat verandert aan de twee paden
niets — de leesweg vult nog steeds een index, de schrijfweg stroomt nog steeds door —
maar het maakt een minor-bump van de motor een een-naadswijziging in plaats van een
zoektocht. pyoxigraph is pre-1.0 (0.3 → 0.4 brak de parse-signatuur al eens), en zo'n
breuk meldt zich anders als een `TypeError` op de plek waar de eerste quad opgehaald
wordt in plaats van waar de aanroep staat. Dezelfde module draagt daarom de poort op de
ondersteunde versiereeks: die staat **naast** de cap in `pyproject.toml`
(`pyoxigraph>=0.5,<0.6`) en niet in plaats daarvan — de cap voorkomt de installatie, de
poort vangt een omzeilde cap (`pip install --no-deps`, een conda-omgeving, een
handmatige upgrade) met een leesbare `DatasetError`. De poort valt **bij het importeren
van `rdfmotor`, één keer**: dat kost niets in de hete lus, en aan de aanroepkant zou de
fout in de `except Exception` van `inlezen._parse` belanden en er als "geen geldige
Turtle" uitkomen. Beide plekken worden aan elkaar geknoopt door
`test_de_reeks_is_dezelfde_als_de_cap_in_pyproject`.

Wat er **niet** doorheen gaat, is even bewust: de term-fabrieken (`NamedNode`,
`BlankNode`, `Literal`, `Quad`, `Triple`). Die staan op tientallen plekken in `clip/` en
in `graaf`, ze zijn sinds 0.3 ongewijzigd, en een wrapper eromheen zou een laag zijn
zonder werk. Wie ze nodig heeft importeert pyoxigraph rechtstreeks; dat is de grens van
de adapter en geen omissie.

Dat de naad er één blijft, staat niet alleen hier: `test_alleen_rdfmotor_roept_de_motor_aan`
loopt de AST van elke module in de package af en laat `pyoxigraph.parse` of
`pyoxigraph.serialize` buiten `rdfmotor` niet toe. Zonder die sweep was "één naad" een
belofte in een docstring en belette niets een vijfde aanroep. De adapter heeft daarom
**twee** ontleedingangen en geen typeswitch: `ontleed_turtle_bestand(pad)` geeft altijd
`path=` door (de motor opent het bestand zelf en leest het streamend),
`ontleed_turtle(bytes | str)` geeft altijd de inhoud door. Op één parameter samengevoegd
zou een `str`-pad in de inhoudstak vallen en zou de *padtekst* als Turtle ontleed worden.

**Drie GML-lezers, omdat de twee lagen niet dezelfde vraag stellen.** `parse_gml` (de
meetkunde in het platte vlak) en `parse_gml_z` (de z-waarde per punt) zijn de losse
vragen; de knip stelt er per literaal precies één van en ze staan gepind in
`tests/test_publieke_api.py`. De leeslaag stelt ze allebei over elke geometrie in de
export, en dat kostte de regex en de float-conversie twee tot vijf keer over dezelfde
tekst (twee op de vorm die een GWSW-export schrijft, vijf op een `gml:pos` zonder
`srsDimension`). `parse_gml_met_z` beantwoordt ze in één gang en is wat `inlezen._geometry`
aanroept. De drie delen hun private stappen (`_kind`, `_values`, `_dimensie_van`,
`_tupels`, `_bouw`), zodat de dimensieregel en de shapely-tak — inclusief de
`ShapelyError`-vangst — maar één keer bestaan; een tweede exemplaar daarvan zou pas
opvallen als de leeslaag en de knip dezelfde literaal verschillend gaan lezen. Wat de
uitkomst betreft is de eenpaslezer per contract `(parse_gml(l), parse_gml_z(l))`, tot en
met de foutmelding, en `test_parse_gml_met_z_is_gelijkwaardig_aan_de_twee_losse_lezers`
toetst dat op de geslaagde én de mislukte literalen.

## Wat "additief" hier betekent

`schrijven` en `clip` staan naast de leeslaag en niet erop: ze bouwen geen domeinmodel en
importeren `dataset` noch `graaf`. `tests/test_publieke_api.py` bewaakt dat aan de
brontekst (`test_schrijflaag_is_additief`, `test_cliplaag_is_additief`). Sinds `clip` een
package is, geldt die vraag daar niet aan het oppervlak maar per fase: `test_cliplaag_is_additief`
loopt over elke submodule, `test_de_clipsnit_ligt_vast` legt vast welke fasen er zijn en dat
het `__init__.py` dun blijft, en `test_de_clipsubmodules_houden_de_importrichting` toetst
allebei de randen -- alleen `errors`/`geometry`/`namen`/`schrijven` uit de package, en een
zuster alleen als die *boven* de fase ligt. Zonder dat laatste kan een enkele import stil
een lus sluiten en is de hersnit weer een bak. Die laatste test leest de **import-AST** en
niet de regels van het bestand: een ingesprongen import in een functie,
`from gwsw_orox_helpers import dataset` en `import gwsw_orox_helpers.graaf` glippen alle
drie langs een `^from ...`-patroon. Ze delen wel de
bladeren onder de leeslaag: `namen` en `errors` allebei, `codering` en `rdfmotor` alleen
`schrijven` (de UTF-8-terugval en de aanroep van de motor; `clip` ziet allebei enkel via
`lees_orox` en `schrijf_orox_quads`) en `geometry` alleen `clip` (de GML-lezers, die de
knip nodig heeft en de serializer niet). Modules die onder allebei
liggen en van geen van beide iets weten. Dat is geen gat in het eigen pad maar de reden
dat het er een blijft: een tweede exemplaar van de `gwsw:`-IRI of van de UTF-8-terugval
valt pas op als de twee lagen dezelfde bron verschillend lezen, en dan is het te laat.

## `dataset` is het gezicht, niet de bak

De leeslaag is intern in vier modules verdeeld (`domein`, `inlezen`, `klassen`,
`codering`), maar **het oppervlak ligt in `dataset`**: elke naam die nlriochecker uit
`gwsw_orox_helpers.dataset` importeert komt daar naar buiten, met dezelfde handtekening
en hetzelfde gedrag. Dat is een Harde regel uit `CLAUDE.md` en `tests/test_publieke_api.py`
is de scheidsrechter. Praktisch:

- de waardeobjecten (`Node`, `Conduit`, `Aspect`, `Inwinning`, `Vulwaarde`,
  `Koppelingsherstel`, `DecodeFallback`) staan in `domein`/`codering` en worden door
  `dataset` geëxporteerd;
- de graafhulpen die de checks rechtstreeks aanroepen (`parts_of`, `part_holders_of`,
  `aspects_of`, `aspect_holders_of`) staan in `inlezen` en idem;
- de IRI-constanten komen uit twee plekken: `GWSW` en de `HAS_*`-namen staan als tekst in
  `namen` en worden in `inlezen` `URIRef`; de `KLASSE_*`- en `KLASSEN_*`-constanten
  bestaan alleen in `inlezen` (samengesteld uit `namen.GWSW`) en staan niet in `namen`.
  Allebei komen ze via `dataset` naar buiten.
- en wat er bij de hersnit naar een blad verhuisde, blijft óók uit `dataset` te
  importeren: de GML-lezers (`parse_gml`, `parse_gml_z`, `is_multipart_literal`,
  `GeometryError`) uit `geometry` en de datumpatronen (`ISO_DATUM`, `JAARTAL`) uit
  `domein`. Ze zijn er niets meer dan een doorgeefluik. De vraag "importeert een afnemer
  dit?" is niet met zekerheid te beantwoorden en het antwoord is dus de veilige kant:
  laten staan kost een regel, weghalen breekt stil.

`dataset.__all__` is die lijst. Een naam met een underscore is intern aan de leeslaag en
geen belofte aan de afnemer — ook waar hij een modulegrens oversteekt, zoals
`inlezen._read_aspects` dat `GwswDataset.onderdeel_aspecten` gebruikt.

## De cache leest mee met de lader

`cache.cachesleutel` hasht niet alleen de invoerbestanden en de bibliotheekversies maar
ook **de broncode van de hele leeslaag**: `cache.LADERMODULES` -- `dataset`, `inlezen`,
`domein`, `klassen`, `codering`, `namen`, `graaf`, `geometry`, `ontologie` en `rdfmotor`.
Dat is de garantie dat een cache nooit achterloopt op een wijziging in de lezing.
`rdfmotor` staat erbij ook al deelt de schrijfweg hem: `inlezen._parse` haalt zijn quads
daarlangs, dus een andere aanroep van de motor is een andere lezing. Wie de leeslaag
opnieuw indeelt, moet de nieuwe modules aan die lijst toevoegen: een vergeten module
levert geen fout op maar een cache die na een wijziging de oude lezing blijft teruggeven.
Twee tests in `tests/test_cache.py` houden dat bij: de ene parametriseert over
`LADERMODULES` en toont per module dat een gewijzigde broncode een andere sleutel geeft,
de andere eist dat elke module van de package óf in die lijst staat óf met een reden in
de uitzonderingsverzameling ernaast. Die tweede telt met `rglob` en ziet dus ook de fasen
in `clip/`; ze staan er alle acht met naam bij, want een nieuwe fase hoort zich net zo
goed te melden als een nieuwe module in de wortel.

Verplaatste code verandert die sleutel, dus na een hersnit worden bestaande caches één
keer opnieuw opgebouwd. Dat is de bedoelde werking en geen gedragswijziging.

## Waar de terugval op geometrie zit

Eén domeinregel loopt door meerdere lagen en is daarom het makkelijkst stuk te maken:
**zonder klassenkennis blijft een subklasse-afsluiting op de wortel zelf steken en valt
de lezing terug op geometrie.** Die terugval staat op één plek (`klassen._afsluiting`) en
wordt op precies één manier zichtbaar gemaakt (`klassen._bruikbare_afsluiting`, dat `None`
geeft waar de afsluiting singleton bleef). `load_dataset` stelt die vraag bij het lezen,
`GwswDataset.klassenhierarchie_bekend` stelt hem daarna nog eens voor de rapportage, en
`inlezen._structural_diff` telt wat het verschil in de praktijk was. Alle drie via
dezelfde functies — een tweede exemplaar zou stilzwijgend een lege selectie opleveren in
plaats van een fout.
