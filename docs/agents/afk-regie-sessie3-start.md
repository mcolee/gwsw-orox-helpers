# Startprompt regiesessie 3 (headless): #69–#72 en release 0.2.3 als GitHub-Release

Dit is de letterlijke opdracht die `docs/agents/afk-regie-sessie3-start.sh` aan een headless
Fable-sessie (`claude -p`) geeft. De auteur besloot op 05-09-2026 dat de reeks zonder
tussenreleases op `dev` landt, dat #73–#75 vervallen, en dat sessie 3 afsluit met de release
0.2.3: tag, merge naar `main` en een GitHub-Release met de wheel, **zonder enige
PyPI-interactie** (Harde regel in `CLAUDE.md`).

---

AFK-regie sessie 3 van de Fable-archperf-reeks in /home/martin/gwsw-orox-helpers, tak dev.
Lees één keer volledig: CLAUDE.md, docs/agents/afk-regie.md (de lus, inclusief de
stavaza-tabel na elke afronding) en docs/agents/afk-regie-issues-59-75.md (deze reeks; de
planwijziging van 05-09 staat erin). Lees ook manifesto.md. Jij bent de regisseur; alle
implementers en reviewers zijn Opus 4.8 via subagent_type: opus48. Volledig unattended: de
auteur is er niet en leest morgen alleen het slotrapport; stel geen vragen, neem beslissingen
volgens de Aannames-secties van de issues en leg afwijkingen vast als issue-comment.

## Deel 1 — vier issues, strikt sequentieel

#69 → #70 → #71 → #72, één tegelijk, nooit twee meetagents naast elkaar. Per issue: lezen
(`gh api repos/mcolee/gwsw-orox-helpers/issues/N --jq .body` en `.../comments`), claimen,
implementer (mattpocock-skills:tdd), poort-uitvoer lezen, Opus 4.8-review via
mattpocock-skills:code-review (alle vier Substantieel), commit "(issue #N)", push,
CI afwachten, comment met de ruwe metingen naast de voorspelling, close, stavaza-tabel.

Meetprotocol voor #70 (het enige perf-issue): gepaard (referentie = HEAD via `git worktree add`
op PYTHONPATH, nooit `git stash`), n ≥ 3, om en om, vers proces per run, eenduidig; niet
aangetoond = open laten met comment. De reviewer reproduceert de meting onafhankelijk.
Aandachtspunt #69 deel (c): kies de conservatieve route uit het issue (cache neemt de laatste
treffer), zoals de reeksbrief zegt. #71: het additieve `CacheUitslag`-veld met default; de pin in
tests/test_publieke_api.py groeit mee met CHANGELOG-regel.

CI: direct na elke push `RUN=$(gh run list -R mcolee/gwsw-orox-helpers --commit $(git rev-parse
HEAD) --json databaseId --jq '.[0].databaseId')` (volledige sha; een korte sha geeft stil een
lege lijst; wacht in een until-lus tot RUN gevuld is) en dan `gh run watch $RUN --exit-status`.

Subagents: schrijf in elke brief dat de agent lange commando's op de voorgrond draait met een
ruime timeout en zijn beurt nooit beëindigt om op een achtergrondtaak te wachten; een subagent
die dat toch doet, hervat je met één SendMessage. Wacht zelf zonder te pollen.

Omgeving: export op ~/Development/nlriochecker/data/gwsw_orox_ttl/dewoldenhoogeveen_orox.ttl
(zet GWSW_OROX_FIXTUREPAD daarop voor scripts/benchmark.py en de zwaar-tests). Lens-scripts
staan in ~/.local/share/Trash/files/gwsw-orox-helpers-onderzoek/2026-09-04-archperf/prototypes/;
kopieer die map naar je scratchpad en zet de BRON-paden met sed op het exportpad; zet niets
terug. Deze sessie draait headless (`claude -p`): er is geen terminal, dus schrijf je
stavaza-tabellen en het slotrapport ook naar docs/agents/afk-regie-sessie3-slotrapport.md in de
repo (overschrijf het bestand na elke afronding met de actuele stand en commit het mee met de
issue-commit, zodat het altijd klopt en de auteur het op GitHub kan lezen).

## Deel 2 — release 0.2.3 als GitHub-Release, ZONDER PyPI (alleen als deel 1 volledig groen is)

Harde regel (CLAUDE.md): **geen PyPI- of TestPyPI-interactie, nooit**. Publiceren is een
GitHub-Release met de wheel en de sdist als assets; `.github/workflows/release.yml` doet dat
sinds 05-09 zonder PyPI-schakels (poort → controle → github-release).

Volg CLAUDE.md, Werkwijze, "Een versie uitbrengen", letterlijk. Op dev met een schone, groene
werkboom: `uv version --bump patch` (pyproject.toml en uv.lock), in CHANGELOG.md de sectie
`## [Unreleased]` omzetten naar `## [0.2.3] - <datum van vandaag>` met een verse lege
`## [Unreleased]` erboven, de volledige poort (vijf stappen) plus de zesde stap `uv build &&
uvx twine check dist/* && uvx check-wheel-contents dist/*.whl`, commit `Versie 0.2.3` (alleen
pyproject.toml, uv.lock, CHANGELOG.md), tag `v0.2.3`, `timeout 45 git push --follow-tags`. Dan
een PR van dev naar main (`gh pr create --base main --head dev`), wachten tot de checks
poort (3.12)/(3.13)/(3.14) groen zijn, mergen als **merge-commit** (`gh pr merge --merge`, nooit
squash of rebase, anders hangt de tag naast main), daarna dev weer gelijk aan main zetten
(`git fetch && git merge --ff-only origin/main` op dev, pushen). De release komt vanzelf via
release.yml op de tag; volg die run (`gh run list --workflow release.yml --json databaseId`,
dan `gh run watch $RUN --exit-status`) tot de GitHub-Release er staat en controleer met
`gh release view v0.2.3 --json assets --jq '.assets[].name'` dat de wheel en de sdist eraan
hangen. Nooit met de hand `uv build`-artefacten uploaden, nooit `twine upload`, nooit
`gh release create`, nooit iets richting PyPI. De review-swarm (orox-10x-swarm) sla je over:
de auteur heeft hem niet gevraagd.

Gaat een schakel niet (checks rood, merge geweigerd, release-run rood): niet forceren, geen
`--admin`, geen tweede tag; leg de toestand vast in het slotrapport en stop daar.

## Slot

Schrijf het slotrapport naar docs/agents/afk-regie-sessie3-slotrapport.md en commit het: per
issue wat landde (commit), gemeten getal naast voorspelling, reviewoordeel, open aannames en
uitgestelde minors; de release-keten stap voor stap (bump-commit, tag, PR-nummer, merge-commit
op main, release-run-id, de assets aan de GitHub-Release) en de expliciete bevestiging dat er
géén PyPI-interactie was; eindstand van dev en main; en een stavaza-tabel met emoticons voor
#59–#72. Werk daarna het
geheugen bij (~/.claude/projects/-home-martin-gwsw-orox-helpers/memory/fable-archperf-swarm-20260904.md
en de indexregel in MEMORY.md) met de eindstand van de reeks.
