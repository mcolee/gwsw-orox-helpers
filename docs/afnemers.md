# Afnemercontext van de publieke API

De publieke docstrings van deze package staan in **domeintaal**: ze zeggen wat een afnemer
met een naam kan, niet welke check of welk bestand van een afnemer hem aanroept. Een
PyPI-afnemer kan een interne checkcode of bestandsnaam van nlriochecker niet opzoeken, dus
die horen niet in `help()` thuis (issue #56).

De herkomst gaat daarmee niet verloren: dit bestand bewaart per publieke naam de
nlriochecker-context die vroeger in de docstrings stond — de checkcode en/of de aanroepende
module. nlriochecker is de eerste afnemer en de publieke API die het importeert is bevroren
(`CLAUDE.md`, Harde regels); deze tabel legt vast *waarom* elke naam er is, zonder die
interne artefacten in het publieke oppervlak te zetten.

De codes zijn die van het nlriochecker-checkregister; de bestands- en modulenamen
(`checks/…`, `uitvoer/…`, `nulbevinding`, `analysis.…`, `afbakening`) horen bij de
nlriochecker-repo, niet bij deze package.

## Per publieke naam

| Publieke naam | nlriochecker-context (checkcode / aanroeper) |
|---|---|
| `domein.Node.bovenkant` | `HGT-004`, `HGT-012`, `HGT-018` — hoogtechecks op de dekselhoogte (met maaiveld als terugval) |
| `dataset.GwswDataset.richting_van_geometrie` / `netwerk.richting_van_geometrie` | `TOP-020` (tekenrichting) en de kaartlaag met richtingspijlen; beide lezen dezelfde functie |
| `dataset.GwswDataset.is_a` | aangeroepen door `klim_naar_knoop` (intern) en `uitvoer/melding.py` (de meldingsweging op het knoop- of strengobject) |
| `dataset.GwswDataset.is_connection_class` | `analysis.bepaal_typeringspoort` leest klassenamen uit de CfkTypes_typ-regels van de SHACL-nulmeting en vraagt deze poort vooraf |
| `dataset.GwswDataset.subset` | `NET-007` en de RVZ-checks (randvoorzieningen); hun drempels lopen via `subjects_of_class()` nog over de volledige export |
| `dataset.markeer_vulwaarden` | `ATTR-013` (meldt de vulwaarde één keer) en de hoogtechecks (slaan het object over) |
| `ontologie.verwachte_property` | `ATTR-014` — ziet dat een export `hasValue` schrijft waar de ontologie `hasReference` eist; de SHACL-nulmeting mist die fout per constructie (issue #37) |
| `ontologie.functie_van_klasse` | `TOP-022`, `TOP-023` — het verwachte aantal leidingen van een hulpstuk (issue #60) |
| `netwerk.klim_naar_knoop` | de breedte-eerst-wandeling zoals `nulbevinding._Joiner`; de tweede uitkomst dient `afbakening` om schakels in de analyseset te houden |
| `graaf.GraafIndex` (leescontract van `GwswDataset.graph`) | externe aanroepers van het leescontract: `parts_of`/`aspects_of`/`part_holders_of`/`aspect_holders_of` ← `checks/netwerk.py`, `checks/randvoorzieningen.py`; `hasConnection` ← `checks/administratief.py`; `subjects` ← `checks/administratief.py`, `checks/attributen.py` (`_property_tellingen`), `nulbevinding.py`; `value` ← `checks/attributen.py` |

De moduledocstring van `graaf` noemt sinds issue #56 alleen nog de aanroepers **binnen** de
package (`dataset`, `inlezen`, `klassen`, `ontologie`, `cache`, `load_dataset`); de externe
aanroepers staan hier.

## De aanbevolen kern (issue #72)

Een check-schrijver hoort de namen hieronder te leren; ze zijn **versie-juist** (ze leiden hun
predicaten en klasse-IRI's af uit de gedetecteerde GWSW-basis van de bron) en geven tekst of
domeinobjecten terug in plaats van rdflib-termen. De kern telt **33 namen**:

| Groep | Namen |
|---|---|
| Laden | `load_dataset`, `cache.laad_met_cache`, `dataset.lees_ontologie` |
| Versie en spelling | `GwswDataset.gwsw_versie`, `GwswDataset.termen`, `GwswVersie`, `namen.klasse_iri`, `namen.korte_naam` |
| Waardeobjecten | `Node`, `Conduit`, `Aspect`, `Inwinning`, `Vulwaarde`, `Koppelingsherstel`, `DecodeFallback` |
| Versie-juiste graafvragen | `uris_of_class`, `buren`, `kenmerken_met_waarde`, `houders`, `dragers`, `kenmerkinstanties`, `knopen_van`, `strengen_van`, `knopen_van_streng`, `valt_onder`, `typen_kort` |
| Klassen en selectie | `closure`, `beheerobjecttype`, `is_connection_class`, `subset` |
| Netwerk | `resolve_network_node`, `klim_naar_knoop`, `richting_van_geometrie` |

### Te vermijden — gebruik de versie-juiste str-laag

De namen hieronder blijven byte-voor-byte bestaan (nlriochecker importeert ze en de publieke API
is bevroren), maar een nieuwe afnemer hoort ze **niet** meer te leren. Twee redenen, en ze
verschillen per rij: de geëxporteerde 1.6-constanten (`GWSW`, `HAS_*`, `KLASSE_*`) spellen letterlijk
1.6 en treffen op een 1.7-export stil nul zodra een afnemer er zelf mee bevraagt (`subjects(RDF.type,
URIRef(GWSW + kenmerk))`, `hasConnection`-buren via `HAS_CONNECTION`); de rdflib-typed methoden en
vrije functies (`subjects_of_class`, `of_class`, `part_holders_of`, `graph_types_of`, ...) leiden hun
IRI's wél uit de gedetecteerde basis af en lezen ook op 1.7 juist, maar geven rdflib-termen terug en
vragen bij elke selectie dezelfde omzetting naar `Node`/`Conduit` -- daar is de str-laag de
ergonomische vervanger, niet de correctie. Kies in beide gevallen de versie-juiste tegenhanger uit de
kern hierboven. (Dit is geen deprecatie of aangekondigde verwijdering — het is een aanbeveling; een
eventuele verwijdering is een aparte auteursbeslissing die niet gepland staat.)

| Te vermijden | Versie-juiste vervanger |
|---|---|
| `subjects_of_class` (rdflib-`Node`) | `uris_of_class` |
| `of_class` + `in dataset.nodes`/`.conduits` | `knopen_van` / `strengen_van` |
| `part_holders_of` (vrije functie) | `houders` |
| `aspect_holders_of` (vrije functie) | `dragers` |
| `parts_of`, `aspects_of` (vrije functies) | `onderdeel_aspecten`, `stelsel_leden` (en `buren` voor hasConnection) |
| `graph_types_of` | `typen_kort` |
| `graph_is_a` (lidmaatschapstest op één klasse) | `valt_onder` met één wortel, of `typen_kort(uri) & closure(...)` |
| `onderdelen` | (blijft nuttig; de gefilterde vorm leunt op `graph_is_a`) |
| `GWSW`, `HAS_ASPECT`, `HAS_PART`, `IS_ASPECT_OF`, `IS_PART_OF`, `HAS_CONNECTION`, `HAS_VALUE`, `HAS_REFERENCE` | de predicaten uit `GwswDataset.termen` (of de str-methoden die er al doorheen lezen) |
| `KLASSE_*` / `KLASSEN_*` (1.6-klasse-IRI's) | `namen.klasse_iri(naam, basis)` met `gwsw_versie.basis`, of de str-methoden die de klasse-IRI zelf opbouwen |

De `hasConnection`-buren en de kenmerkinstanties (het `subjects(RDF.type, URIRef(GWSW + kenmerk))`-
idioom) hebben met `buren` respectievelijk `kenmerkinstanties` een directe, versie-juiste vervanger.
