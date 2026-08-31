# gwsw-orox-helpers

gwsw-orox-helpers is een Python-bibliotheek voor GWSW-OroX-bestanden (Turtle): rioleringsdata volgens het
[Gegevenswoordenboek Stedelijk Water](https://data.gwsw.nl/). Ze leest een OroX-export in een domeinmodel (putten,
leidingen, aspecten, klassenhiërarchie) met de geometrie als shapely-objecten, schrijft dat model verliesloos terug,
en knipt een export langs een grenslaag in delen die weer tot het origineel samen te voegen zijn. De GWSW-ontologieën
1.6 en 1.7 zijn meegebundeld (1.6 is de default). Eerste afnemer: [nlriochecker](https://github.com/mcolee/nlriochecker).

[![toets](https://github.com/mcolee/gwsw-orox-helpers/actions/workflows/toets.yml/badge.svg?branch=main)](https://github.com/mcolee/gwsw-orox-helpers/actions/workflows/toets.yml)
[![licentie MIT](https://img.shields.io/badge/licentie-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](pyproject.toml)

## Stand van zaken

De bibliotheek is bruikbaar, maar nog vóór 1.0.

- **Pre-1.0.** De publieke API kan tot 1.0 nog wijzigen, maar alleen met een regel in [CHANGELOG.md](CHANGELOG.md)
  en een versiebump. Het oppervlak dat nlriochecker importeert ligt vast in `tests/test_publieke_api.py` en geldt
  als bevroren.
- **GWSW-ontologieën 1.6 en 1.7 meegebundeld** als package-resource (`bronnen.gebundelde_ontologie` /
  `bronnen.vocabulaire_index_pad` leveren de default 1.6; `..._voor(versie)` kiest een van beide). Een nieuwe
  GWSW-versie is een release hier plus een `uv lock` bij de afnemer.
- **Getest op de export van De Wolden en Hoogeveen** (112 MB, 1,9 miljoen triples, ruim 23.000 putten en strengen).
  Andere gemeenten en andere beheerpakketten zijn nog niet geprobeerd.
- **Niet op PyPI.** Installeren gaat rechtstreeks uit git (zie hieronder).

## Wat je krijgt

Drie bewerkingen op een OroX-export, elk uit één ingang.

**Lezen** — `load_dataset` parseert een export naar een domeinmodel: putten, leidingen, aspecten en de
klassenhiërarchie, met de GML-geometrie als shapely-objecten. Zonder opgave leest het met de gebundelde
GWSW-ontologie (default 1.6). `laad_met_cache` maakt herladen vrijwel gratis.

**Schrijven** — `schrijf_orox` regenereert een export van bestand naar bestand: niet byte-gelijk aan de bron, wel
graaf-gelijk (isomorf). Het schrijft via een tijdelijk bestand en hernoemt pas bij succes, zodat een fout halverwege
geen afgekapte export achterlaat.

**Knippen en samenvoegen** — `clip_orox` knipt een export langs een GeoJSON-grenslaag in N delen; `merge_orox` voegt
die verliesloos terug tot een graaf die isomorf is aan de bron. Een leiding die de grens kruist wordt doorgeknipt en
per herkomst weer aaneengenaaid; het geknipte stuk krijgt het merk `knip:geknipt`, zodat een deel op zichzelf
leesbaar blijft.

Motoren: pyoxigraph (de Rust-parser), rdflib en shapely.

## Snel proberen

Python 3.12+ en [uv](https://docs.astral.sh/uv/) (of pip). Installeren gaat uit git:

```sh
uv add git+https://github.com/mcolee/gwsw-orox-helpers   # of: pip install git+https://github.com/mcolee/gwsw-orox-helpers
```

Lezen, en dan knippen en weer samenvoegen:

```python
from pathlib import Path

from gwsw_orox_helpers import clip_orox, merge_orox
from gwsw_orox_helpers.dataset import load_dataset

ds = load_dataset(Path("gemeente_orox.ttl"))  # met de gebundelde GWSW-ontologie (default 1.6)
print(len(ds.nodes), "putten,", len(ds.conduits), "leidingen")

delen = clip_orox(
    Path("gemeente_orox.ttl"), Path("grenzen.geojson"), Path("delen/"), sleutel="gemeentenaam"
)
merge_orox(delen, Path("terug.ttl"))  # isomorf aan de bron
```

Op de export van De Wolden en Hoogeveen (112 MB) laadt `load_dataset` in ~20 s (23.485 putten, 23.440 strengen) en
knipt `clip_orox` in ~39 s; het piekgeheugen blijft onder 1,3 GB. De metingen en het benchmarkscript staan in
[CHANGELOG.md](CHANGELOG.md).

## Verder lezen

- **[docs/architectuur.md](docs/architectuur.md)**: de modulesnit van `src/gwsw_orox_helpers/`, de importrichting,
  de twee paden door pyoxigraph (lezen met index, schrijven als stroom) en waar de gedeelde IRI-, prefix- en
  coderingskennis woont.
- **[tests/test_publieke_api.py](tests/test_publieke_api.py)**: het bevroren oppervlak dat nlriochecker importeert —
  handtekeningen en velden liggen daar vast.
- **[CHANGELOG.md](CHANGELOG.md)**: het versienummer en elke noemenswaardige wijziging.

## Ontwikkelen

```sh
uv sync
uv run ruff check
uv run ruff format --check .
uv run mypy                                             # over src/gwsw_orox_helpers
uv run pytest                                           # `zwaar` niet; `-m zwaar` draait tegen een niet-getrackte export
uv run pytest --cov=gwsw_orox_helpers --cov-fail-under=95  # pytest-cov komt uit de dev-groep
```

Dezelfde vijf stappen draaien in CI bij elke push naar `main` of `dev` (`.github/workflows/toets.yml`). De werkwijze
en de harde regels (de bevroren API, de leidende GWSW-versie) staan in [CLAUDE.md](CLAUDE.md).

## Bijdragen

Meld een fout of een export waarop het misgaat op de
[issuetracker](https://github.com/mcolee/gwsw-orox-helpers/issues). Omdat nlriochecker op de publieke API leunt,
bespreek je een pull request die dat oppervlak raakt eerst in een issue.

## Licentie

Copyright © 2026 Martin Colee. Licensed under the [MIT License](LICENSE).
