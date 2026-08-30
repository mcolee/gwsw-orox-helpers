# Changelog

## [Unreleased]
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
