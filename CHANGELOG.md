# Changelog

## [Unreleased]
- De netwerkwandeling staat los van de leeslaag: nieuwe module `netwerk` (issue #27,
  modulariteit; **additief** — geen bevroren contract geraakt). `resolve_network_node`,
  `klim_naar_knoop`, `_schakels` en `richting_van_geometrie` verhuizen van methoden op
  `GwswDataset` naar vrije functies die hun context als parameter nemen: de knopen
  (`nodes`), het typepredicaat (`is_a`) en waar er gememoiseerd wordt de memo zelf. De
  verhuizing is **puur in de bodies**: elke body is per functie AST-gelijk aan a0bb934
  modulo precies zes substituties (`self.nodes`→`nodes`, `self.is_a`→`is_a`,
  `self._resolved_nodes`→`memo` en de drie zelfaanroepen naar hun vrije vorm), en de
  parameterkop van elke vrije functie begint letterlijk met de parameters van de methode.
  Wat er wél mee verschuift is de **dispatch**, en dat is aan geen enkele uitkomst te
  zien: waar de methoden elkaar via `self.` aanriepen, roepen de vrije functies elkaar
  rechtstreeks aan, dus een subklasse-override of een `monkeypatch.setattr` op
  `GwswDataset` bereikt de wandeling binnenin niet meer (onderscheppen doe je voortaan op
  `netwerk`). Nlriochecker kent geen subklasse van `GwswDataset` en patcht geen van de
  drie methoden — geverifieerd met een AST-sweep over `src/`, `tests/` en `scripts/` van
  de afnemer — dus in de praktijk raakt het niemand.
  **De vier methoden blijven bestaan** en zijn doorgeefluiken geworden: dezelfde
  handtekening (gepind in `tests/test_publieke_api.py`), dezelfde uitkomst en dezelfde
  memo-semantiek — `GwswDataset._resolved_nodes` blijft een `init=False`-veld op de
  dataclass, zodat een `replace()`-afgeleide (`subset`, `markeer_vulwaarden`, het
  cachepad) met een lege memo begint; het doorgeefluik geeft die van zijn eigen instantie
  mee en de vrije functie maakt er nooit zelf een aan. Wat het oplevert is dat de zwaarst
  verweven logica van de leeslaag toetsbaar is zonder een ingelezen export: een
  handgebouwd `nodes`-woordenboek en een `is_a`-lambda volstaan (`tests/test_netwerk.py`),
  en daarmee komen ook de vier `None`-takken van `richting_van_geometrie` onder toets die
  in geen enkele TTL-fixture voorkwamen. `netwerk` leunt alleen op `domein` en shapely;
  `test_de_netwerksnit_ligt_vast` legt de vier namen, die ene toegestane import en de
  *dunheid* van de doorgeefluiken vast (op de AST, want een teruggekopieerde wandeling
  laat elke gedragstest groen). `docs/architectuur.md` draagt de nieuwe rij in de
  lagentabel. `netwerk` staat in `cache.LADERMODULES`, net als elke leeslaagmodule: die
  code telde tot nu toe via `dataset.py` al mee in de sleutel en dat blijft zo, dus
  **bestaande caches worden één keer opnieuw opgebouwd** — de bedoelde werking van een
  hersnit en geen gedragswijziging. **Eén meetbaar prijskaartje, en het staat er als
  meting en niet als claim**: een gememoiseerde `resolve_network_node` doet nu één
  Python-aanroeplaag extra (plus het binden van `self.is_a`). Geen van de twee
  benchmarkscripts raakt dit pad — `benchmark.py` meet het laden, dat de wandeling niet
  aanroept, en `benchmark_is_a.py` meet `is_a`/`of_class` — dus gemeten met een
  wegwerpmeting: oud en nieuw om en om in één proces, op een synthetische dataset van
  20.000 putten met een compartiment onder twee houders, minimum over veertig stootjes
  (de machine droeg ander werk; een minimum overleeft dat, een gemiddelde niet). Uitkomst,
  tweemaal reproduceerbaar: 352 → 473 ns per warme aanroep (+121 ns, +34% op een lus die
  *niets anders* doet) en 7,2 → 7,4 µs per koude aanroep (+2%). Op de ruim een miljoen
  aanroepen van een nlriochecker-run is dat circa +0,12 s, tegenover een lezing die op
  dezelfde export 20 s kost. Als regressiecheck ook
  gepaard nagemeten op de De Wolden- en Hoogeveen-export, back-to-back en op een machine
  die ander werk droeg: `scripts/benchmark.py --paden load_dataset --herhalingen 3`
  mediaan 20,29 s vóór tegen 20,39 s ná bij een gelijke piek (1219 MiB) en een identieke
  lezing (1.877.729 triples, 23.485 knopen, 23.440 strengen), en `scripts/benchmark_is_a.py`
  minimum 1,25 s vóór tegen 1,32 s ná bij exact dezelfde 1.126.200 aanroepen — allebei
  paden die de wandeling niet aanraken, dus ruis. De twee `zwaar`-tests draaien groen op
  dezelfde export.
- Het parseerpad staat los van de domeinlezers: nieuwe module `bestand` (issue #26,
  modulariteit; **additief** — geen bevroren contract geraakt). `_parse`, `_decode`,
  `_quiet_rdflib` en `_gc_uit` verhuizen ongewijzigd van `inlezen` naar
  `gwsw_orox_helpers.bestand`; alle vier blijven privé en geen enkele naam die
  nlriochecker importeert verandert van plaats, handtekening of gedrag (foutteksten
  inbegrepen). De verhuizing is **puur**: per functie AST-gelijk aan bea96a7, en de 31
  moduleniveau-symbolen van het oude `inlezen` zijn nu 27 + 4 met nul verschillen. Wat
  het oplevert is dat de twee clusters die alleen de `GraafIndex` deelden ook echt los
  staan — `inlezen` kent sindsdien geen paden, bytes of coderingen meer (zijn imports
  gaan van acht naar vijf) en is te testen zonder een echt bestand, terwijl `bestand`
  alleen op `codering`/`errors`/`graaf`/`rdfmotor` leunt. Er loopt met opzet **geen** rand
  tussen de twee: `inlezen` her-importeert niets, `dataset` haalt `_parse` en `_gc_uit`
  rechtstreeks bij `bestand`. `tests/test_publieke_api.py::test_de_bestandssnit_ligt_vast`
  legt de vier namen, de toegestane imports en die ontbrekende rand vast, en
  `docs/architectuur.md` draagt de nieuwe rij in de lagentabel. `bestand` staat in
  `cache.LADERMODULES`, zoals elke leeslaagmodule: de sleutel hasht bestanden en niet
  functies, dus **bestaande caches worden één keer opnieuw opgebouwd** — de bedoelde
  werking van een hersnit en geen gedragswijziging. **Geen perf-claim, en er valt niets te
  meten**: elke verplaatste functie is AST-gelijk, dus de hete lus voert exact dezelfde
  bytecode uit; wat erbij komt is één module-import bij het laden van de package. Als
  regressiecheck wél gepaard nagemeten op de De Wolden- en Hoogeveen-export
  (`scripts/benchmark.py --paden load_dataset --herhalingen 3`, back-to-back): mediaan
  20,11 s vóór tegen 20,28 s ná en een piek van 1220 tegen 1219 MiB — ruis — met een
  identieke lezing (1.877.729 triples, 23.485 knopen, 23.440 strengen).
- `cache.LuieGraaf` draagt het leescontract expliciet (issue #34, typeveiligheid;
  **additief** — geen bevroren contract geraakt). De vijf bewerkingen die `GraafIndex`
  aanbiedt (`objects`, `subjects`, `value`, `subject_objects`, `heeft_subject`) staan nu
  als methode op de klasse, met dezelfde handtekening en niets anders doend dan
  `self._geladen().<methode>(...)`; `__len__` en `__contains__` stonden er al.
  `__getattr__` blijft als vangnet voor alles daarbuiten. De antwoorden zijn dezelfde, het
  zelfherstel bij een beschadigde graafcache is ongewijzigd, en de graafpickle komt nog
  steeds pas bij de eerste leesbewerking van schijf. Eén nuance, en ze gaat de goede kant
  op: dat laden hangt nu aan de *aanroep* en niet meer aan de attribuuttoegang, want
  `getattr(luie, "objects")` liep vroeger via `__getattr__` en las de pickle al. Strikt
  luier dus, nooit gretiger. Wat verandert is wat mypy ziet: een doorgifte via
  `__getattr__` typeert elke leesbewerking als `object`, dus de vijf aanroepen op
  `GraafIndex` in de doorgeefmethoden worden nu gecontroleerd — hernoemt `GraafIndex` een
  parameter, dan wordt `cache.py` rood in plaats van pas de leesweg. `LuieGraaf` vervult
  daarmee `graaf.GraafLezer` structureel — bewezen in `tests/typecheck/graaflezer.py`,
  naast `Graph` en `GraafIndex` — al ziet een aanroeper daar pas iets van als de
  `cast(GraafIndex, ...)` valt. Die blijft namelijk staan: `GwswDataset.graph` is op de
  concrete `GraafIndex` gepind en dat veld verbreden is een auteursbeslissing (stap 2,
  apart geparkeerd). De cachesleutel verschuift niet — `cache` staat met reden in
  `BUITEN_DE_SLEUTEL` en niet in `LADERMODULES` — dus bestaande caches blijven geldig
  (nagemeten op de De Wolden- en Hoogeveen-export: sleutel `17fed55b…` vóór en ná). Geen
  perf-claim; indicatief gaf een cache-hit-run op diezelfde export geen meetbaar verschil.
- `tests/test_schrijven.py::test_juinen_blijft_isomorf` leest de sinds #10 gebundelde
  Juinen-fixture in plaats van een pad buiten de repo (uitgestelde minor uit #10). Aanleiding:
  de externe map `nlriochecker/data/gwsw_orox_ttl` was op 30-08 tussentijds afwezig, waardoor
  de dekkingsstap van de poort één keer rood werd terwijl de gewone pytest-run groen was; de
  test slaat zichzelf nu nooit meer over en is niet meer machinegebonden.
- De twee hete lezers bouwen hun termen niet meer per aanroep (issue #23, performance;
  **additief** — geen bevroren contract geraakt). `GwswDataset.graph_types_of` maakte per
  aanroep een `URIRef` mét rdflib's validatieregex uit tekst die al een geldige
  graafsleutel is, plus een `RDF.type`-lezing op rdflib's `DefinedNamespace` (geen
  attribuut maar een `__getattr__`); hij gebruikt nu `graaf._uriref_snel` en het
  `_RDF_TYPE` dat `inlezen` al eenmalig las — geleend en niet nog eens neergezet, want de
  `URIRef`-vorm van een GWSW-IRI woont daar (`docs/architectuur.md`).
  `GwswDataset.subjects_of_class` bouwde dezelfde twee termen per klasse van een
  afsluiting en gaat mee langs hetzelfde snelpad. `inlezen._deksel_kenmerk`
  herbouwde dezelfde drie dekselklassen (`Putdeksel`, `Putdeksel_LichtVerkeer`,
  `Putdeksel_ZwaarVerkeer`) per put én per onderdeel van die put; `_read_nodes` zet ze nu
  één keer om, buiten de knopenlus, en geeft ze als `frozenset[URIRef]` door. **Signatuur
  vóór → na**: alleen de private `inlezen._deksel_kenmerk(graph, subject, deksel_klassen:
  frozenset[str])` → `frozenset[URIRef]`. `_read_nodes` houdt zijn `frozenset[str] | None`,
  `graph_types_of` blijft een `frozenset[str]` teruggeven en `load_dataset` roept alles
  aan zoals het was. **Gemeten** (gepaard, De Wolden en Hoogeveen: 1.877.729 triples,
  23.485 knopen, 23.440 strengen): de microbenchmark op `graph_types_of` — alle 46.925
  knoop- en streng-URI's, oud en nieuw afwisselend in één proces, 5 ronden — gaat van
  0,195 s gemiddeld (mediaan 0,192) naar 0,107 s (mediaan 0,106), dus **−45% en circa
  1,9 µs per aanroep**; een tweede, losse run gaf 0,196 → 0,115 s gemiddeld (mediaan 0,192
  → 0,106), dezelfde mediaan-uitkomst met één uitschieter in het gemiddelde. Op het
  laadpad (`scripts/benchmark.py --paden load_dataset --herhalingen 3`) is het verschil
  **niet meetbaar**, en dat is met twéé rondes in omgekeerde volgorde vastgesteld in
  plaats van met één: met de oude stand eerst 21,44 s gemiddeld (mediaan 21,68) tegen
  20,74 s (mediaan 20,59) — schijnbaar −3,3% —, en met de nieuwe stand eerst 21,35 s
  (mediaan 21,27) tegen 19,89 s (mediaan 19,91) voor de oude — schijnbaar +7,3%. Over alle
  zes de metingen per kant: 20,67 s gemiddeld (mediaan 20,10) vóór tegen 21,04 s (mediaan
  21,04) ná. Het teken hangt aan de volgorde en niet aan de wijziging; wie hier één ronde
  had gedraaid, had een winst van 5% gemeld die er niet is. De piek blijft 1219 MiB.
  **Op het laden wordt dus niets beloofd** — daar is dit een opruiming; de winst zit aan de
  opvraagkant. De gelijkheid waarop het rust staat vast in
  `test_uriref_snel_geeft_dezelfde_term_voor_elke_iri_in_de_gebundelde_ontologie`
  (`tests/test_graaf.py`), dat het snelpad tegen `URIRef()` houdt op alle **3.367** unieke
  IRI's van de gebundelde GWSW 1.6-ontologie — een vijfde getal dat bij een
  ontologie-upgrade meeschuift en zich vanzelf meldt. Daarnaast drie bewakers in
  `tests/test_dataset.py`: `test_de_hete_lezers_bouwen_hun_termen_niet_per_aanroep` (aan de
  AST, zodat de wegwerptermen niet stilletjes terugkomen),
  `test_de_dekseltermen_worden_een_keer_gebouwd_en_niet_per_put` (een telling op
  `inlezen._uriref_snel`, want dát de omzetting buiten de knopenlus staat is aan de vorm
  van `_deksel_kenmerk` niet te zien — zet iemand haar terug in de lus, dan blijft de
  AST-bewaker groen en wordt deze rood) en
  `test_graph_types_of_geeft_dezelfde_typen_als_de_urirefweg` (hetzelfde antwoord voor elke
  knoop, streng en elk graafonderdeel, plus twee missers). De meting is na te lopen met
  het nieuwe `scripts/benchmark_graph_types_of.py`, dat beide wegen uitgeschreven draagt
  en ze per ronde afwisselt. **Twee dingen die wél veranderen en geen antwoord zijn**:
  `_uriref_snel` slaat `_is_valid_uri` over, dus een misvormde IRI levert op deze twee
  opvraagplekken geen `logger.warning` meer op (bij het vullen was die er al niet — zie
  `bestand._quiet_rdflib`), en een aanroep met een niet-`str` liep vroeger op een
  `TypeError` stuk waar hij nu een misser geeft. Allebei buiten de getypeerde afspraak,
  allebei genoteerd in de docstring van `_uriref_snel`. **Cachesleutel**: `dataset`,
  `inlezen` en `graaf` staan alle drie in `cache.LADERMODULES`, dus deze wijziging
  verschuift de sleutel en bestaande caches worden één keer opnieuw opgebouwd — bedoelde
  werking, geen gedragswijziging.
- `GwswDataset.is_a` vraagt de doorsnede niet meer, maar de disjunctie (issue #12,
  doorgevoerd bij #23). `bool(typen & closure(root))` bouwde per aanroep een
  wegwerp-verzameling om er alleen de leegheid van te vragen; `not
  typen.isdisjoint(closure(root))` beantwoordt dezelfde vraag zonder die verzameling.
  Gedragsgelijk voor elke combinatie — ook de lege typenverzameling (een URI die geen knoop
  en geen streng is) en een wortel die de hierarchie niet kent, waar `closure` op de wortel
  zelf blijft steken; `test_is_a_geeft_hetzelfde_antwoord_als_de_doorsnedevraag` houdt de
  twee formuleringen naast elkaar. `graph_is_a` ging mee: één predicaat hoort in deze
  klasse niet in twee gedaanten te staan. **Gemeten** met `scripts/benchmark_is_a.py` (gepaard,
  1.126.200 `is_a`-aanroepen per herhaling, 3 herhalingen, aan beide kanten dezelfde
  266.650 treffers): 1,54 s gemiddeld (mediaan 1,51; min 1,41) → **1,29 s** (mediaan 1,27;
  min 1,27), dus **−16% op het gemiddelde en −16% op de mediaan** (−10% op het minimum).
  Ruimer dan de −8,8% die de meting bij #12 voorspelde.
- De handtekening van `graaf.naar_rdflib` staat gepind in `tests/test_publieke_api.py`
  (auteursbeslissing bij issue #21). nlriochecker importeert hem rechtstreeks
  (`scripts/maak_voorbeeld.py:57`) om een pyoxigraph-parse in rdflib-termen te lezen zonder
  de index te bouwen; net als bij `dataset.lees_ontologie` is dit een naam die de auteur
  aanwees en niet een die uit de AST-sweep over de afnemer komt. **Additief**: de pin legt
  de bestaande handtekening vast en verandert er niets aan.
- De ontologie-`GraafIndex` is als publieke functie bereikbaar (issue #33, vervolg op
  #19; architectuur, **additief** — geen bevroren contract geraakt). **Nieuw en publiek**:
  `dataset.lees_ontologie(paden: list[Path] | None = None, terugvalcodering:
  str | None = None, *, voortgang: Voortgang = NUL_VOORTGANG) -> GraafIndex`, ook
  opgenomen in `dataset.__all__`. De parameternamen zijn Nederlands (auteursbeslissing
  30-08, `CLAUDE.md` boven symmetrie met de bevroren Engelse van `load_dataset`; ze
  landden eerst als `ontology_paths`/`fallback_encoding` en zijn vóór enige afnemer
  hernoemd). Hij levert precies de index die `load_dataset` intern
  als `restrictiebron` opbouwt en daarna weggooit; wie de lezers van `ontologie`
  (`facetbereik`, `datatype_van_kenmerk`, `kenmerkbereik`, `verwachte_property`,
  `functie_van_klasse`) op een geladen dataset wil gebruiken, hoefde daarvoor tot nu toe
  `bestand._parse` na te bootsen — en die is privé. De padkeuze is die van
  `ontologiepaden`: `None` is de gebundelde GWSW 1.6, een lege lijst is de expliciete
  keuze om zonder ontologie te lezen, meerdere bestanden stapelen in volgorde in één
  index. **Gemeten**: de gebundelde ontologie levert 63.614 triples (het getal uit #19,
  nu als pin in `tests/test_dataset.py`) in circa 0,43 s per lezing (drie lezingen:
  0,418 / 0,447 / 0,434 s; indicatief, geen perf-claim).
  **`load_dataset` blijft gedragsgelijk**, en de snit is daarop gekozen: beide functies
  delen de privé-hulp `_stapel_ontologie`, die per bestand parseert en een voortgangsstap
  meldt maar **zelf geen fase opent**. `load_dataset` houdt daardoor zijn ene fase
  `"TTL laden"` met `1 + len(paden)` stappen; `lees_ontologie` opent zijn eigen fase
  `"Ontologie laden"` met één stap per bestand. Zou het delen op faseniveau gebeuren, dan
  kreeg elke afnemer met een voortgangsbalk er stilzwijgend een tweede fase bij.
  Twee nieuwe bewakers in `tests/test_dataset.py`:
  `test_de_voortgang_van_load_dataset_blijft_een_enkele_ttl_fase` (fase, stappen en
  volgorde van de lader) en `test_lees_ontologie_levert_de_restrictiebron_van_load_dataset`
  (onderschept `_subclass_closure` en houdt de twee wegen op tripelaantal én tripelinhoud
  gelijk). `test_de_publieke_leesweg_geeft_dezelfde_facet_en_kenmerklezing` in
  `tests/test_ontologie.py` houdt de facet- en kenmerklezing op `lees_ontologie()` gelijk
  aan die op de `_parse`-weg van #19 (39 datatypes, 709 kenmerkklassen), zodat die
  gelijkheid niet alleen transitief geldt. **Twee kleinere keuzes uit de review**: ook een
  lege lijst levert één fase op (totaal nul, geen stappen) — de fase-indeling hoort niet
  van de inhoud van het argument af te hangen; en het tripelaantal is een derde plek die
  bij een ontologie-upgrade meeschuift, naast `scripts/maak_gwsw_index.py` en de
  versieregel in `CLAUDE.md` (hij meldt zich vanzelf: de test wordt rood).
  **Cachesleutel**: `dataset` staat in `cache.LADERMODULES`, dus deze wijziging
  verschuift de sleutel en bestaande caches worden één keer opnieuw opgebouwd — bedoelde
  werking, geen gedragswijziging. **Bewust níét meegenomen**: een ontologieveld op
  `GwswDataset`. Die dataclass staat gepind in `tests/test_publieke_api.py` en blijft
  dicht; dat is een auteursbeslissing (`CLAUDE.md`, Harde regels).
- De laaggrens tussen `ontologie` en de graaf is een `typing.Protocol` geworden (issue
  #21, architectuur; additief, geen bevroren contract geraakt). **Nieuw en publiek**:
  `graaf.GraafLezer`, een protocol met precies twee leden —
  `objects(subject: RdfNode, predicate: RdfNode, /) -> Iterator[RdfNode]` en
  `value(subject: RdfNode, predicate: RdfNode, /) -> RdfNode | None`. `graaf.GraafIndex`
  en `rdflib.Graph` vervullen het allebei **structureel**: geen van beide erft ervan,
  geen van beide weet ervan. **Signaturen vóór → na**: `facetbereik`,
  `datatype_van_kenmerk`, `kenmerkbereik`, `verwachte_property`, `functie_van_klasse` en
  het interne `_lijstleden` namen `graph: Graph | GraafIndex` en nemen nu
  `graph: GraafLezer` — verbreding, geen versmalling: elke `Graph` en elke `GraafIndex`
  die paste, past nog, en het gedrag is regel voor regel hetzelfde. **Gemeten**: zes
  `Graph | GraafIndex`-annotaties in `src/` → nul (een kale
  `grep -rc "Graph | GraafIndex" src/` telt 6 → 2, want de twee resterende treffers zijn
  proza in een docstring — die van `graaf` en die van `ontologie`, allebei over wat er
  vroeger stond). Het aantal `cast(` in `src/` blijft twee: de `LuieGraaf`-cast in
  `cache` raakt een gepind contract en de `module.__file__`-cast staat er los van — zie
  hieronder. `uv run mypy`: 0 issues, 24 → 25 bronbestanden.
  **Twee leden en niet zeven**, want het protocol is de smalste vorm die werkt en niet de
  getypte vorm van het hele leescontract: `heeft_subject` is een eigen aanvulling die
  `rdflib.Graph` niet kent, dus dat lid zou de `Graph`-kant per direct uitsluiten, en
  `subjects`/`subject_objects`/`__contains__`/`__len__` roept `ontologie` niet aan. De
  parameters staan positioneel (`/`), zodat een rdflib-upgrade die `subject` hernoemt de
  vervulling niet breekt. **Bewijs in de poort**: `pyproject.toml` zet `tests/typecheck`
  in `[tool.mypy] files` en `warn_unused_ignores = true` aan;
  `tests/typecheck/graaflezer.py` geeft een `Graph` én een `GraafIndex` aan een
  `GraafLezer`-parameter (positief) en biedt twee objecten aan die het protocol niet
  vervullen met `# type: ignore[arg-type]` erop (negatief) — wordt zo'n regel ooit
  geldig, dan valt mypy om op de ongebruikte ignore. Twee nieuwe tests in
  `tests/test_ontologie.py` houden het protocol precies zo breed als `ontologie` het
  gebruikt (AST-sweep) en toetsen de runtimekant op allebei de graafvormen.
  **Cachesleutel**: `graaf` en `ontologie` staan allebei in `cache.LADERMODULES`, dus deze
  wijziging verschuift de sleutel en bestaande caches worden één keer opnieuw opgebouwd —
  bedoelde werking, geen gedragswijziging. **Bewust níét meegenomen**: de gepinde
  `dataset.parts_of`/`part_holders_of`/`aspects_of`/`aspect_holders_of`, het veld
  `GwswDataset.graph` en de `cast(GraafIndex, LuieGraaf(...))` in `cache` blijven op het
  concrete `GraafIndex` — die raken het bevroren contract in `tests/test_publieke_api.py`
  en zijn een auteursbeslissing.
- De facetlezing is bereikbaar geworden vanaf de echte leesweg (issue #19, architectuur;
  additief, geen bevroren contract geraakt). `ontologie.facetbereik`,
  `datatype_van_kenmerk` en `kenmerkbereik` liepen over de `owl:withRestrictions`-lijst
  met `rdflib.collection.Collection`, en dat itereert via `Graph.items` — dus eisten ze
  een echte `rdflib.Graph`, terwijl `load_dataset` de ontologie in een `GraafIndex` leest
  en die als `restrictiebron` doorgeeft. De "ontbrekende schakel" uit issue #35 draaide
  daardoor **alleen in tests**: op de leesweg liep zij op een
  `AttributeError: 'GraafIndex' object has no attribute 'items'` stuk, en nlriochecker kon
  haar niet aanroepen. **Signaturen vóór → na**: `facetbereik(graph: Graph, datatype)`,
  `datatype_van_kenmerk(graph: Graph, kenmerk)` en `kenmerkbereik(graph: Graph, kenmerk)`
  nemen nu alle drie `graph: Graph | GraafIndex` — dezelfde verbreding die
  `verwachte_property` en `functie_van_klasse` al hadden. Verbreden, niet versmallen: elke
  bestaande aanroep met een `Graph` doet wat hij deed. **Nieuw en intern in `ontologie`**:
  `_lijstleden(graph: Graph | GraafIndex, kop: RdfNode) -> Iterator[RdfNode]`, dat de
  `rdf:first`/`rdf:rest`-ketting zelf afloopt met niets anders dan de `value` die allebei
  de graafvormen aanbieden. Bewust met een underscore: `facetbereik` is de enige
  aanroeper, en een tweede aanroeper maakt hem later additief publiek. **Dekking van de
  leesweg: van 0 naar 39 datatypes en 709 kenmerkklassen**, waarvan er 38 respectievelijk
  40 daadwerkelijk een bereik dragen (GWSW 1.6). Dat getal meet *aanroepbaarheid op de
  graafvorm die de lader levert* en niet gebruik: binnen deze package roept nog niets in
  `src/` deze drie lezers aan — zij zijn er voor nlriochecker. Drie nieuwe tests lezen die
  hele populatie langs allebei de wegen en vergelijken de uitkomsten woordelijk; de
  `GraafIndex` erin komt uit `bestand._parse` op de gebundelde ontologie, dus dat is de
  leesweg zelf en geen nabootsing. De derde pint meteen `verwachte_property` en
  `functie_van_klasse` over alle 2.087 `owl:Class`en vast — die twee namen allebei de
  vormen al, maar dat stond alleen op een fixture van vijf klassen vast. Ook de
  handgeschreven fixture draait sinds deze wijziging op allebei de graafvormen
  (geparametriseerde `graaf`-fixture), zodat een verschil tussen de twee meteen opvalt.
  **Wat hiermee nog niet af is**, en bewust niet: `load_dataset` bouwt zijn
  ontologie-`GraafIndex` als lokale `restrictiebron` en bewaart hem niet op `GwswDataset`
  (dat draagt alleen de kleine afgeleide woordenboeken; `.graph` is de *dataset*graaf).
  Een afnemer die deze lezers op een geladen dataset wil loslaten, leest de ontologie dus
  nog altijd zelf in. Dat dichten vraagt een veld bij `GwswDataset`, en die handtekening
  is gepind in `tests/test_publieke_api.py`: een auteursbeslissing volgens de Harde regels
  in `CLAUDE.md`, geen agentbeslissing — dus hier gemeld en niet gedaan.
  **De randgevallen van een RDF-lijst zijn opzettelijk die van `Graph.items`**, tegen
  `Collection` geijkt in de tests: een afgebroken lijst (schakel zonder `rdf:rest`)
  eindigt stil met wat er wél stond, een schakel zonder `rdf:first` slaat een lid over,
  `rdf:nil` en een onbekende kop leveren niets op, een geneste lijst wordt niet
  afgevlakt — en een **cyclus** in `rdf:rest` is de enige harde fout: geen oneindige lus
  maar dezelfde `ValueError("List contains a recursive rdf:rest reference")` die
  `Collection` gaf, woordelijk gelijk zodat wie hem ving hem blijft vangen. Een stille
  afbreking zou daar een willekeurig afgekapt bereik opleveren, en dat is precies de
  stille verkeerde uitkomst die niet mag. Ter indicatie, één run op de gebundelde
  ontologie (63.614 triples): de facetlezing over alle 39 datatypes kost 3,0 ms via
  `Graph` en 0,9 ms via `GraafIndex`, de kenmerklezing over alle 709 kenmerkklassen
  25,1 ms tegen 10,3 ms — de weg die er eerst niet was, is ook de snelste. **De
  cachesleutel verschuift**: `ontologie` staat in `cache.LADERMODULES` (en `graaf`, waarvan
  hier de docstring bijgetrokken is) en de sleutel hasht hun broncode, dus bestaande caches
  worden één keer opnieuw opgebouwd. Dat is de bedoelde werking, geen gedragswijziging.
  `docs/architectuur.md` heeft er een eigen sectie over gekregen; de verbreding is zo
  gelaten dat het `GraafLezer`-protocol uit issue #21 er later overheen past zonder aan de
  handtekeningen iets anders te veranderen dan de naam van het type.
- Eén naad naar pyoxigraph: de nieuwe interne module `gwsw_orox_helpers.rdfmotor`
  (issue #18, upgradebaarheid; geen gedragswijziging). **Alle vier de parse/serialize-
  callsites gaan er nu doorheen** — `bestand._parse` (bytes), `schrijven.lees_orox` (een
  pad, of tekst bij een `fallback_encoding`) en `schrijven.schrijf_orox_quads` (de
  serializer) — waar er vier keer een eigen `pyoxigraph.parse(...)` /
  `pyoxigraph.serialize(...)` met `RdfFormat.TURTLE` stond. Na de wijziging staat
  `pyoxigraph.parse`/`serialize` nog op **nul** plekken buiten `rdfmotor`
  (`grep -rn "pyoxigraph.parse\|pyoxigraph.serialize" src/`). **Nieuw, intern en
  additief**: `ontleed_turtle(bron: bytes | str) -> QuadParser` voor Turtle die al in het
  geheugen staat, `ontleed_turtle_bestand(pad: Path) -> QuadParser` voor een bestand dat
  streamend van schijf gelezen wordt,
  `serialiseer_turtle(quads, doel: IO[bytes], *, prefixen: dict[str, str]) -> None` en
  `controleer_versie(versie: str) -> None` met `ONDERSTEUNDE_REEKS` (`>=0.5,<0.6`). De
  namen zijn Nederlands (CLAUDE.md) waar het issue `parse_turtle`/`serialize_turtle`
  schreef. `test_alleen_rdfmotor_roept_de_motor_aan` houdt de naad enkelvoudig: die loopt
  de AST van elke module in de package af, zodat "één naad" een test is en niet een
  belofte in een docstring. **Twee ontleedingangen en geen typeswitch**, want het verschil
  is niet cosmetisch: `path=` laat de motor het bestand zelf openen en streamend lezen,
  terwijl dezelfde waarde als `input` de *padtekst* als Turtle zou ontleden. Eén functie
  met `isinstance(bron, Path)` liet een `str`-pad in de inhoudstak vallen, en omdat
  `lees_orox` vóór deze module altijd `path=bron` doorgaf (waar pyoxigraph ook een `str`
  accepteert) zou dat een stille versmalling van een bevroren functie zijn geweest —
  gevonden door beide review-assen, hersteld vóór de commit, en bewaakt door
  `test_een_str_pad_leest_het_bestand_en_niet_de_padtekst`. De adapter is verder een
  doorgeefluik: hij vangt niets af, dus `OSError`, de
  syntaxfout van de motor en een fout uit een luie quadstroom komen er onveranderd uit
  en `bestand._parse`, `schrijven._gecontroleerd` en `schrijf_orox_quads` houden hun
  eigen, contractvaste `DatasetError`-teksten. De **term-fabrieken** (`NamedNode`,
  `BlankNode`, `Literal`, `Quad`, `Triple`) gaan er met opzet *niet* doorheen: die staan
  op tientallen plekken in `clip/` en `graaf`, zijn sinds 0.3 ongewijzigd, en een wrapper
  eromheen zou een laag zonder werk zijn. Nieuw is verder een **versiepoort**: draait de
  package op een pyoxigraph buiten `>=0.5,<0.6`, dan valt bij het importeren van
  `rdfmotor` één leesbare `DatasetError` ("pyoxigraph 0.6.0 valt buiten de reeks
  >=0.5,<0.6 ... installeer een pyoxigraph binnen de reeks") in plaats van een rauwe
  `TypeError` diep in de quadstroom. Die poort staat *naast* de cap in `pyproject.toml`
  en niet in plaats daarvan — de cap voorkomt de installatie, de poort vangt een
  omzeilde cap (`pip install --no-deps`, conda, een handmatige upgrade) — en
  `test_de_reeks_is_dezelfde_als_de_cap_in_pyproject` knoopt de twee aan elkaar zodat ze
  niet uit elkaar lopen. Bij import en niet per aanroep, omdat de fout aan de aanroepkant
  in de `except Exception` van `bestand._parse` zou belanden en er als "geen geldige
  Turtle" uit zou komen. Gevolg voor de auteur om te weten: `import gwsw_orox_helpers` kan
  daardoor met een `DatasetError` falen in plaats van te slagen — alleen op een pyoxigraph
  buiten de reeks, waar het alternatief een rauwe `TypeError` bij de eerste quad is.
  `rdfmotor` staat in `cache.LADERMODULES` (de lezing gaat
  erlangs), dus **de cachesleutel verschuift** en bestaande caches worden één keer
  opnieuw opgebouwd; dat is de bedoelde werking van die sleutel en geen
  gedragswijziging. Dat de schrijfweg dezelfde module deelt, betekent dat een wijziging
  aan alléén `serialiseer_turtle` de leescache mee ongeldig maakt: te vaak herbouwen kost
  één lezing, te weinig herbouwen geeft stil een verouderd antwoord. **Gedragsbehoud gepaard gemeten** op `tests/fixtures/ttl/
  juinen_voorbeeld_v1_6.ttl` (f58a5b2 in een aparte worktree tegen HEAD, zelfde invoer):
  de twee clipdelen en de hereniging zijn **byte-identiek**
  (`3e49228d…`, `ee3e55a6…`, merge `b2b682c0…`), en `schrijf_orox` levert dezelfde
  1.621 triples met dezelfde genormaliseerde quadstroom (`cf0e8f3c…`; de kále bytes van
  `schrijf_orox` verschillen ook op f58a5b2 van run tot run, want pyoxigraph mint per
  lezing nieuwe labels voor blanke knopen — de knip niet, die geeft ze vaste namen).
  Daarnaast `uv run pytest -m zwaar` groen (2 passed, 337,95 s) op de 112 MB-export.
  Geen perfbelofte, en gemeten is er ook geen meetbaar verschil: `scripts/benchmark.py
  --paden load_dataset --herhalingen 1`, zes keer **om en om** (f58a5b2, HEAD, f58a5b2,
  …) op de export van De Wolden/Hoogeveen gaf vóór 21,278 / 27,669 / 21,414 s en ná
  21,884 / 21,778 / 21,039 s — mediaan 21,41 → 21,78 s (+1,7%), minimum 21,28 → 21,04 s
  (−1,1%). De spreiding bínnen de vóór-kant (21,3–27,7 s) is een orde groter dan het
  verschil ertussen, dus dit is ruis en geen effect; dat past bij wat de wijziging is —
  één extra Python-aanroep per bestand, niet per quad. Geheugen gelijk (piek 1.248.676
  KiB vóór tegen 1.248.180 KiB ná) en de lezing levert aan beide kanten dezelfde
  1.877.729 triples, 23.485 knopen, 23.440 strengen en 0 geometriefouten.
- De leeslaag leest een GML-literaal nog één keer in plaats van twee (issue #13,
  performance; geen gedragswijziging). `inlezen._geometry` riep per geometrie zowel
  `parse_gml` als `parse_gml_z` aan, en die twee liepen elk hun eigen regex en
  float-conversie over dezelfde tekst: twee volledige lezingen op de vorm die een
  GWSW-export schrijft (`srsDimension` aanwezig) en tot vijf op een `gml:pos` zonder
  `srsDimension`. **Nieuw in `geometry`, additief**:
  `parse_gml_met_z(literal) -> tuple[Point | LineString | Polygon, list[float | None]]`,
  dat beide antwoorden uit één gang geeft; `inlezen._geometry` gebruikt die nu.
  `parse_gml`, `parse_gml_z`, `is_multipart_literal`, `COORDINATEN_PATROON` en
  `GeometryError` zijn onaangeraakt -- de knip en nlriochecker roepen ze rechtstreeks
  aan en hun handtekening, retourvorm en foutmeldingen staan gepind. Wat er intern wél
  veranderde is dat de drie lezers hun stappen delen (`_kind`, `_values`,
  `_dimensie_van`, `_tupels`, `_bouw`), zodat de dimensieregel en de
  `ShapelyError`-vangst niet in twee exemplaren kunnen gaan uiteenlopen.
  Gelijkwaardigheid **gepaard** getoetst over 23 literalen, geslaagde én mislukte:
  dezelfde geometrie, dezelfde z-lijst en dezelfde `GeometryError`-melding
  (`test_parse_gml_met_z_is_gelijkwaardig_aan_de_twee_losse_lezers`), plus een nieuwe
  test dat een onleesbare literaal nog steeds in `GwswDataset.geometry_errors` belandt
  zonder de lezing af te breken, en dezelfde vergelijking op de **69.288
  `geo:gmlLiteral`-teksten van de De Wolden/Hoogeveen-export**: nul afwijkingen, op de
  geometrie, de z-lijst én de foutmelding. **Gemeten, gepaard** (oud en nieuw om en om
  in hetzelfde proces op diezelfde 69.288 literalen, `scripts/benchmark_gml.py`,
  5 herhalingen): de literaalparsing gaat van 1,650 s naar 1,298 s gemiddeld (-21,4%),
  van 1,609 s naar 1,291 s op de mediaan (-19,8%) en van 1,446 s naar 1,164 s op het
  minimum (-19,5%); de nieuwe weg won alle vijf herhalingen. Dat is circa **4,1 µs
  minder per literaal**. Op het hele laadpad valt dat weg in de ruis, en dat hoort
  eerlijk opgeschreven: `inlezen._geometry` leest circa 47.000 literalen per export, dus
  de winst is daar ~0,2 s op een `load_dataset` van circa 22 s (~1%), terwijl de
  run-op-run-spreiding van `scripts/benchmark.py` op deze machine groter is (3x voor
  22,14 / 21,87 / 22,37 s tegen 3x na 21,10 / 28,87 / 20,27 s -- mediaan 22,14 → 21,10 s,
  het gemiddelde vertekend door één uitschieter). Het geheugen blijft gelijk: piek
  1.248.668 KiB vóór tegen 1.248.376 KiB ná (-0,02%), en de lezing levert aan beide
  kanten dezelfde 1.877.729 triples, 23.485 knopen, 23.440 strengen en 0
  geometriefouten. De winst is dus reëel maar klein; wat hier vooral verandert is dat de
  literaal nog maar op één plek gelezen wordt. `geometry` en `inlezen` staan allebei in
  `cache.LADERMODULES`, dus **de cachesleutel verschuift** en bestaande caches worden
  één keer opnieuw opgebouwd; dat is de bedoelde werking van die sleutel en geen
  gedragswijziging. Nieuw meetscript `scripts/benchmark_gml.py` (naast
  `scripts/benchmark_is_a.py`) dat de literaalparsing geïsoleerd en gepaard meet.
- De coordinaat-tekstchirurgie woont nu één keer, in `geometry` (issue #17, modulariteit;
  geen gedragswijziging op een leesbare GML-literaal -- zie de uitzondering onderaan deze
  regel). `clip` droeg een eigen coordinaat-regex (`clip.knip._COORDINATEN`)
  naast `geometry.COORDINATEN_PATROON` en leidde de verhouding tussen tokens en punten twee
  keer af -- in `knip._knip_lijn` en in `merge._stapgrootte`. Dat is precies het
  tweede-exemplaar-patroon dat `docs/architectuur.md` verbiedt: geen live bug, maar wel de
  plek waar een GML-vormvariant een stille byte-afwijking in `merge(clip(bron))` kon worden.
  **Nieuw in `geometry`, additief**: `coordinaattokens(literal) -> list[str]` (de getallen
  van de eerste `gml:pos`/`gml:posList` als brontekst, ongeoordeeld: geen lijst levert een
  lege lijst en geen fout), `vervang_coordinaten(literal, coordinaten) -> str` (dezelfde
  literaal met een andere lijst erin; srsName, srsDimension en soort blijven letterlijk
  staan) en `tokens_per_punt(literal, punten) -> int | None`. Die laatste draagt de
  **opzettelijke round-trip-keuze**: het aantal getallen per punt volgt uit de telling en
  níet uit de `srsDimension`, zodat de knip en zijn omkering bij een literaal zonder (of met
  een onjuiste) srsDimension hetzelfde raden en de hereniging niet op de verkeerde plaats
  snoeit. `clip.knip`, `clip.stroom` en `clip.merge` gebruiken die drie nu; `_COORDINATEN`,
  `_tokens`, `_ruwe_coordinaten` en `_met_coordinaten` zijn uit `clip.knip` verdwenen en
  `clip.merge` importeert daardoor niets meer uit `clip.knip` (de pijl `merge -> knip` is
  weg; `stroom` ziet nu wel `geometry`). Geen bestaande handtekening, retourvorm of
  foutmelding aangeraakt -- `COORDINATEN_PATROON`, `parse_gml`, `parse_gml_z` en
  `is_multipart_literal` staan er onveranderd, en de melding van `_stapgrootte` is tot op
  het getal dezelfde. Gedragsbehoud **gepaard** gemeten (zelfde invoer, vóór en ná in
  dezelfde run): clip + merge op de Juinen-fixture en op `mini_orox.ttl` leveren
  **byte-identieke** bestanden op, gelijke SHA-256 voor beide delen en voor de hereniging
  (Juinen-West `3e49228d…`, Juinen-Oost `ee3e55a6…`, terug `b2b682c0…`). De zware De
  Wolden/Hoogeveen-round-trip (112 MB) staat er ook onder: 1.877.729 triples in en uit,
  vingerafdruk gelijk, 650.470 objecten en 74 GWSW-klassen aan beide kanten, 13
  grenskruisende leidingen, 102.704.657 bytes tegen 102.704.657 (1,000x). **De ene
  uitzondering**, en de prijs van het ontdubbelen: de oude clip-regex eiste een `\b` achter
  `pos`/`posList` en de gedeelde `COORDINATEN_PATROON` doet dat niet, dus een literaal met
  een misvormde openingstag (`<gml:posz>…</gml:pos>`) las de knip vroeger *niet* terwijl
  `parse_gml` hem wel las. Die literaal ging toen heel door de knip en gaf in
  `_stapgrootte` stap 0 (de hereniging snoeide dan niets); nu lezen beide kanten dezelfde
  lijst en komt de verhouding wel rond. Zulke literalen komen niet uit een GWSW-export en
  niet uit de clip zelf -- alleen eventueel uit een deel van elders -- en de nieuwe uitkomst
  is de veiligere, maar het is gedrag en het staat hier daarom opgeschreven
  (`test_de_tekstkant_leest_dezelfde_lijst_als_de_lezerskant`). In dezelfde categorie
  onbereikbaar-maar-anders: `_stapgrootte` werpt bij nul tokens op één of meer punten nu
  een `DatasetError` in plaats van stil stap 0 terug te geven -- een leesbare literaal kan
  die stand niet bereiken, want zonder tokens faalt `parse_gml` en zijn er geen punten.
  **Let op:** `geometry` staat in
  `cache.LADERMODULES`, dus deze wijziging verzet de cachesleutel -- bestaande caches worden
  één keer opnieuw opgebouwd. Dat is de bedoelde werking van die sleutel en geen
  gedragswijziging.
- `clip.py` is een `clip/`-package geworden (issue #11, modulariteit; geen
  gedragswijziging). Het bestand was met 1299 regels bijna 29% van de package en droeg vijf
  bannerblok-hoofdstukken achter elkaar; dat is nu zeven submodules van 56 tot 320 regels,
  met een importrichting die niet terug kan wijzen: `termen` en `grenzen` zijn bladeren,
  daarboven `knip` (geometrie plaatsen en doorknippen, `_Stuk`), `plan` (de analyseronde,
  `_Plan`), `stroom` (de gefilterde quadstroom per deel), `merge` (de delen weer aaneen) en
  `orkest` (`clip_orox`, `merge_orox`). Het `__init__.py` is dun: het draagt de docstring
  van 135 regels die het verhaal vertelt, en her-exporteert de twee ingangen. **Voor een
  afnemer verandert er niets** -- `from gwsw_orox_helpers.clip import clip_orox,
  merge_orox` en `gwsw_orox_helpers.clip_orox` doen wat ze deden, en geen enkele
  handtekening, retourvorm of foutmelding is aangeraakt. Alleen verplaatst: geen functie
  herschreven. Bewaakt door drie tests in `tests/test_publieke_api.py` --
  `test_cliplaag_is_additief` (nu per submodule in plaats van alleen aan het oppervlak),
  `test_de_clipsnit_ligt_vast` en `test_de_clipsubmodules_houden_de_importrichting`, die
  aan de import-AST toetst dat een fase alleen `errors`/`geometry`/`namen`/`schrijven` en
  zusters *boven* zich importeert -- aan de boom en niet aan een regex op regelbegin, want
  een ingesprongen import in een functie, `from gwsw_orox_helpers import dataset` en
  `import gwsw_orox_helpers.graaf` zijn alle drie manieren om de leeslaag alsnog binnen te
  halen. Gedragsbehoud gemeten met de Juinen-round-trip (in CI)
  en eenmalig met de zware De Wolden/Hoogeveen-round-trip (112 MB): 1.877.729 triples in
  en uit, vingerafdruk gelijk, 650.470 objecten en 74 GWSW-klassen aan beide kanten, 13
  grenskruisende leidingen, 102.704.657 bytes tegen 102.704.657 (1,000x). Sterker nog:
  dezelfde knip op de Juinen-fixture levert vóór en ná de hersnit **byte-identieke**
  bestanden op -- gelijke SHA-256 voor beide delen en voor de hereniging. De hersnit
  verzet de cachesleutel niet (`clip` staat niet in `cache.LADERMODULES`).
- Het warmste predicaat van de checkfase is circa 40% sneller (issue #12, performance;
  `dataset.py`, `klassen.py`). `GwswDataset.is_a` wordt via `klim_naar_knoop` en
  `of_class` ruim een miljoen keer per nlriochecker-run gesteld en bouwde per aanroep een
  verse types-unie (`node.types | node.orientation_types`), terwijl `klassen._afsluiting`
  op élke aanroep ook zijn terugval opbouwde -- een `dict.get`-default is een gewoon
  argument, dus `subclasses.get(_uri(w), frozenset({_uri(w)}))` maakte die wegwerp-set en
  die tweede `_uri`-aanroep ook op de treffer. `types_of` krijgt nu een `_types_memo`
  volgens exact het patroon van `_resolved_nodes` (`init=False`, dus elke
  `replace()`-afgeleide -- `subset`, `markeer_vulwaarden`, het cachepad -- begint met een
  lege memo, en `cache._schrijf` houdt het veld buiten de pickle), en `_afsluiting` bouwt
  frozenset en tweede `_uri`-aanroep alleen nog op de miss-tak. Gemeten op De Wolden en
  Hoogeveen (112 MB, 23.485 knopen en 23.440 strengen) met het nieuwe
  `scripts/benchmark_is_a.py`, dat de checkfase-lus nabootst met 24 GWSW-wortels en zo op
  1.126.200 `is_a`-aanroepen per ronde komt: de hele lus (`of_class` per wortel plus die
  `is_a`-aanroepen) gaat van **2,26 s naar 1,32 s op het minimum van drie rondes (-42%)**,
  met dezelfde 266.650 treffers vóór en ná. Vier procesmetingen in beide volgordes (oud,
  nieuw, nieuw, oud) gaven 2,26 / 1,52 / 1,32 / 2,32 s als minimum -- de machine was
  onrustig, dus de spreiding binnen elke kant is aanzienlijk; een eenmalige controle die
  de oude en de nieuwe implementatie in hetzelfde proces op dezelfde geladen dataset
  afwisselde, waar die ruis niet in past, gaf -38% (2,15 -> 1,33 s). De winst ligt dus
  rond de 38 tot 42%: incrementeel, geen orde van grootte. De procespiek blijft 1219 MiB,
  maar dat is een ondergrens en geen meting van de ruil -- die piek zet de lader.
  Signaturen en retourwaarden van
  `is_a`, `types_of`, `graph_types_of`, `closure` en `of_class` zijn ongewijzigd: zuiver
  additief, `tests/test_publieke_api.py` blijft groen.
- Schrijflaag veiliger tijdelijk bestand (issue #15, security; `schrijven.py`).
  `schrijf_orox_quads` schreef naar de voorspelbare naam `<doel>.tmp` met een gewone
  `open('wb')`. Dat volgt een symlink (CWE-59/377): een vooraf geplante `uit.ttl.tmp` in
  een gedeelde uitmap werd doorgeschreven naar waar hij heen wees — gemeten vóór de
  wijziging kreeg het slachtofferbestand de volledige export, ná de wijziging blijft het
  byte-voor-byte ongemoeid (`test_geplante_tijdelijke_symlink_wordt_niet_doorheen_geschreven`,
  rood vóór en groen ná de fix). Twee gelijktijdige runs naar hetzelfde doel botsten
  bovendien op diezelfde ene naam. Het tijdelijke bestand krijgt nu een unieke naam in de
  doelmap — doelnaam, proces-ID en een willekeurig deel — en wordt aangemaakt met
  `open(..., "xb")` (`O_CREAT | O_EXCL`, mode `0o666`): `O_EXCL` weigert een bestaande naam
  en volgt dus geen symlink, en de kernel past `0o666 & ~umask` toe. De rechten van de
  geschreven export blijven daarmee precies wat een `open('wb')` gaf (gemeten op deze
  machine `0664`, gelijk aan een referentiebestand in dezelfde map); een nieuwe test pint
  dat aan dat referentiebestand in plaats van aan een vast getal, want de umask verschilt
  per machine. Dat wijkt bewust af van `cache._schrijf_atomair`, dat `tempfile.mkstemp`
  (mode `0600`) gebruikt: de cache schrijft privé pickles in `~/.cache`, de schrijflaag
  levert een bestand af in andermans uitmap en mag de rechten van de gebruiker niet
  verstrengen. Signatuur, retourvorm, rechten en de atomariteitsbelofte (`os.replace` na
  de laatste quad, tmp opgeruimd bij een fout) zijn ongewijzigd — de wijziging is zuiver
  additief; `tests/test_publieke_api.py` blijft groen.
- Afhankelijkheden krijgen een bovengrens (issue #14; `pyproject.toml`, geen
  `src`-wijziging): `pyoxigraph>=0.5,<0.6`, `rdflib>=7.0,<8`, `shapely>=2.0,<3`. Reden:
  `graaf._literal_string_snel` zet vier rdflib-interne velden (`_language`, `_datatype`,
  `_value`, `_ill_typed`) rechtstreeks en is daarmee aan 7.x gebonden, en pyoxigraph is
  pre-1.0 waar 0.5 -> 0.6 de parse-signatuur mag breken; `shapely<3` is precautionair.
  Zonder bovengrens kon een verse install bij een afnemer stil een incompatibele versie
  trekken en op het parse-pad verkeerde termen opleveren — de drifttests draaien daar niet.
  De gepinde omgeving verandert niet (pyoxigraph 0.5.9, rdflib 7.6.0, shapely 2.1.2); in
  `uv.lock` wijzigt alleen de requirement-metadata van het package zelf, geen enkele
  versie. **Release-hygiëne voor nlriochecker**: bij de volgende release van deze package
  moet daar `uv lock` draaien om de nieuwe grenzen over te nemen — het is geen
  contractbreuk, de publieke API blijft ongewijzigd.
- Tests (issue #10, additief; geen `src`-wijziging): het publieke GWSW-Voorbeeld van
  Stichting RIONED staat nu byte-exact als fixture in de repo
  (`tests/fixtures/ttl/juinen_voorbeeld_v1_6.ttl`, 119.332 bytes, 1.621 triples, 567
  objecten in 116 GWSW-klassen). Daarmee vervalt de `skipif` op
  `test_juinen_round_trip_is_isomorf` en `test_juinen_kent_grenskruisende_leidingen`:
  de verliesloze knip-en-hereniging wordt voortaan ook in CI op een échte export bewezen
  en niet alleen op de synthetische 79-triple-fixture. Gemeten op een machine zonder de
  externe export ging `uv run pytest -q` van 345 passed / 3 skipped naar 347 passed /
  1 skipped (de overgebleven skip is de Juinen-test in `tests/test_schrijven.py`, die nog
  naar het pad buiten de repo wijst); de looptijd van de snelle poort loopt daarmee op van
  12,6 s naar 25,8 s, vrijwel geheel de canonicalisatie van `rdflib.compare.isomorphic`
  over 1.621 triples met 1.347 blanke-knoopposities. De fixture draagt geen `zwaar`-marker
  en wordt niet door `scripts/maak_fixtures.py` gegenereerd; die docstring somt hem nu op
  als handwerk dat byte-exact moet blijven.
- Ontwikkelstraat: de multi-lens review-swarm (`.claude/workflows/orox-10x-swarm.js`) is nu
  een **verplichte release-poort** — vóór elke versie draaien en de bevindingen wegen
  (overnemen niet verplicht), zie `CLAUDE.md`, Werkwijze. De additieve bevindingen van de
  eerste run staan als `ready-for-agent`-issues (#10–#31); de contract-rakers zijn bewust
  buiten scope gelaten als auteursbeslissing.

## [0.2.0] - 2026-08-30
- README herschreven als landingspagina met vaste opbouw (badges, Stand van zaken, Wat je
  krijgt, Snel proberen, Verder lezen, Ontwikkelen, Bijdragen, Licentie), naar het model
  van nlriochecker. Zelfde inhoud, geen apparatuur eromheen (geen getrackt voorbeeld,
  rooktest of schermafdrukken): de bibliotheek heeft al een runbaar voorbeeld en
  `docs/architectuur.md`.
- Leesweg sneller (intern; geen API-wijziging, gedrag bevroren; issue #7): twee losse
  stappen die elkaar niet raken. De cyclische GC ligt nu stil over het hele leesblok van
  `load_dataset` -- beide parses, de klassenafleiding en de objectopbouw van
  `_read_nodes`/`_read_conduits` -- en niet meer alleen om het vullen van de grafindex
  heen; `inlezen._gc_uit` wordt daarvoor vanuit `dataset` aangeroepen en zet de oude stand
  in een `finally` terug, ook na een fout. Dat verbreedt wat de regel hieronder over
  `_gc_uit` zegt: `_parse` blijft de enige weg naar `GraafIndex.vul_uit`, maar
  `load_dataset` is er nu de buitenste aanroeper omheen, en die zegt het procesbrede
  neveneffect in haar eigen docstring toe. Daarnaast krijgen de twee dominante termvormen
  in `graaf.naar_rdflib` een kort pad (`_uriref_snel`, `_literal_string_snel`) dat rdflib's
  IRI-validatie en literaalconstructor overslaat zonder een ander object op te leveren; de
  taal-literaal, elk ander datatype en de `BNode` blijven op de generieke weg.
  Gemeten op de 112 MB-export van De Wolden en Hoogeveen met
  `scripts/benchmark.py --paden load_dataset`, gepaard (n=4, referentie en experiment om
  en om): mediaan 27,65 -> 25,46 s (-7,9%, de verhouding van de twee medianen), en alle
  vier de rondes wezen dezelfde kant op (per paar 9,7%, 5,4%, 8,3% en 20,2% sneller).
  Piekgeheugen ongewijzigd op 1218 MiB. De tellingen
  zijn exact gelijk gebleven: 1.877.729 triples, 23.485 knopen, 23.440 strengen, 0
  geometriefouten; `schrijf_orox`, `clip_orox` en `merge_orox` zijn niet aangeraakt.
  `_literal_string_snel` zet vier rdflib-interne velden rechtstreeks -- er is geen publieke
  weg om een literaal zonder de constructor te bouwen -- en de snelpad-tests in
  `tests/test_graaf.py` zijn de enige bewaker daarvoor bij een rdflib-upgrade. Wat wegvalt
  is rdflib's `logger.warning` bij een vreemd ogende IRI; op de leesweg was die al gedempt,
  maar wie `GraafIndex.vul_uit` rechtstreeks aanroept ziet hem voortaan ook niet. `graaf`
  en `dataset` staan in `cache.LADERMODULES`, dus bestaande caches worden een keer opnieuw
  opgebouwd -- bedoeld, geen gedragswijziging.
- Performanceronde (intern; geen API-wijziging, gedrag bevroren): de vier hete paden zijn
  op de 112 MB-export van De Wolden en Hoogeveen gemeten met `scripts/benchmark.py` en
  daarna alleen bijgesteld waar het profiel dat aanwees. `load_dataset` gaat van 27,3 naar
  20,7 s (-24%), `merge_orox` van 20,9 naar 18,2 s (-13%) en `clip_orox` van 42,0 naar
  39,1 s (-7%); `schrijf_orox` blijft op 6,9 s en het geheugen blijft gelijk. Wat er
  veranderde: het verslag van de UTF-8-terugval zoekt zijn voorbeeldregels met een
  bytepatroon in plaats van met een Python-lus over alle 112 MB
  (`codering._fallback_samples`, 4,8 -> 0,5 s); de cyclische GC ligt stil terwijl de
  grafindex zich vult, waar hij anders bij elke paar duizend nieuwe dicts opnieuw door
  miljoenen containers loopt (`inlezen._gc_uit` om `_parse` heen -- de enige productieweg
  naar `GraafIndex.vul_uit`, zodat die publieke methode van dat procesbrede neveneffect
  vrij blijft); `RDF.type` en `RDFS.label` worden een keer opgevraagd in plaats van bijna
  negenhonderdduizend keer (`inlezen`, want op rdflib's `DefinedNamespace` is dat geen
  attribuut maar een `__getattr__` van bijna een microseconde); de schrijfronde van de
  clip slaat per quad de omweg over `_Plan.blok`,
  de tuple van randpredicaten, de sleutelfunctie per term en de GML-vraag over
  (`clip._deelstroom`, `clip._genummerd`); en de hereniging bouwt de term van een subject
  niet meer uit zijn eigen tekst opnieuw op (`clip._samengevoegd`, `clip._scan_delen`).
  Geen nieuwe afhankelijkheden, geen C-extensies. De tellingen van de `zwaar`-tests zijn
  ongewijzigd: 1.877.729 triples, 74 klassen, 650.470 objecten, dezelfde vingerafdruk en
  dezelfde bestandsgrootte.
- Architectuurronde (intern; geen API-wijziging): de leeslaag is uit `dataset.py` in vier
  modules gesneden -- `domein` (de waardeobjecten), `inlezen` (alles wat de graaf aanraakt,
  inclusief het parsen), `klassen` (de subklasse-afsluiting en wat eruit volgt) en
  `codering` (UTF-8 met terugval) -- en de IRI's van alle drie de lagen staan nu één keer,
  in `namen`. Daarmee verdwijnen drie plekken waar kennis dubbel stond: de `gwsw:`-basis
  (leeslaag, schrijflaag, cliplaag), de UTF-8-terugval (`dataset._decode` naast
  `schrijven._gedecodeerd`) en de kringverwijzing tussen `dataset` en `ontologie`, die met
  functie-lokale imports werd omzeild. `dataset` blijft het gezicht van de leeslaag: elke
  naam die nlriochecker importeert komt daar naar buiten, met identieke handtekening en
  identiek gedrag (`tests/test_publieke_api.py` blijft groen). `dataset` draagt daarvoor
  nu een expliciete `__all__` met dat hele oppervlak, inclusief de namen die bij de
  hersnit naar een andere module verhuisden maar uit `dataset` importeerbaar blijven:
  `parse_gml`, `parse_gml_z`, `is_multipart_literal` en `GeometryError` (uit `geometry`)
  en `ISO_DATUM` en `JAARTAL` (uit `domein`). De cachesleutel hasht nu de broncode van
  alle leeslaagmodules (`cache.LADERMODULES`), dus bestaande caches worden
  één keer opnieuw opgebouwd. De gekozen snit staat in `docs/architectuur.md`.
- Cliplaag: `gwsw_orox_helpers.clip` met `clip_orox` (een OroX-export langs een
  GeoJSON-grenslaag van N vlakken in N OroX-bestanden knippen) en `merge_orox` (die
  delen weer tot het origineel samenvoegen). `merge(clip(bron))` is isomorf aan `bron`:
  knopen gaan naar het vlak waarin ze liggen, een leiding die de grens kruist wordt
  doorgeknipt en per herkomst weer aaneen genaaid, gedeelde structuur staat in elk deel
  dat een afstammeling bevat en wordt bij de hereniging op inhoud ontdubbeld. De
  geknipte stukken worden uit de *tekst* van de bron gesneden, zodat het snoeien van het
  knippunt letterlijk de oorspronkelijke coordinaten teruggeeft; welk punt ingevoegd was
  staat in de knipmerken (`knip:`-naamruimte) en hoeft niet aan zijn collineariteit
  herkend te worden. Eigen pad naast de leeslaag, net als `schrijven`: geen import van
  `dataset` of `graaf`. Additief; `tests/test_publieke_api.py` blijft groen.
  `clip_orox` en `merge_orox` zijn ook rechtstreeks uit `gwsw_orox_helpers` te
  importeren, net als de schrijflaag.
  Wat de afnemer per deel extra krijgt: het merk `knip:geknipt` op de houder van een
  geknipte geometrie. `merge_orox` leest het niet -- het gaat met de hele
  `knip:`-naamruimte weg -- maar wie een deel op zichzelf leest, ziet er een leiding met
  een geometrie die korter is dan haar lengtekenmerk en die niet in haar eindpunten
  aankomt; het merk zegt dat dat de knip is en geen fout in de data. Kruist een leiding
  de grens heen en weer, dan draagt een deel meer dan een stuk van dezelfde lijn: dat is
  een meerdelige geometrie en `load_dataset` meldt hem als zodanig (`Conduit.multipart`).
- Schrijflaag: `gwsw_orox_helpers.schrijven` met `schrijf_orox` (bestand naar bestand),
  `lees_orox` (quadstroom plus bronprefixen) en `schrijf_orox_quads` (een al geparseerde
  stroom wegschrijven, de ingang voor de clip). Regenererende serializer met een eigen
  pad naast `load_dataset`: niet byte-gelijk aan de bron, wel graaf-gelijk. Schrijft via
  een tmp naast het doel en hernoemt pas bij succes, zodat een fout halverwege geen
  afgekapte export achterlaat. Additief; `tests/test_publieke_api.py` pint het oppervlak
  dat nlriochecker importeert.
- Agent-regie-infrastructuur overgenomen uit nlriochecker (docs/agents,
  CLAUDE.md-werkwijze).

## [0.1.0] - 2026-08-26
- Leeslaag overgenomen uit nlriochecker: OroX-TTL naar domeinmodel, grafindex,
  GML-geometrie, ontologiefacetten, cache en voortgangsprotocol.
- GWSW-ontologie 1.6 en vocabulaire-index gebundeld als package-resources
  (`bronnen.gebundelde_ontologie`, `bronnen.vocabulaire_index_pad`). `load_dataset`
  en `laad_met_cache` lezen zonder opgave die ontologie; een lege lijst betekent
  expliciet geen ontologie.
