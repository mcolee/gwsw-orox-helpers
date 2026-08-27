# gwsw-orox-helpers

Python-bibliotheek voor GWSW-OroX-bestanden (Turtle): rioleringsdata volgens het
[Gegevenswoordenboek Stedelijk Water](https://data.gwsw.nl/).

- **Lezen** — `load_dataset` parseert een OroX-export naar een domeinmodel (putten,
  leidingen, aspecten, klassenhiërarchie) met GML-geometrie als shapely-objecten;
  `laad_met_cache` maakt herladen vrijwel gratis.
- **Schrijven** — `schrijf_orox` regenereert een export: niet byte-gelijk, wel
  graaf-gelijk (isomorf).
- **Knippen en samenvoegen** — `clip_orox` knipt een export langs een
  GeoJSON-grenslaag in N delen; `merge_orox` voegt die verliesloos terug tot een
  graaf die isomorf is aan de bron.

De GWSW-ontologie 1.6 is meegebundeld. Motoren: pyoxigraph, rdflib, shapely.
Eerste afnemer: [nlriochecker](https://github.com/mcolee/nlriochecker).

## Installatie

Python 3.12+.

```sh
uv add git+https://github.com/mcolee/gwsw-orox-helpers   # of: pip install git+...
```

## Gebruik

```python
from pathlib import Path
from gwsw_orox_helpers import clip_orox, merge_orox
from gwsw_orox_helpers.dataset import load_dataset

ds = load_dataset(Path("gemeente_orox.ttl"))  # met de gebundelde GWSW-ontologie 1.6
print(len(ds.nodes), "putten,", len(ds.conduits), "leidingen")

delen = clip_orox(Path("gemeente_orox.ttl"), Path("grenzen.geojson"),
                  Path("delen/"), sleutel="gemeentenaam")
merge_orox(delen, Path("terug.ttl"))  # isomorf aan de bron
```

Schaal: een export van 112 MB (1,9 mln triples) laadt in ~20 s en knipt in ~39 s.

## Status en licentie

Pre-1.0; de API kan nog wijzigen (zie `CHANGELOG.md`). Het oppervlak dat
nlriochecker gebruikt ligt vast in `tests/test_publieke_api.py`; de modulesnit
staat in `docs/architectuur.md`. Licentie: [MIT](LICENSE).
