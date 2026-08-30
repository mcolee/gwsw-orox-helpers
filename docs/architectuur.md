# Architectuur van gwsw-orox-helpers

De package doet drie dingen met een GWSW-OroX-TTL: hem **lezen** tot een toetsbaar
domeinmodel (`load_dataset`), hem **terugschrijven** (`schrijf_orox`) en hem ruimtelijk
**verdelen en herenigen** (`clip_orox` / `merge_orox`). Die drie zijn in drie fasen
gegroeid en hebben elk een eigen pad door pyoxigraph. Dit document zegt welke lagen er
zijn, wie wat importeert, en waar de kennis woont die meer dan één laag nodig heeft.

## De lagen

Wie wat importeert, binnen de package. `A -> B` betekent "A importeert B"; elke pijl
wijst naar een regel *boven* zich en nooit andersom. Na te lopen met
`grep -n "^from gwsw_orox_helpers" src/gwsw_orox_helpers/*.py` -- dit zijn alle randen
die er zijn.

```
errors   voortgang   bronnen   namen   geometry   domein    <- bladeren: geen import
                                                               binnen de package

graaf      -> namen
codering   -> errors
ontologie  -> graaf, namen
klassen    -> graaf, namen, ontologie
inlezen    -> codering, domein, errors, geometry, graaf, klassen, namen
dataset    -> bronnen, codering, domein, errors, geometry, graaf, inlezen, klassen,
              namen, voortgang
cache      -> codering, dataset, domein, geometry, graaf, inlezen, klassen, namen,
              ontologie, voortgang

schrijven  -> codering, errors, namen
clip       -> errors, geometry, namen, schrijven
__init__   -> clip, schrijven
```

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
| `geometry` | Wat staat er in een GML-literaal? (shapely; z apart van xy) |
| `graaf` | Hoe vraag je een graaf iets? (`GraafIndex`: twee dicts, rdflib-termen) |
| `codering` | Hoe worden de bytes van een TTL tekst? (UTF-8 met terugval) |
| `ontologie` | Wat zegt een `owl:Restriction` over een klasse of kenmerk? |
| `klassen` | Wat volgt daaruit? (subklasse-afsluiting, `kenmerk_property`, functies) |
| `domein` | Wat *is* een knoop of streng? (waardeobjecten, zonder graaf) |
| `inlezen` | Hoe vul je die objecten uit een graaf? (parsen, hasPart/hasAspect, lezers) |
| `dataset` | Wat kun je een ingelezen dataset vragen? (`GwswDataset`, `load_dataset`) |
| `cache` | Hoe sla je die lezing over? (pickle, sleutel op inhoud én broncode) |
| `schrijven` | Hoe komt een quadstroom er als OroX-Turtle weer uit? |
| `clip` | Hoe verdeel je die stroom over vlakken, en hoe draai je dat terug? |

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
| De IRI's: `GWSW` en de naamruimten, `hasAspect`/`hasPart`/`hasConnection`, `geo:gmlLiteral` | `namen` (tekst) | `inlezen` (als `URIRef`), `clip` (als `NamedNode`), `schrijven` (prefixkop), `graaf` (`xsd:string`), `ontologie`, `klassen` (`GWSW`, voor de korte namen), `dataset` (`GWSW`, en het exporteert hem) |
| De prefixkop van een OroX-export | `schrijven.STANDAARD_PREFIXEN`, opgebouwd uit `namen` | `schrijven`, `clip` (krijgt ze via `lees_orox` en vult `knip:` aan) |
| UTF-8 met terugvalcodering, inclusief beide foutmeldingen | `codering.decodeer` | `inlezen._decode`, `schrijven._gedecodeerd` |
| Het verslag van zo'n terugval (`DecodeFallback`) | `codering.terugvalverslag` | alleen `inlezen` |
| De GML-lezers | `geometry` | `inlezen`, `clip`, `dataset` (doorgeefluik) |

Dat laatste onderscheid is opzettelijk: het verslag telt de afwijkende bytes en zoekt de
regels waarin ze staan, en dat is een tweede gang over het hele bestand. Een lezing wordt
gerapporteerd (`GwswDataset.decode_fallback`), een terugschrijving niet — dus betaalt de
schrijfweg er ook niet voor.

## Wat "additief" hier betekent

`schrijven` en `clip` staan naast de leeslaag en niet erop: ze bouwen geen domeinmodel en
importeren `dataset` noch `graaf`. `tests/test_publieke_api.py` bewaakt dat aan de
brontekst (`test_schrijflaag_is_additief`, `test_cliplaag_is_additief`). Ze delen wel de
bladeren onder de leeslaag: `namen` en `errors` allebei, `codering` alleen `schrijven` (de
UTF-8-terugval; `clip` ziet die enkel via `lees_orox`) en `geometry` alleen `clip` (de
GML-lezers, die de knip nodig heeft en de serializer niet). Modules die onder allebei
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
`domein`, `klassen`, `codering`, `namen`, `graaf`, `geometry` en `ontologie`. Dat is de
garantie dat een cache nooit achterloopt op een wijziging in de lezing. Wie de leeslaag
opnieuw indeelt, moet de nieuwe modules aan die lijst toevoegen: een vergeten module
levert geen fout op maar een cache die na een wijziging de oude lezing blijft teruggeven.
Twee tests in `tests/test_cache.py` houden dat bij: de ene parametriseert over
`LADERMODULES` en toont per module dat een gewijzigde broncode een andere sleutel geeft,
de andere eist dat elke module van de package óf in die lijst staat óf met een reden in
de uitzonderingsverzameling ernaast.

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
