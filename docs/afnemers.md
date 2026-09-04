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
