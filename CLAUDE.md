# Project: gwsw-orox-helpers

Lees vóór je code aanraakt `manifesto.md` in de repo-root (lokaal, git-ignored): het
draagt de missie, de prioriteiten bij botsende doelen en wat we nadrukkelijk niet doen.

Leeslaag voor GWSW-OroX (TTL): grafmodel, geometrie, klassenhierarchie, cache.
Eerste afnemer: nlriochecker. Nederlandse identifiers, GWSW-conform.

## Harde regels
- **Twee gebundelde GWSW-versies, 1.6 (default/leidend) en 1.7.** Beide reizen
  versie-benoemd met de package mee:
  - **1.6** uit `src/gwsw_orox_helpers/data/gwsw_ontologie_totaal_16.ttl` (`owl:versionInfo`:
    *"Deelmodel Totaal, filter op CoFs BAS DMO EN HYD LDR MDS NLCS PLI RRB TOP,
    versie=1.6 (2025-11-18T14:53:33)"*).
  - **1.7** uit `src/gwsw_orox_helpers/data/gwsw_ontologie_totaal_17.ttl` (`owl:versionInfo`:
    *"Deelmodel Totaal, filter op CoFs BAS DMO EN HYD LDR MDS NLCS PLI REV RRB TOP,
    versie=1.7 (2026-08-25T17:09:23)"*).

  **1.6 is de default en de leidende versie**: `bronnen.gebundelde_ontologie()` en
  `bronnen.vocabulaire_index_pad()` leveren de 1.6-bestanden, en zonder dataset-context
  leest de package 1.6. Sinds deel c van issue #32 **detecteert de package de versie uit de
  bron**: `bestand._parse` leest de `gwsw:`-prefix (met de predicaat-IRI's als terugval) en
  zet die basis op `GraafIndex.gwsw_basis`; de lees- en cliplaag leiden hun predicaten en
  klasse-IRI's daaruit af, en `load_dataset` kiest zonder opgegeven ontologie de gebundelde
  versie die bij de gedetecteerde basis hoort. Een bron zonder herkenbare versie valt terug
  op 1.6 **met een `logging.warning`** (nooit stil); een gedetecteerde maar niet-gebundelde
  versie (bv. 1.8) leest met de gevonden termenset maar valt voor de ontologie terug op de
  1.6-bundel, ook met een melding. De **publieke leesweg** naar die versie is de
  gememoiseerde property `GwswDataset.gwsw_versie` (issue #39; het drieveldige `GwswVersie`:
  `basis`, `versie`, `gedetecteerd`), niet het interne `_basis`; ze leidt de versie net als
  `_basis` af uit de typen van de knopen en strengen, zodat het luie cachepad de graafpickle
  niet hoeft te laden.

  Dit is de enige plek waar de versienummers als projectafspraak staan;
  `test_indexversie_staat_in_claude_md` leest per gebundelde index het `versie=`-deel hier
  terug (beide versies). Upgraden is handwerk van de auteur: hij levert een nieuw
  ontologiebestand en dan trekt de package bij. Draai daarbij
  `uv run python scripts/maak_gwsw_index.py` (herschrijft **beide** gebundelde indexen,
  `gwsw-vocabulaire-index-16.json` / `-17.json`) en werk deze regel bij; de drifttests
  bewaken beide richtingen, per versie.
- De publieke API is wat nlriochecker importeert; breken mag tot 1.0 maar alleen
  met een CHANGELOG-regel en een versiebump.
- **nlriochecker mag nooit breken.** Dat "breken mag tot 1.0" hierboven is de vrijheid
  van de bibliotheek tegenover de buitenwereld, niet die van een agent: voor een agent
  is de publieke API die nlriochecker importeert **bevroren**. Fasewerk (de schrijver,
  de clip, wat er nog volgt) is **additief** — nieuwe modules en nieuwe functies, nooit
  een bestaande signatuur, een bestaande retourvorm of bestaand gedrag. Raakt een
  wijziging tóch een bestaand contract, dan **stopt de agent en legt het aan de auteur
  voor**; hij lost het niet zelf op en verzint geen migratiepad. Pas na expliciete
  toestemming van de auteur mag het, en dan **gecoördineerd in beide repo's**: een
  CHANGELOG-regel en een versiebump in elk, en `uv lock` aan de nlriochecker-kant.
- Geen nlriochecker-begrippen in deze package: vulwaardenlijsten, encodingkeuzes
  en checkconfiguratie zijn parameters, geen constanten.

## Werkwijze
- Python 3.12+, src-layout, uv; poort: ruff check, ruff format, mypy, pytest,
  dekking >= 95% (`uv run pytest --cov=gwsw_orox_helpers`).
- **De mechanische poort** is deze vijf stappen, in deze volgorde, op de voorgrond:
  `uv run ruff check`, `uv run ruff format --check .`, `uv run mypy`, `uv run pytest`,
  en `uv run pytest --cov=gwsw_orox_helpers --cov-fail-under=95`. Stap vijf draait sinds
  issue #25 **zonder `--with pytest-cov`**: pytest-cov staat in `[dependency-groups] dev`
  van `pyproject.toml` en dus in `uv.lock`, en uv synct de dev-groep standaard mee — kaal
  `uv run` volstaat, `--group dev` is niet nodig. Zo draait de dekkingsstap uit de
  gelockte set in plaats van elke keer een ongepinde download.
  Dezelfde vijf staan in `.github/workflows/toets.yml`; wijkt de een af, dan wijken ze
  allebei af. CI draait daarnaast, ná die vijf, `uv build && uvx twine check dist/* && uvx
  check-wheel-contents dist/*.whl` als sdist-/wheel-bewaker (issue #44) — een zesde stap die
  de vijf niet raakt en die je lokaal alleen bij een packaging-wijziging hoeft te draaien.
  Draai hem bij elke commit die `src/**.py` raakt en **lees de uitvoer** —
  "de tests draaiden" is geen bewijs, de geplakte uitvoer wel. Let op: `ruff format
  --check .` controleert óók Python-codeblokken in Markdown; een README-only commit kan
  de poort dus rood zetten (gebeurde 27-08), draai die check ook bij docs met codeblokken.
- Kleine stappen; na elke groene stap een commit met een duidelijke boodschap. Werk op
  `dev`; `main` draagt alleen uitgebrachte, getagde versies en is GitHub-beschermd (PR
  verplicht, ook voor de eigenaar).
- **Release-poort naar bump-grootte: de review-swarm.** Het script staat geborgd in
  `.claude/workflows/orox-10x-swarm.js`; draai `Workflow({name: 'orox-10x-swarm'})` (8
  lens-agents → adversariële verify → Fable-regisseur met ≤25 aanbevelingen,
  additief-vs-contract gelabeld). De poort hangt af van de bump:
  - **Major** (na 1.0): **verplicht** vóór de release — draaien en de uitkomst **wegen** is
    een poort, geen suggestie.
  - **Minor en patch:** **aanbevolen, maar alleen ná expliciete goedkeuring van de auteur**
    draai je hem — standaard sla je hem over. Hij kost tokens en ~50 min wall-clock; elke
    minor/patch blind draaien is de overkill die we bewust vermijden.
  Verplicht (bij major) is het **draaien en wegen** van de bevindingen, niet het overnemen
  ervan: je mag alles parkeren, maar je legt in de release-notitie (of een comment op de
  release-PR) kort vast dát je hem hebt gedraaid en wat je met de top-bevindingen doet
  (oppakken, als `ready-for-agent`-issue wegzetten, of bewust laten liggen). Contract-rakers
  gaan nooit stilzwijgend mee: die zijn een auteursbeslissing (`CLAUDE.md`, Harde regels).
- **Een versie uitbrengen** (handwerk, deze repo heeft geen `scripts/uitgave.py`): op `dev`,
  met een schone en groene werkboom, `uv version --bump patch|minor|major` (raakt
  `pyproject.toml` én `uv.lock`), dan in `CHANGELOG.md` de sectie `## [Unreleased]` omzetten
  naar `## [X.Y.Z] - <datum>` met een verse lege `Unreleased` erboven, de volledige poort
  draaien, committen als `Versie X.Y.Z` (alleen `pyproject.toml`, `uv.lock`, `CHANGELOG.md`)
  en taggen als `vX.Y.Z`. Landen op `main` via een **merge-commit-PR** (geen squash/rebase,
  anders hangt de tag naast `main`); zet `dev` daarna weer gelijk aan `main`. Pushen met
  `git push --follow-tags` en `timeout 45 git push …`. **De wheel komt vanzelf**:
  `.github/workflows/release.yml` gaat af op de tag `v*`, draait `uv build` en hangt de
  wheel + sdist aan een GitHub Release — nooit met de hand `gh release create` draaien.
  Cijfers: patch = reparaties; minor = een afgerond blok/fase of een breuk in de publieke
  API vóór 1.0; major pas ná 1.0.
- Kies de review naar het **risico** van de wijziging, niet naar de omvang:
  - **Docs/config** (geen `src/**.py`, bv. deze regel): geen poort en geen review,
    alleen de drifttests die de wijziging raakt — voor `CLAUDE.md` is dat
    `test_indexversie_staat_in_claude_md`, die de regel over de leidende GWSW-versie aan
    de gebundelde index bindt.
  - **Klein** (code buiten de kritieke paden, geen nieuwe feature): `/code-review` —
    `low` bij een triviale one-liner, anders `medium`.
  - **Substantieel** (een nieuwe module of feature, óf de wijziging raakt een kritiek
    pad: de publieke API, de dataset-/graafinlees, de geometrie, de cache of de
    ontologie): `mattpocock-skills:code-review`; verwerk de uitkomsten en draai de poort
    daarna opnieuw.
  - **Altijd Substantieel**, ongeacht je inschatting: elke wijziging aan een Harde regel
    of aan een publiek contract dat nlriochecker importeert.
- Elke noemenswaardige wijziging krijgt een regel onder `## [Unreleased]` in
  `CHANGELOG.md`.
- Regenereer elke generator die je raakt (`scripts/maak_fixtures.py`,
  `scripts/maak_gwsw_index.py`) en commit het gegenereerde bestand in dezelfde stap mee;
  de drifttests bewaken beide richtingen.

## Naslag
- **`docs/architectuur.md`** beschrijft de snit van `src/gwsw_orox_helpers/`: de lagen en
  hun importrichting, de twee paden door pyoxigraph (lezen met index, schrijven als
  stroom) en waar de gedeelde IRI-, prefix- en coderingskennis woont. Lees dat vóór een
  wijziging die meer dan een module raakt.
- **`docs/agents/afk-regie.md`** is het sjabloon voor een onbewaakte regiesessie die een
  reeks `ready-for-agent`-issues met Opus-subagents afwerkt: lus per issue, één poort,
  review-timing, wachten zonder pollen, slotrapport.
- **`docs/agents/issue-tracker.md`** beschrijft de `gh`-conventies en de zesdelige
  huisstijl van een `ready-for-agent`-issue. Openstaand werk staat als GitHub-issue op
  `mcolee/gwsw-orox-helpers`, niet in een bestand hier; hou die lijst de enige plek.
- **`docs/agents/triage-labels.md`** koppelt de vijf canonieke triagerollen aan de
  labelstrings van deze tracker.
