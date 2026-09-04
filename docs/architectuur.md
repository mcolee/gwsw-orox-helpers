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
bestand    -> codering, errors, graaf, rdfmotor
inlezen    -> domein, geometry, graaf, klassen, namen
netwerk    -> domein
dataset    -> bestand, bronnen, codering, domein, errors, geometry, graaf, inlezen,
              klassen, namen, netwerk, voortgang
cache      -> bestand, codering, dataset, domein, geometry, graaf, inlezen, klassen,
              namen, netwerk, ontologie, rdfmotor, voortgang

schrijven  -> codering, errors, namen, rdfmotor
clip/      -> errors, geometry, namen, schrijven   (een package; zie hieronder)
__init__   -> clip, schrijven
```

`bestand` en `inlezen` zijn sinds issue #26 twee rijen en niet één. Ze deelden alleen de
`GraafIndex`: `bestand` máákt er een (de bytes van schijf, de codering, de parser en de
procesbrede GC eromheen), `inlezen` bevráágt hem (hasPart/hasAspect, de kenmerklezers,
`_read_nodes` en `_read_conduits`). Let op wat die twee rijen wél en niet zeggen:
`bestand` staat *onder* `inlezen` omdat hij alleen op de bladeren leunt, maar er loopt
géén rand tússen de twee -- `inlezen` importeert `bestand` niet en her-exporteert hem ook
niet; `dataset` haalt `_parse` en `_gc_uit` rechtstreeks bij `bestand`. De volgorde is
hier dus een rangschikking en geen afhankelijkheid. Dat is wat het testen van de lezers
van echte bestanden losmaakt, en `test_de_bestandssnit_ligt_vast` in
`tests/test_publieke_api.py` legt de vier namen, de toegestane imports en die ontbrekende
rand vast.

`netwerk` is sinds issue #27 een eigen rij, en het is de dunste in de tekening: hij leunt
alleen op `domein` (en op shapely). Wat erin staat is de wandeling langs hasPart omhoog
(`klim_naar_knoop`, `resolve_network_node`) en de tekenrichting van een streng
(`richting_van_geometrie`) — als **vrije functies** die hun context als parameter nemen:
de knopen (`nodes`), het typepredicaat (`is_a`) en waar er gememoiseerd wordt de memo
zelf. Ze stonden als methoden op `GwswDataset` en waren daardoor alleen via een volledig
ingelezen dataset te toetsen; nu is een handgebouwd woordenboek genoeg
(`tests/test_netwerk.py`). De drie publieke methoden bestaan nog en zijn wat ze moeten
zijn: doorgeefluiken met dezelfde handtekening en hetzelfde gedrag, memo inbegrepen —
`GwswDataset._resolved_nodes` blijft op de dataclass staan (zie "de memo hoort bij de
dataset" hieronder) en gaat als argument mee.
`test_de_netwerksnit_ligt_vast` in `tests/test_publieke_api.py` legt de vier functies, de
enkele toegestane import en de dunheid van de doorgeefluiken vast — die laatste op de AST,
want een teruggekopieerde wandeling laat elke gedragstest groen.

**`namen` spelt sinds issue #29 twee kanten op.** `_uri` (korte klassenaam → GWSW-IRI) en
`_short` (het omgekeerde) stonden in `klassen` en zijn twee `rsplit`-en op een string:
geen klassenkennis, geen graaf, geen rdflib. Ze horen bij de IRI's die ze uit elkaar
halen. Aan de tekening hierboven verandert dat **niets** -- geen enkele rand valt weg,
want `inlezen` houdt `klassen` nodig voor `_afsluiting` en `dataset` voor tien andere
namen. Wat het oplevert is dat een module die alléén wil spellen de klassenlaag niet meer
hoeft binnen te halen. `test_de_namensnit_ligt_vast` in `tests/test_publieke_api.py` legt
dat vast: `namen` zonder pakketimport, de twee helpers erin, geen tweede module die ze
definieert (een teruggekopieerde `rsplit` geeft overal hetzelfde antwoord en zou dus door
geen gedragstest opvallen) en geen gebruiker binnen de package die ze nog via `klassen`
haalt.

**Sinds issue #32 draagt `namen` óók de termenset per versie, naast de gepinde
1.6-constanten.** De module-constanten (`GWSW`, `HAS_*`) blijven letterlijk 1.6 -- dat is het
bevroren contract dat nlriochecker importeert -- maar erbij staat een `Termen`-dataclass met
de zeven properties per basis (`termen_voor(basis)`, `TERMEN_16` als default) en de detectie
zelf: `basis_uit_prefixen` leest de `gwsw:`-prefix, `basis_uit_iri` de basis uit een losse
IRI (de terugval voor een export zonder prefixdeclaratie), en `versie_van_basis` /
`basis_voor_versie` rekenen tussen versienummer en basis-IRI. `_uri` kreeg een
`basis`-parameter (default 1.6). Alles blijft tekst -- de lezers maken er hun eigen
munteenheid van: `inlezen` een `URIRef`-termenset per basis (`_leestermen`, gecachet),
`clip` een `_Kniptermen` met pyoxigraph-`NamedNode`-en. **Waar de gedetecteerde basis woont:**
op `GraafIndex.gwsw_basis`, gezet door `bestand._parse` na het vullen; de leeslaag leest hem
daar, en `GwswDataset` leidt hem voor `closure`/`is_connection_class` af uit de typen van zijn
objecten (een `init=False`-memo, zodat het gepinde cachepad de graafpickle niet hoeft te laden).
De **publieke leesweg** daarnaartoe is sinds issue #39 de gememoiseerde property
`GwswDataset.gwsw_versie -> GwswVersie` (`basis`, `versie`, `gedetecteerd`): dezelfde afleiding
uit de typen van de knopen en strengen -- geen `self.graph.gwsw_basis`, dus geen pickle-lading op
het cachepad -- met `gedetecteerd=False` wanneer geen enkele knoop of streng een GWSW-type draagt.
`_basis` blijft de interne leesweg en levert `gwsw_versie.basis`; `namen.versie_uit_basis` haalt
het versiecijfer uit de basis.

**Sinds issue #51 is diezelfde versie-juiste termenset ook publiek leesbaar naast de
1.6-constanten.** De `URIRef`-termenset per basis (`inlezen.Leestermen`, was `_Leestermen`) is nu
publiek, en `GwswDataset.termen` levert hem voor de gedetecteerde basis -- gememoiseerd langs
hetzelfde luie `init=False`-patroon als `gwsw_versie`, zodat het cachepad de graafpickle niet
laadt. Daarop staan drie str-methoden (`uris_of_class`, `buren`, `kenmerken_met_waarde`) die de
graaf versie-juist bevragen en tekst teruggeven, plus `namen.klasse_iri(naam, basis)` als
publieke tegenhanger van `_uri`. Zo hoeft een afnemer die op 1.7 leest niet meer met de gepinde
1.6-`HAS_*`/`KLASSE_*`-constanten te bevragen -- die spellen 1.6 en treffen op een 1.7-graaf stil
nul. `load_dataset` waarschuwt daarom één keer (en niet nog eens op het cachepad, dat niet langs
`load_dataset` loopt) wanneer `gwsw_versie.versie` niet 1.6 is. Dit is *additief*: de constanten,
signaturen en retourvormen die nlriochecker importeert blijven byte-voor-byte gelijk.

`rdfmotor` ligt naast `codering`: allebei bladeren op `errors` na, en allebei door de
leesweg én de schrijfweg gebruikt. De cliplaag komt er niet langs -- die parseert en
serialiseert niet zelf maar leent `lees_orox` / `schrijf_orox_quads` van `schrijven` --
en `CLIP_MAG_IMPORTEREN` in `tests/test_publieke_api.py` laat `rdfmotor` dus met opzet
niet toe -- die lijst noemt hem bij de bewust geweerde modules. De term-fabrieken die
`clip/` wél rechtstreeks bij pyoxigraph haalt (`NamedNode`, `BlankNode`, `Literal`,
`Quad`, `Triple`) gaan niet door de adapter; zie hieronder.

`clip` is sinds de hersnit geen bestand maar een package met acht fasen, en dezelfde
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
clip.bereik     -> clip.grenzen, clip.termen             (+ geometry, namen, schrijven)
clip.orkest     -> clip.grenzen, clip.plan, clip.stroom, clip.merge, clip.bereik,
                   clip.termen                           (+ errors, schrijven)
clip.__init__   -> clip.orkest
```

`clip.bereik` staat achteraan in die rij en niet in het midden: hij is geen stap van de knip
maar de **opt-in bereikcontrole** ernaast (issue #28), en alleen `orkest` roept hem aan. Hij
legt de omhullende van de grenslaag naast die van de bron en schrijft een
`logging`-waarschuwing als de twee niet bij elkaar kunnen horen -- de grenslaag in
WGS84-graden tegen een bron in RD-meters is de gewone vergissing, en de terugval op het
dichtstbijzijnde vlak (`clip.knip._vlak_van`) schuift dan stilzwijgend elk object naar
hetzelfde deel. `clip_orox` doet dat alleen op verzoek (`bereikcontrole=True`, default
`False`) en de geschreven delen zijn met of zonder de controle byte voor byte dezelfde: het
is een waarnemer en geen validatie. Waarom een waarschuwing en geen fout, staat in de
docstring van de module -- kort: de terugval is een belofte en geen vergissing, dus een
bereik dat niet past is een sterk vermoeden, en weigeren wat vandaag geknipt wordt zou het
gedrag van de bevroren `clip_orox` veranderen.

Het `__init__.py` is dun: het draagt het verhaal (de docstring van 178 regels, die de
vier stappen van de toewijzing, de terugval op het dichtstbijzijnde vlak, de knip en zijn
omkering en de vaste namen voor blanke knopen uitlegt) en her-exporteert `clip_orox` en
`merge_orox`. Voor een afnemer verandert
er niets: `from gwsw_orox_helpers.clip import clip_orox, merge_orox` doet wat het deed.

Twee dingen die de tekening makkelijk verkeerd om zet. `domein` is een blad: de
waardeobjecten rekenen alleen met wat ze zelf dragen, dus ze importeren niets uit de
package -- `inlezen` is degene die ze *vult* en dus naar `domein` wijst, samen met de vier
andere modules die hij nodig heeft. En de cliplaag hangt aan de schrijflaag en niet
andersom: `clip` leest en schrijft met `schrijven.lees_orox` / `schrijf_orox_quads`, en
`schrijven` weet van `clip` niets. Dat `cache` zoveel randen heeft, is geen verstrengeling
maar de cachesleutel: hij hasht de broncode van elke leeslaagmodule (zie hieronder).

Elke module beantwoordt één vraag; in deze volgorde heeft niets ooit iets van later nodig:

| Module | Vraag die hij beantwoordt |
|---|---|
| `errors` | Welke uitzondering krijgt de afnemer? (`OroxError`, `DatasetError`, en daaronder de zeven faalfamilies van issue #31: `BestandError`, `CoderingError`, `TurtleError`, `InhoudError`, `GrenslaagError`, `KnipError`, `MotorError` — ingedeeld naar de oorzaak, niet naar de invoer, dus een `OSError` op de grenslaag is een `BestandError`) |
| `voortgang` | Hoe meldt een lange stap zich? (protocol; `NUL_VOORTGANG` doet niets) |
| `bronnen` | Waar liggen de meegeleverde ontologie en vocabulaire-index? |
| `namen` | Hoe spellen we een IRI? (de naamruimten en de properties als tekst, plus `_uri`/`_short` die een korte klassenaam uitschrijven en weer teruglezen; alleen tekst, geen imports) |
| `geometry` | Wat staat er in een GML-literaal? (shapely; z apart van xy of allebei in een gang; en de coordinatentekst zelf, voor wie hem letterlijk moet terugleggen) |
| `graaf` | Hoe vraag je een graaf iets? (`GraafIndex`: twee dicts, rdflib-termen) |
| `codering` | Hoe worden de bytes van een TTL tekst? (UTF-8 met terugval) |
| `rdfmotor` | Hoe roepen we pyoxigraph aan? (`ontleed_turtle`, `serialiseer_turtle`, plus de poort op de ondersteunde versiereeks) |
| `ontologie` | Wat zegt een `owl:Restriction` over een klasse of kenmerk? (op allebei de graafvormen; zie hieronder) |
| `klassen` | Wat volgt daaruit? (subklasse-afsluiting, `kenmerk_property`, functies) |
| `domein` | Wat *is* een knoop of streng? (waardeobjecten, zonder graaf) |
| `bestand` | Hoe wordt een TTL-bestand een gevulde `GraafIndex`? (bytes, codering, parse, GC) |
| `inlezen` | Hoe vul je die objecten uit een gevulde graaf? (hasPart/hasAspect, lezers) |
| `netwerk` | Welke knoop hangt boven dit object, en loopt de lijn de goede kant op? (vrije functies op `nodes` + `is_a`) |
| `dataset` | Wat kun je een ingelezen dataset vragen? (`GwswDataset`, `load_dataset`, `lees_ontologie`) |
| `cache` | Hoe sla je die lezing over? (pickle, sleutel op inhoud én broncode) |
| `schrijven` | Hoe komt een quadstroom er als OroX-Turtle weer uit? |
| `clip` | Hoe verdeel je die stroom over vlakken, en hoe draai je dat terug? (package) |

## De ontologielezers nemen een `GraafLezer`

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
liepen ze op een `AttributeError` stuk. `ontologie._lijstleden` wandelt de
`rdf:first`/`rdf:rest`-ketting nu zelf, met niets anders dan de `value` die allebei de
vormen aanbieden.

Dat is meteen de reden dat `GraafIndex` geen collectie-bewerking aanbiedt: een RDF-lijst
is met `value` te wandelen, dus het leescontract in de docstring van `graaf` blijft de
handvol bewerkingen die het was.

Sinds issue #21 staat die vrijheid niet meer als union `Graph | GraafIndex` in zes
handtekeningen maar als één protocol: **`graaf.GraafLezer`**, een `typing.Protocol` met
precies twee leden -- `objects(subject, predicate, /)` en `value(subject, predicate, /)`.
`GraafIndex` en `rdflib.Graph` vervullen het allebei *structureel*: geen van beide erft
ervan, geen van beide weet ervan. Sinds issue #34 doet `cache.LuieGraaf` dat ook, en om
diezelfde reden expliciet: zie "De cache leest mee met de lader" hieronder. Voor de
aanroeper is dat verbreding en geen breuk --
elke `Graph` en elke `GraafIndex` die paste, past nog -- en aan de kant van `ontologie`
verschuift er iets wezenlijks: de laaggrens is mypy-bewaakt geworden. Een lezer die daar
een derde bewerking gaat gebruiken, loopt op een `attr-defined` vast tot het protocol
verbreed is, in plaats van stil een van de twee graafvormen onaanroepbaar te maken. Dat
laatste is precies wat er tussen issue #35 en #19 gebeurde.

Drie keuzes eromheen zijn de moeite waard, want ze zijn tegen de intuïtie in:

- **Twee leden en niet zeven.** Het protocol is *niet* de getypte vorm van het hele
  leescontract in de `graaf`-docstring. Dat kan ook niet: `heeft_subject` is een eigen
  aanvulling die `rdflib.Graph` niet kent, dus een protocol over het hele contract sluit
  de `Graph`-kant per direct uit. En het hoeft niet: elk lid erbij is een eis aan wie het
  protocol wil vervullen, geen dienst aan wie het aanroept. `subjects`,
  `subject_objects`, `__contains__` en `__len__` roept `ontologie` niet aan en staan er
  dus niet in. `test_het_protocol_is_precies_zo_breed_als_ontologie_het_gebruikt` leest de
  AST van `ontologie.py` en houdt beide kanten gelijk.
- **Positionele parameters** (de `/`). `rdflib.Graph.objects` draagt een derde parameter
  (`unique`) en `Graph.value` is vijfvoudig overladen (`object`, `default`, `any`); extra
  parameters mét default breken de structurele vervulling niet, maar een afwijkende
  parameter*naam* zou dat wel doen zodra rdflib er een hernoemt. Positioneel is de vorm
  die dat overleeft.
- **Het bewijs staat in de poort.** Structurele vervulling is een typebegrip en met een
  `assert` niet te toetsen, dus `pyproject.toml` zet `tests/typecheck` in
  `[tool.mypy] files`: `tests/typecheck/graaflezer.py` geeft een `Graph`, een `GraafIndex`
  én een `LuieGraaf` aan een `GraafLezer`-parameter (positief) en biedt twee objecten aan
  die het protocol *niet* vervullen, met `# type: ignore[arg-type]` erop (negatief). Omdat
  `warn_unused_ignores = true` aanstaat, valt mypy ook om als die negatieve gevallen ooit
  geaccepteerd worden -- bijvoorbeeld doordat rdflib zijn typen kwijtraakt en `Graph`
  `Any` wordt. Een protocol dat alles accepteert ziet er anders groen uit.

Wat er **niet** mee verschoven is, en bewust niet: de gepinde
`dataset.parts_of`/`part_holders_of`/`aspects_of`/`aspect_holders_of` en het veld
`GwswDataset.graph` staan nog op het concrete `GraafIndex`, en de `cast(GraafIndex, ...)`
op `LuieGraaf` in `cache` staat er ook nog. Die handtekeningen liggen vast in
`tests/test_publieke_api.py` en zijn een auteursbeslissing (`CLAUDE.md`, Harde regels).

Eén stap is er bewust *niet* gezet, en één stap wél -- maar niet dezelfde. `load_dataset`
bouwt de ontologie-`GraafIndex` als lokale `restrictiebron` (`dataset.py`, in
`load_dataset`) en bewaart hem niet: `GwswDataset` draagt alleen de kleine afgeleide
woordenboeken (`subclasses`, `kenmerk_property`, `functie_per_klasse`) en zijn `graph` is
de *dataset*graaf, niet de ontologie. Dát dichten -- een ontologieveld op `GwswDataset` --
vraagt een wijziging aan een handtekening die in `tests/test_publieke_api.py` gepind
staat, en dat blijft een auteursbeslissing volgens de Harde regels in `CLAUDE.md`, niet
iets wat een agent er zelf bij doet.

Wat er sinds issue #33 wél is, is de andere helft van datzelfde probleem: de afnemer
hoefde die index niet op de dataset te krijgen, hij moest hem alleen kúnnen bouwen zonder
`bestand._parse` (privé) na te bootsen. `dataset.lees_ontologie()` is die weg; zie
[`lees_ontologie` naast `load_dataset`](#lees_ontologie-naast-load_dataset) hieronder.

## Twee paden door pyoxigraph, en dat blijft zo

Er zijn twee wegen van een TTL-bestand naar triples, en ze zijn met opzet verschillend:

- **De leesweg** (`bestand._parse`) decodeert het bestand, parseert het en giet de quads
  in een `GraafIndex` met rdflib-termen. Wie leest, moet daarna kunnen opzoeken; die
  index kost tijd en geheugen en is precies wat de checks nodig hebben. Over die hele
  lezing -- ook over de klassenafleiding en de objectopbouw ná het vullen van de index --
  ligt de cyclische GC van het proces stil (`bestand._gc_uit`, aangeroepen vanuit
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
| De motor-naad: `pyoxigraph.parse` en `pyoxigraph.serialize` op Turtle, sinds issue #50 ook de foutvertaling (`MOTORFOUTEN`, `is_coderingsfout`) en de prefixlezing (`prefixen_van`), plus de reeks pyoxigraph-versies waarop de package getoetst is | `rdfmotor` | `bestand._parse` (bytes; parse, `prefixen_van`, en de smalle vangst op `MOTORFOUTEN`+`TypeError`), `schrijven.lees_orox` (een pad, of tekst bij een terugvalcodering of een UTF-8-BOM; parse, `prefixen_van`), `schrijven._gecontroleerd` (`MOTORFOUTEN`+`is_coderingsfout`) en `schrijven.schrijf_orox_quads` (de serializer) |
| De IRI's: `GWSW` en de naamruimten, `hasAspect`/`hasPart`/`hasConnection`, `geo:gmlLiteral`; sinds issue #32 óók de termenset per gedetecteerde basis (`Termen`, `termen_voor`) en de detectie (`basis_uit_prefixen`, `basis_uit_iri`/`basis_uit_iris`, met de gedeelde terugval-melding `terugvalmelding`) | `namen` (tekst) | `inlezen` (als `URIRef`-termenset per basis), `clip.termen` (als `NamedNode`-termenset), `clip.plan`/`clip.stroom`/`clip.merge`/`clip.bereik` (via die termenset), `schrijven` (prefixkop, 1.6-cosmetisch), `graaf` (`xsd:string` + `gwsw_basis`), `bestand` (detectie), `ontologie`, `dataset` (`GWSW`, en het exporteert hem) |
| Het spellen van een korte klassenaam heen en terug (`_uri`, `_short`) | `namen` | `klassen` (`_afsluiting`, `_kenmerk_properties`, `_klassefuncties`), `inlezen` (de korte naam van een soort, een referentie of een klasse), `dataset` (`beheerobjecttype`, `is_connection_class`) |
| De prefixkop van een OroX-export | `schrijven.STANDAARD_PREFIXEN`, opgebouwd uit `namen` | `schrijven`, `clip.orkest` (krijgt ze via `lees_orox` en vult `knip:` aan) |
| UTF-8 (met of zonder een leidende BOM, via `utf-8-sig`) met terugvalcodering, inclusief beide foutmeldingen | `codering.decodeer` | `bestand._decode`, `schrijven._gedecodeerd` |
| Het verslag van zo'n terugval (`DecodeFallback`) | `codering.terugvalverslag` | alleen `bestand` |
| De GML-lezers | `geometry` | `inlezen` (`parse_gml_met_z`), `clip.knip`, `clip.plan`, `clip.merge`, `clip.bereik` (`parse_gml` / `parse_gml_z`), `dataset` (doorgeefluik) |
| De tekstkant van diezelfde literaal: de coordinatenlijst als tokens, het terugleggen ervan in het omhulsel, en hoeveel getallen er op een punt gaan (`coordinaattokens`, `vervang_coordinaten`, `tokens_per_punt`) | `geometry` | `clip.knip` (de knip), `clip.stroom` (het stuk wegschrijven), `clip.merge` (de omkering) |
| De `knip:`-naamruimte, de stuknamen (`<origineel>__knip<k>`) en het herkennen van een GML-literaal (`_gml_waarde`) | `clip.termen` | `clip.plan`, `clip.stroom`, `clip.merge`, `clip.bereik`, `clip.orkest` |

Dat laatste onderscheid is opzettelijk: het verslag telt de afwijkende bytes en zoekt de
regels waarin ze staan, en dat is een tweede gang over het hele bestand. Een lezing wordt
gerapporteerd (`GwswDataset.decode_fallback`), een terugschrijving niet — dus betaalt de
schrijfweg er ook niet voor.

**De motor heeft één naad, de paden blijven twee.** De eerste rij van die tabel is de
jongste: `pyoxigraph.parse` en `pyoxigraph.serialize` stonden op vier plekken
uitgeschreven en staan nu één keer, in `rdfmotor`. Sinds issue #50 draagt diezelfde naad
niet alleen de aanroep maar ook de **foutvertaling en de prefixlezing**: `MOTORFOUTEN`
(`SyntaxError`, `ValueError`) en `is_coderingsfout` zeggen wat de motor als fout gooit en
wanneer dat een coderings- en geen syntaxfout is, en `prefixen_van` leest `parser.prefixes`.
`bestand._parse` en `schrijven` lenen die drie in plaats van elk hun eigen kopie te dragen,
en `bestand._parse` vangt daardoor smal -- `MOTORFOUTEN` plus de `TypeError` uit
`naar_rdflib` -- zodat een `MemoryError` niet langer als lege "geen geldige Turtle ()" naar
buiten komt (`test_de_foutvertaling_en_de_prefixen_wonen_alleen_in_rdfmotor` bewaakt de naad,
naast `test_alleen_rdfmotor_roept_de_motor_aan`). Dat verandert aan de twee paden
niets — de leesweg vult nog steeds een index, de schrijfweg stroomt nog steeds door —
maar het maakt een minor-bump van de motor een een-naadswijziging in plaats van een
zoektocht. pyoxigraph is pre-1.0 (0.3 → 0.4 brak de parse-signatuur al eens), en zo'n
breuk meldt zich anders als een `TypeError` op de plek waar de eerste quad opgehaald
wordt in plaats van waar de aanroep staat. Dezelfde module draagt daarom de poort op de
ondersteunde versiereeks: die staat **naast** de cap in `pyproject.toml`
(`pyoxigraph>=0.5,<0.6`) en niet in plaats daarvan — de cap voorkomt de installatie, de
poort vangt een omzeilde cap (`pip install --no-deps`, een conda-omgeving, een
handmatige upgrade) met een leesbare `MotorError` — sinds issue #31 een eigen familie
onder `DatasetError`, want dit is de enige fout van de package die niet over invoer gaat
maar over de installatie eronder. De poort valt **bij het importeren
van `rdfmotor`, één keer**: dat kost niets in de hete lus, en aan de aanroepkant zou een
`MotorError` niet in de smalle vangst van `bestand._parse` (`MOTORFOUTEN` plus `TypeError`)
vallen en dus rauw naar buiten komen op de plek waar de eerste quad opgehaald wordt in
plaats van waar de aanroep staat. Beide plekken worden aan elkaar geknoopt door
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

De leeslaag is intern in zes modules verdeeld (`domein`, `bestand`, `inlezen`, `klassen`,
`codering`, `netwerk`), maar **het oppervlak ligt in `dataset`**: elke naam die nlriochecker uit
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
- hetzelfde geldt sinds issue #27 voor de wandeling: `klim_naar_knoop`,
  `resolve_network_node` en `richting_van_geometrie` staan als vrije functies in
  `netwerk` en blijven als **methode** op `GwswDataset` bestaan, met dezelfde
  handtekening en hetzelfde gedrag — nlriochecker roept ze op de dataset aan
  (`afbakening`, `checks/topologie`, `checks/netwerk`, `uitvoer/gpkg`), dus dat is het
  contract en niet de vrije vorm. **De memo hoort bij de dataset**: `_resolved_nodes`
  blijft een `init=False`-veld op de dataclass, zodat een `replace()`-afgeleide
  (`subset`, `markeer_vulwaarden`, het cachepad) met een lege memo begint — een
  uitgedunde dataset kan anders resolven dan de volle export, want de wandeling ziet
  minder knopen. De vrije functie krijgt hem als argument en maakt er zelf nooit een aan.

`dataset.__all__` is die lijst. Een naam met een underscore is intern aan de leeslaag en
geen belofte aan de afnemer — ook waar hij een modulegrens oversteekt, zoals
`inlezen._read_aspects` dat `GwswDataset.onderdeel_aspecten` gebruikt.

### `lees_ontologie` naast `load_dataset`

`lees_ontologie(paden=None, terugvalcodering=None, *, voortgang=NUL_VOORTGANG)`
levert de ontologie-`GraafIndex` waarop de lezers van `ontologie` werken — dezelfde index
die `load_dataset` intern als `restrictiebron` opbouwt en daarna weggooit. Zonder haar
moest een afnemer die `facetbereik` of `kenmerkbereik` op een geladen dataset wilde
gebruiken de ontologie zelf parsen, en de enige weg daarheen (`bestand._parse`) is privé.
De padkeuze is die van `ontologiepaden`: `None` is de gebundelde GWSW-default 1.6 (63.614
triples, circa 0,4 s) — er reizen sinds issue #32 twee versie-benoemde bundels mee (1.6 en
1.7, zie `bronnen`). Voor `lees_ontologie` blijft `None` **onvoorwaardelijk 1.6**, en met
reden: deze functie leest alleen een ontologie en heeft geen dataset om een versie uit te
detecteren. De versiekeuze zit sinds deel c van issue #32 in `load_dataset`, dat de dataset
éérst parst en dan bij `None` de gebundelde ontologie kiest die bij de gedetecteerde
dataset-basis hoort (`_gebundelde_paden_voor_basis`). Een lege lijst is de expliciete keuze
om zonder ontologie te lezen, en meerdere bestanden stapelen in volgorde in één index.

**De snit zit onder de fase, niet erop.** Beide functies lopen langs één privé-hulp,
`_stapel_ontologie(paden, fallback_encoding, voortgang)`: de lus die per bestand
`bestand._parse(pad, ..., index=...)` doet en daarna een voortgangsstap met de
bestandsnaam meldt. Die hulp opent zelf geen fase, en dat is precies de reden dat hij
bestaat. `load_dataset` telt de ontologiebestanden mee in zijn eigen fase `"TTL laden"`
met `1 + len(paden)` stappen (de dataset eerst), en die voortgang is bevroren; zou
`load_dataset` de nieuwe functie *inclusief* haar `start_fase` aanroepen, dan kreeg elke
afnemer met een voortgangsbalk er stilzwijgend een tweede fase bij.
`lees_ontologie` opent voor zichzelf wél een fase, `"Ontologie laden"`, met één stap per
bestand. `test_de_voortgang_van_load_dataset_blijft_een_enkele_ttl_fase` in
`tests/test_dataset.py` is de bewaker van de eerste helft;
`test_lees_ontologie_levert_de_restrictiebron_van_load_dataset` onderschept
`_subclass_closure` en houdt de twee wegen op tripelinhoud gelijk, zodat "hetzelfde
parseerpad" geen belofte in een docstring blijft.

De GC ligt in allebei de gevallen stil (`bestand._gc_uit`, hersteld in een `finally`), en
de fout bij een onleesbaar of ongeldig bestand is dezelfde `DatasetError` als bij de
lader. Twee kleinere keuzes eromheen, allebei uit de review van #33 en allebei tegen de
intuïtie in:

- **Ook een lege lijst levert een fase op**, met totaal nul en zonder stappen. Een
  aanroeper die fasen meetelt — een balk per fase, een teller in een log — hoort de
  fase-indeling niet van de *inhoud* van zijn argument te zien afhangen; "soms een fase,
  soms geen" is het lastigere contract om tegenaan te programmeren dan een fase die
  eerlijk nul zegt.
- **Het tripelaantal staat gepind** (`AANTAL_TRIPELS_GWSW16` in `tests/test_dataset.py`).
  Dat is een derde plek die bij een ontologie-upgrade meeschuift, naast
  `scripts/maak_gwsw_index.py` en de versieregel in `CLAUDE.md` — hij meldt zich vanzelf,
  want de test wordt rood. `tests/test_ontologie.py` draagt sinds #19 al twee zulke
  getallen (39 datatypes, 709 kenmerkklassen), en
  `test_de_publieke_leesweg_geeft_dezelfde_facet_en_kenmerklezing` houdt die lezing op
  `lees_ontologie()` gelijk aan die op de `_parse`-weg.

Wat er níét bij hoort: een veld op `GwswDataset` — zie de vorige sectie.

## De cache leest mee met de lader

`cache.cachesleutel` hasht niet alleen de invoerbestanden en de bibliotheekversies maar
ook **de broncode van de hele leeslaag**: `cache.LADERMODULES` -- `dataset`, `bestand`,
`inlezen`, `domein`, `klassen`, `codering`, `namen`, `graaf`, `geometry`, `netwerk`,
`ontologie` en `rdfmotor`.
Dat is de garantie dat een cache nooit achterloopt op een wijziging in de lezing.
Zonder opgegeven ontologie hasht de sleutel sinds issue #52 alleen de gebundelde bundel van
de versie die een goedkope prefix-scan van de datasetkop detecteert -- dezelfde die de lader
dan kiest -- in plaats van álle bundels, met terugval op alle bundels als die scan geen
`gwsw:`-prefix vindt.
`rdfmotor` staat erbij ook al deelt de schrijfweg hem: `bestand._parse` haalt zijn quads
daarlangs, dus een andere aanroep van de motor is een andere lezing. Wie de leeslaag
opnieuw indeelt, moet de nieuwe modules aan die lijst toevoegen: een vergeten module
levert geen fout op maar een cache die na een wijziging de oude lezing blijft teruggeven.
Twee tests in `tests/test_cache.py` houden dat bij: de ene parametriseert over
`LADERMODULES` en toont per module dat een gewijzigde broncode een andere sleutel geeft,
de andere eist dat elke module van de package óf in die lijst staat óf met een reden in
de uitzonderingsverzameling ernaast. Die tweede telt met `rglob` en ziet dus ook de fasen
in `clip/`; ze staan er alle negen met naam bij, want een nieuwe fase hoort zich net zo
goed te melden als een nieuwe module in de wortel.

Verplaatste code verandert die sleutel, dus na een hersnit worden bestaande caches één
keer opnieuw opgebouwd. Dat is de bedoelde werking en geen gedragswijziging -- de sleutel
hasht *bestanden* en niet functies, dus ook een AST-gelijke verhuizing als die van issue
#26 (`bestand` erbij) of #27 (`netwerk` erbij) rekent één keer af en is daarna weer een
treffer. `netwerk` draait weliswaar *ná* het laden en van zijn uitkomst wordt niets
gepickeld, maar hij staat er om de sterkste reden die de lijst kent: die code zat tot #27
in `dataset.py` en telde dus al mee. Hem er nu buiten laten zou de garantie stilzwijgend
versmallen op het moment dat er alleen van bestand gewisseld wordt. `cache` zelf
staat er nadrukkelijk **niet** in — de sleutel kan zichzelf niet hashen — dus een
wijziging aan deze module laat bestaande caches met rust; `LADER_VERSIE` is de knop om
dat alsnog af te dwingen.

Bij een cachetreffer krijgt `GwswDataset.graph` geen `GraafIndex` maar `cache.LuieGraaf`:
de graafpickle is op een gemeentebrede export tientallen seconden en honderden megabytes,
en de meeste runs raken hem niet aan. Hij komt pas van schijf bij de eerste leesbewerking
(`_geladen`), en is hij dan beschadigd, dan leest `_herstel` hem alsnog uit de brondata en
schrijft de cache opnieuw weg in plaats van de run te laten crashen — `cache.py` stelt die
functie samen, `LuieGraaf` kent zelf geen paden en geen `load_dataset`.

Sinds issue #34 draagt die plaatsvervanger **het leescontract expliciet**: `objects`,
`subjects`, `value`, `subject_objects` en `heeft_subject` staan als methode op de klasse,
met dezelfde handtekening als op `GraafIndex` en elk niets anders doend dan doorgeven
(`__len__` en `__contains__` stonden er al). Voor de aanroeper verandert er niets — via
`__getattr__` kwam hetzelfde antwoord — maar voor mypy wel: een doorgifte via
`__getattr__` heeft type `object`, en dan is een typefout in een doorgegeven aanroep pas
zichtbaar als hij op de leesweg als `AttributeError` valt. Met de methoden erop vervult
`LuieGraaf` `graaf.GraafLezer` structureel, naast `Graph` en `GraafIndex`;
`tests/typecheck/graaflezer.py` draagt dat bewijs en `tests/test_cache.py` houdt per
bewerking zowel het antwoord als het laadmoment gelijk aan een verse `GraafIndex`.
`__getattr__` blijft als vangnet voor alles buiten het contract. Wat er **niet** mee
verschoven is: de `cast(GraafIndex, ...)` in `laad_met_cache`. `GwswDataset.graph` staat
gepind op de concrete `GraafIndex` (`tests/test_publieke_api.py`) en dat veld verbreden
naar een protocol raakt een contract dat nlriochecker importeert — een auteursbeslissing
(`CLAUDE.md`, Harde regels), niet iets wat er bij deze stap bij hoort.

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
