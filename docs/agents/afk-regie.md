# AFK-regie: een reeks issues fixen met subagents (sjabloon)

Geef dit, met de issuelijst ingevuld, aan een **verse (gecleared) Fable-sessie** in
`/home/martin/gwsw-orox-helpers`. Fable is de regisseur; het echte werk doen **subagents**.
Kies per issue het model naar zwaarte volgens de globale `CLAUDE.md` (sectie **Modelkeuze
subagents**): substantieel/kritiek-pad → **Opus 4.8** via de `opus48`-agent (de kale alias
`model: opus` levert in deze harness Opus 5), klein/docs/config/test-only → **Sonnet**.
**Rapporteer bij elke dispatch expliciet welk model je inzet.** De auteur is er niet
bij — **unattended**. Dit sjabloon is overgenomen uit `nlriochecker`, waar het over meerdere
onbewaakte runs is aangescherpt; de punten hieronder komen uit die metingen.

## Houding

- **Stel geen vragen aan de auteur.** De issues zijn volledige `ready-for-agent`-specs; ze zijn
  de bron. Twijfel je over een detail, volg de sectie **Aannames** in het issue en leg een
  afwijking vast als issue-comment — verzin geen domeinlogica (GWSW is leidend, `CLAUDE.md`).
  Eén uitzondering, en die staat in `CLAUDE.md`: raakt een wijziging een bestaand publiek
  contract dat nlriochecker importeert, dan **stopt** de agent en legt het aan de auteur voor.
- **"Klaar" pas als jíj het bewijs zag** — bewijs is de *geplakte* poort-uitvoer van de
  implementer plus de groene CI na de push, niet een derde run (zie de lus).
- **Werk op `dev`.** Deze repo kent (nog) geen release-splitsing: er is geen merge naar `main`
  en geen `scripts/uitgave.py`. Uitbrengen is handwerk van de auteur. Commit na elke groene stap.
- Lees vooraf één keer: `CLAUDE.md`, `docs/architectuur.md` (de lagen, de twee paden door
  pyoxigraph, de beloften) en het issue zelf; daarna elke module die je raakt één keer volledig.
- **Auto-mode blokkeert een paar schrijfacties.** In een unattended run weigert de
  auto-mode-classifier soms `gh issue create` en `gh repo create` ("Blocked by classifier"), en
  soms de eerste agent-dispatch (die lukt bij herhaling). Probeer na een classifier-blokkade
  geen variant van dezelfde schrijfactie: stage de body/args in een scratchbestand, meld het één
  keer aan de auteur en wacht op het startsein.
- **Volg `CLAUDE.md` strikt.** Bij twijfel wint `CLAUDE.md` boven deze brief.
- **Gebruik de skills expliciet.** Elke implementer draait `mattpocock-skills:tdd` (eerst de
  falende test, dan de code); een bug los je op met `mattpocock-skills:diagnosing-bugs`; een
  substantiële review gaat via `mattpocock-skills:code-review`. Er is geen skill die
  "verificatie vóór afronden" of het uitvoeren van een plan afdwingt: dat schrijf je gewoon in
  de brief — *draai de volledige poort op de voorgrond en lees de uitvoer regel voor regel*, en
  *werk het issue punt voor punt af en meld per punt wat er landde*. Een agent die een skill
  negeert, doet het over.

## Volgorde — strikt sequentieel

Issues die bestanden delen doe je één voor één; noteer hier de volgorde en de
`blocked by`-relaties:

1. **#…** …
2. **#…** … — *blocked by #…*

Eén issue = één sessie-eenheid: commit + push + CI groen + comment + close vóór het volgende.

## De lus per issue N

1. **Lees** het issue volledig: `gh api repos/mcolee/gwsw-orox-helpers/issues/N --jq .body` en
   `.../issues/N/comments`. Dat is de spec.
2. **Claim**: `gh issue edit N --add-assignee @me`.
3. **Dispatch de implementer** — kies het model naar de zwaarte van #N (globale `CLAUDE.md`,
   **Modelkeuze subagents**): substantieel/kritiek-pad → Opus 4.8 via `subagent_type: opus48`;
   klein/test-/config-only → `model: sonnet`, `subagent_type: general-purpose`. **Meld
   expliciet welk model deze dispatch inzet.** Brief, zelfstandig en met een taaklabel:

   > **Task 1 — implementeer issue #N.** Repo `/home/martin/gwsw-orox-helpers`, tak `dev`. Volg
   > de body van #N verbatim en `CLAUDE.md` strikt (Harde regels + Werkwijze). Draai
   > `mattpocock-skills:tdd` (eerst de falende test/fixture, dan de code). Concreet:
   > - **Lezen:** lees het issue en `CLAUDE.md` één keer volledig vóór je begint, en daarna elk
   >   bestand dat je aanraakt één keer volledig — niet per symbool in plakjes. Geen `cd`: de
   >   werkmap is al de repo-root.
   > - **Harde regel:** nlriochecker mag nooit breken. Fasewerk is additief; raak je tóch een
   >   bestaande signatuur of bestaand gedrag, **stop** en meld het in plaats van het te wijzigen.
   > - Regenereer elke generator die je raakt (`scripts/maak_fixtures.py`,
   >   `scripts/maak_gwsw_index.py`) en commit de gegenereerde bestanden mee.
   > - Voeg een regel toe onder `## [Unreleased]` in `CHANGELOG.md`.
   > - Draai de **volledige mechanische poort op de voorgrond** en plak de uitvoer letterlijk:
   >   `uv run ruff check`, `uv run ruff format --check .`, `uv run mypy`, `uv run pytest -q`,
   >   `uv run pytest --cov=gwsw_orox_helpers --cov-fail-under=95`.
   > - **Niet pushen.** Rapporteer terug: gewijzigde bestanden, de geplakte poort-uitvoer, en
   >   open aannames.

4. **Lees de geplakte poort.** Staat er een rode regel of ontbreekt een van de vijf stappen,
   dispatch een fix-agent (Task 2). Is hij groen, dan **draai je hem niet nog eens**: in de
   nlriochecker-run van 26-08 waren alle 12 herhalingen groen en kostten ze ~36 calls en ~1 uur
   pytest.
5. **Review naar risico** (reviewer, verse agent — model naar risico) — de indeling staat in `CLAUDE.md`:
   - **Docs/config** (geen `src/**.py`): geen poort en geen review, alleen de drifttests die de
     wijziging raakt (bv. `test_indexversie_staat_in_claude_md`, die `CLAUDE.md` aan de
     gebundelde index bindt).
   - **Klein** → `/code-review` (`low` bij een triviale one-liner, anders `medium`).
   - **Substantieel** (nieuwe module/feature, publieke API, cache- of geometriepad, of een
     Harde regel) → `mattpocock-skills:code-review` met een verse **Opus 4.8**-reviewer (`opus48`-agent): *"Task 3 —
     review de diff op `dev` sinds de laatste commit tegen de spec van #N en de Harde regels.
     Adversarieel: correctheid, dekt het de spec, kloppen de drifttests, breekt het een publiek
     contract dat nlriochecker importeert?"* Important-bevindingen gaan naar een fix-agent,
     minors naar de ledger.
   - **Re-review alleen als de fixronde meer dan één bevinding of meer dan ~100 diffregels
     raakte.** Een één-bevinding-fix controleer je zelf op de diff: op 26-08 veranderden 6 van
     6 re-reviews niets.
6. **Commit** op `dev`, boodschap eindigend op `(issue #N)`.
7. **Push, dan CI.** Eén keer, ná de laatste fixronde: `git push` en
   **`gh run watch --exit-status`** tot groen; dat bewijst de CI, een extra `gh run view` niet.
   De CI draait dezelfde poort als jij (`.github/workflows/toets.yml`).
8. **Comment + close — pas na het reviewoordeel.** `gh issue comment N` met wat er landde en wat
   er gemeten is naast de voorspelling uit het issue (klopt de ordegrootte? zo niet, verklaar het
   — geen nieuwe waarheid verzinnen). Schrijf de comment niet vooraf om hem later te patchen: op
   26-08 kostte dat 6 patches en één teruggenomen claim. Dan `gh issue close N`.
9. **Vastloper?** Poort niet groen of iets echt onbeslist → meld nooit "klaar": comment met
   de échte toestand, issue open laten, door naar het volgende issue dat er niet op leunt.

## Ledger

Houd één `progress.md` bij in de werkruimte, maar laat het achtergrondcommando zijn eigen
slotregel schrijven (`...; tail -3 poort.log >> progress.md`) in plaats van `cat log` plus
`echo >> progress.md` als twee losse calls (17 losse ledger-calls op 26-08). **Uitgestelde
minors die de auteur moet zien, zet je in het slotrapport** — de ledger is git-ignored en
verdwijnt met de werkruimte.

## Meten

Noteer hier per issue het getal dat het issue voorspelt (bv. een dekkingspercentage, een
aantal tripels, een laadtijd) en reproduceer het na afloop met de echte package-API, niet uit
het geheugen. Een meetscript dat een getal onderbouwt commit je mee.

## Wachten (uit `CLAUDE.md`)

Niet pollen. Een subagent en een `run_in_background`-commando **melden zich vanzelf** — geen
`sleep`, geen `ListAgents`-lus. Alleen `gh run watch` gebruikt een voorgrond-wacht.

## Slotstap — na alle issues

1. **Volledige poort op de eindstand van `dev`**, inclusief de dekkingsstap, en de CI groen na
   de laatste push.
2. **Slotrapport aan de auteur.** Per issue wat er landde, gemeten getal naast voorspelling,
   open gebleven issues en waarom, de uitgestelde minors, en elk punt waarop je een aanname hebt
   gecorrigeerd.

## Harde grenzen

- **Werk op `dev`.** Geen merge naar `main`, geen uitgave: die splitsing bestaat hier (nog)
  niet en het versienummer bumpt de auteur.
- **nlriochecker mag nooit breken.** Raakt een wijziging een bestaand publiek contract, dan
  stop je en leg je het voor; pas na expliciete toestemming, en dan gecoördineerd in beide
  repo's (CHANGELOG + versiebump in elk). Zie `CLAUDE.md`.
- Raakt een wijziging een Harde regel of een publiek contract, dan is de review **verplicht
  Substantieel**, ongeacht je inschatting.
- Overschrijf nooit invoerbestanden; het versienummer staat alleen in `pyproject.toml`. Zie
  `CLAUDE.md`.
