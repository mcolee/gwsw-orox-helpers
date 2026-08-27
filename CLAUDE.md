# Project: gwsw-orox-helpers

Leeslaag voor GWSW-OroX (TTL): grafmodel, geometrie, klassenhierarchie, cache.
Eerste afnemer: nlriochecker. Nederlandse identifiers, GWSW-conform.

## Harde regels
- **Leidende GWSW-versie: 1.6**, uit de gebundelde
  `src/gwsw_orox_helpers/data/Ontologie_GWSW_Totaal.ttl` (`owl:versionInfo`:
  *"Deelmodel Totaal, filter op CoFs BAS DMO EN HYD LDR MDS NLCS PLI RRB TOP,
  versie=1.6 (2025-11-18T14:53:33)"*). Dit is de enige plek waar het nummer als
  projectafspraak staat; `test_indexversie_staat_in_claude_md` leest het `versie=`-deel
  hier terug. Upgraden is handwerk van de auteur: hij levert een nieuw ontologiebestand
  en dan trekt de package bij. Draai daarbij `uv run python scripts/maak_gwsw_index.py`
  (herschrijft de gebundelde index) en werk deze regel bij; de drifttests bewaken
  beide richtingen.
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
  dekking >= 95% (`uv run --with pytest-cov pytest --cov=gwsw_orox_helpers`).
- **De mechanische poort** is deze vijf stappen, in deze volgorde, op de voorgrond:
  `uv run ruff check`, `uv run ruff format --check .`, `uv run mypy`, `uv run pytest`,
  en `uv run --with pytest-cov pytest --cov=gwsw_orox_helpers --cov-fail-under=95`.
  Dezelfde vijf staan in `.github/workflows/toets.yml`; wijkt de een af, dan wijken ze
  allebei af. Draai hem bij elke commit die `src/**.py` raakt en **lees de uitvoer** —
  "de tests draaiden" is geen bewijs, de geplakte uitvoer wel.
- Kleine stappen; na elke groene stap een commit met een duidelijke boodschap. Werk op
  `dev`. Deze repo kent (nog) geen release-splitsing: geen merge naar `main`, geen
  `scripts/uitgave.py`; het versienummer in `pyproject.toml` bumpt de auteur.
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
- **`docs/agents/afk-regie.md`** is het sjabloon voor een onbewaakte regiesessie die een
  reeks `ready-for-agent`-issues met Opus-subagents afwerkt: lus per issue, één poort,
  review-timing, wachten zonder pollen, slotrapport.
- **`docs/agents/issue-tracker.md`** beschrijft de `gh`-conventies en de zesdelige
  huisstijl van een `ready-for-agent`-issue. Openstaand werk staat als GitHub-issue op
  `mcolee/gwsw-orox-helpers`, niet in een bestand hier; hou die lijst de enige plek.
- **`docs/agents/triage-labels.md`** koppelt de vijf canonieke triagerollen aan de
  labelstrings van deze tracker.
