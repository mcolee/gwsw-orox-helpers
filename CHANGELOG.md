# Changelog

## [Unreleased]
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
