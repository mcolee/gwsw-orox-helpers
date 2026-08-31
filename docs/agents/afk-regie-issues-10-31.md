# AFK-regie: issues #10–#31 (de "10x"-review-batch)

Geef dit aan een **verse (gecleared) Fable-sessie** op `dev` in `/home/martin/gwsw-orox-helpers`.
Fable is de regisseur; het echte werk doen verse Opus-subagents (`model: opus`). Het is de
ingevulde variant van `docs/agents/afk-regie.md` voor deze specifieke batch.

---

Je bent de REGISSEUR (model: Fable) van een unattended AFK-regierun in
/home/martin/gwsw-orox-helpers. Werk de openstaande ready-for-agent-issues #10–#31 af
(de "10x"-review-batch). Het echte werk doen verse Opus-subagents (model: opus); jij
orkestreert, reviewt en sluit.

## Bron van waarheid
Volg `docs/agents/afk-regie.md` in deze repo VERBATIM — dat is het regiesjabloon (houding,
de lus per issue, wachten-zonder-pollen, ledger, slotrapport, harde grenzen). Lees vooraf
één keer volledig: `docs/agents/afk-regie.md`, `CLAUDE.md`, `docs/architectuur.md` en
`docs/agents/issue-tracker.md`. Bij twijfel wint `CLAUDE.md` boven deze brief.

## Repo-specifieke invulling (afwijkingen t.o.v. het generieke nlriochecker-sjabloon)
- **Poort** (voorgrond, uitvoer plakken), de vijf stappen uit `CLAUDE.md`:
  `uv run ruff check`, `uv run ruff format --check .`, `uv run mypy`, `uv run pytest`,
  `uv run --with pytest-cov pytest --cov=gwsw_orox_helpers --cov-fail-under=95`.
  Zware tests staan onder de marker `zwaar` en slaan zichzelf over zonder de export — de
  snelle poort draait ze niet mee; forceer ze niet.
- **Geen release-splitsing:** dit is `dev`-werk. Geen merge naar `main`, geen
  `scripts/uitgave.py`, geen gemeentebrede eind-uitvoer. Uitbrengen is handwerk van de auteur.
- **Review naar risico, per `CLAUDE.md`, Werkwijze** (staat ook al in elk issue onder
  "Verificatie"): klein → `/code-review`; substantieel (kritiek pad / publiek contract /
  Harde regel) → `mattpocock-skills:code-review`, uitkomsten verwerken, dan de poort opnieuw.
  Deze repo gebruikt **mattpocock-skills:code-review**, niet superpowers:requesting-code-review.
- **Geen `docs/beslislog.md` / BO-nummers** in deze repo — sla die stap over.
- **Meten (perf-issues #12, #13, #23):** gebruik `scripts/benchmark.py` (meet load/schrijf/
  clip/merge elk in een eigen kindproces) en meet **gepaard** (voor/na op dezelfde export).
  Beloof geen orde-grootte-winst; incrementele % is het verwachte beeld. Voor niet-perf-issues
  is "meten" de test/fixture die het issue vraagt.
- **Generators die je raakt regenereer je in dezelfde stap** (`scripts/maak_fixtures.py`,
  `scripts/maak_gwsw_index.py`) en commit het gegenereerde bestand mee; de drifttests bewaken
  beide richtingen.
- **Publieke API is BEVROREN** (clip_orox/merge_orox/lees_orox/schrijf_orox/schrijf_orox_quads
  + leeslaag dataset/cache/geometry). Blijkt een issue tóch een bevroren contract te raken:
  STOP, comment op het issue, laat het open, ga door naar het volgende — zelf geen migratiepad
  verzinnen (`CLAUDE.md`, Harde regels).
- **Issues lezen/commenten/sluiten:** `gh api repos/mcolee/gwsw-orox-helpers/issues/N --jq .body`
  en `.../issues/N/comments`; claimen met `gh issue edit N --add-assignee @me`; afsluiten met
  `gh issue comment N` (wat er landde + gemeten getal naast de voorspelling) dan
  `gh issue close N`. Na de push: `gh run watch --exit-status` tot groen bewijst de CI.

## Volgorde — strikt sequentieel (bijna alles deelt bestanden; één issue = één eenheid)
Foundationeel/blokkers eerst, dan per gebied. Respecteer de blocked-by's.
 1. **#10** round-trip-fixture — vangnet vóór de clip-refactor (test_clip.py)
 2. **#14** bovengrenzen op deps (pyproject.toml)
 3. **#15** mkstemp in schrijf_orox_quads (schrijven.py)
 4. **#12** is_a-memoïsatie (dataset/klassen) — *blocker voor #27*
 5. **#11** clip.py → clip/-package (clip.py) — *blocker voor #17; foundationeel voor alle clip-werk*
 6. **#17** geometry tekst-chirurgie ↔ clip — *blocked by #11*
 7. **#13** één-pass GML-lezer (geometry/inlezen)
 8. **#18** pyoxigraph-adapter (inlezen/schrijven/clip) — na #11/#13/#15/#17
 9. **#19** facetbereik-lezing #35 (ontologie/klassen/graaf)
10. **#21** GraafLezer-Protocol (graaf/ontologie) — na #19
11. **#23** _uriref_snel doortrekken (dataset/inlezen/graaf) — na #12/#21
12. **#26** parseerpad splitsen in inlezen (inlezen/dataset/cache)
13. **#27** netwerkwandeling uit GwswDataset (dataset) — *blocked by #12*
14. **#29** _short/_uri → namen (klassen/namen/inlezen/dataset)
15. **#30** dedup-yield-lussen bundelen (inlezen)
16. **#22** RecursionError in _lees_grenzen (clip)
17. **#28** CRS-mismatch-terugval (clip)
18. **#31** DatasetError-subklassen (errors/codering/clip)
19. **#20** mypy strenger: disallow_untyped_defs (pyproject/inlezen)
20. **#16** vier ongedekte takken (tests/maak_fixtures)
21. **#24 + #25** CI-triggerdiscipline + reproduceerbare install — **samen landen** (docs/config, geen poort)

## Wachten
Niet pollen. Subagents en `run_in_background`-commando's melden zich vanzelf — geen `sleep`,
geen `ListAgents`-lus. Alleen `gh run watch` is een voorgrond-wacht.

## Slot
Slotrapport aan de auteur: per issue wat er landde, gemeten getal naast voorspelling, welke
issues open bleven en waarom, en de uitgestelde minors. Raakte iets een bevroren contract, dan
staat het als open issue met een comment — niet stilzwijgend meegenomen.
