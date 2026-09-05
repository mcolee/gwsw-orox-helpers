# Slotrapport AFK-regiesessie 3 (headless, 05-09-2026): #69–#72 en release 0.2.3

Regisseur: Fable 5.1 (hoofdsessie, `claude -p`). Implementers en reviewers: Opus 4.8 via
`subagent_type: opus48`. Dit bestand wordt na elke afronding overschreven met de actuele stand.

## Stand van zaken

| Issue | Onderwerp | Status |
|---|---|---|
| #69 | Klein onderhoud cache.py: herstelpad leest alleen de graaf, één herstelpad in `_geladen`, één basisdetectie (conservatieve route) | ✅ 971efc4; review GOEDGEKEURD (3 minors); poort 746 passed, dekking 98,95 %; CI-run 33980434158 groen; gesloten |
| #70 | Restposten koud laadpad: `_structural_diff`-houders hergebruiken (a), gebundelde ontologie als GraafIndex-pickle (b) | ❌ open gelaten: gebouwd, poort groen, review GOEDGEKEURD, maar end-to-end in twee onafhankelijke reeksen niet eenduidig (~0,1–0,2 s per deelstap op ~18 s, ruis 0,5–0,9 s); subfase wél eenduidig (≈ −0,39 s); auteursbeslissing; patch bewaard |
| #71 | Beloften bijstellen, gesloten routes vastleggen, fasetabel in benchmark.py, `CacheUitslag.graaf_seconden` (additief) | ✅ 4667f91; review GOEDGEKEURD (1 minor); poort 749 passed, dekking 98,95 %; CI-run 33985540612 groen; gesloten |
| #72 | Versie-juiste str-laag verbreden tot de zes graafvragen van de afnemer, plus aanbevolen kern in `docs/afnemers.md` | ✅ 931b176; review GOEDGEKEURD MET MINORS (2 docs-minors, door de regie gefixt); poort 763 passed, dekking 98,91 %; CI-run 33986984317 groen; gesloten |
| Release 0.2.3 | GitHub-Release, geen PyPI | ❌ gestopt bij de laatste schakel: versiecommit 9917590, tag `v0.2.3` gepusht, PR #76 open met de drie poort-checks groen, **niet gemergd**; release-run 33987225498 rood op de job `github-release` (`gh release create` zonder checkout: "not a git repository"); fix in `release.yml` op `dev` (bc74401); géén PyPI-interactie |

## Per issue

### #69 — cache-opruiming (Substantieel; Opus 4.8-implementer + Opus 4.8-reviewer)

- **Landde:** (a) `cache._herlees_graaf` leest alleen de datasetgraaf via `bestand._parse`
  binnen `_gc_uit`; `ontology_paths` uit handtekening en `partial`. (b) één herstelpad in
  `LuieGraaf._geladen`. (c) conservatieve route uit §6 van het issue (regiebeslissing conform
  reeksbrief): `_dataset_basis_uit_kop` neemt de láátste `gwsw:`-treffer in het 8 KB-venster,
  net als de lader; #52 en zijn test blijven staan; nieuwe test op een herdeclarerende bron.
  Docstrings, `docs/architectuur.md` en CHANGELOG bijgewerkt.
- **Meting:** geen perf-poort (het herstelpad is zeldzaam); winst is niet gemeten, conform §5.
- **Object-identiteitsaanname (§6):** bevestigd door implementer én reviewer in `laden.py`
  (regels 210 → 261, geen graafmutatie in `inlezen`/`model`).
- **Review:** GOEDGEKEURD, drie minors (ledger): een `None`-pickle raakt nu een `assert` in
  plaats van een `TypeError` (pathologisch); een herdeclaratie vóórbij 8 KB blijft uiteenlopen
  (docstring noemt dat "veilige kant", strikt te optimistisch); `_parse` gooit geen
  `InhoudError` op een knooploze bron zoals `load_dataset` (onbereikbaar op het herstelpad).
- **Afwijking van de issue-body:** de voorkeursroute van (c) (schrappen van
  `_dataset_basis_uit_kop`) is niet gekozen; de CHANGELOG-regel zegt dus niet "hasht weer
  alle bundels".

### #70 — restposten koud laadpad (Substantieel; Opus 4.8-implementer + Opus 4.8-reviewer met onafhankelijke hermeting)

- **Niet geland; open gelaten** conform §5/§6 van het issue en de reeksbrief ("niet aangetoond
  = open laten, niet mergen"). `dev` bleef op 971efc4.
- **Gebouwd en groen:** (a) `inlezen._structural_diff_uit` + houder-teruggevende
  `_read_nodes`/`_read_conduits`, `laden.load_dataset` geeft de houders door; (b)
  `bronnen`-paden, `laden._graafindex_hash`/`_gebundelde_graafindex` (sha256-poort over
  TTL + `graaf.py` + rdflib-versie vóór elke `pickle.load`), `scripts/maak_gwsw_index.py`
  schrijft per bundel pickle + `.sha256`, drifttests bidirectioneel, pickle in wheel én sdist.
  Poort 758 passed, dekking 98,95 %, packaging-stap groen. Review GOEDGEKEURD (2 minors).
- **Meting naast voorspelling** (voorspeld ~0,2 s per deelstap, ~2 % samen): end-to-end
  `scripts/benchmark.py --paden load_dataset`, gepaard, om en om, vers proces, referentie via
  worktree op `PYTHONPATH`:
  - (a) HEAD → (a): implementer n=7 niet eenduidig (18,225 > 17,780; 5/7 gunstig, mediaan
    −0,17 s); reviewer n=5 niet eenduidig (18,000 > 17,618; 3/5 gunstig, gem. −0,12 s).
  - (b) (a) → (a)+(b): implementer n=5 niet eenduidig met 4 ms (17,781 > 17,777; 5/5 gunstig,
    gem. −0,21 s); reviewer n=5 niet eenduidig (18,217 > 17,672; 4/5 gunstig, gem. −0,08 s).
  - Subfase (reviewer, n=5, eenduidig): (b) depickle 0,047–0,049 s vs parse 0,322–0,337 s;
    (a) 0,436–0,456 → 0,324–0,343 s. Samen ≈ −0,39 s = de voorspelling.
- **Regiebeslissing:** de reviewer adviseerde landen op de subfase-cijfers; de regie heeft de
  letter van het protocol gevolgd (meetstraat is end-to-end; §6: niet gepaard-eenduidig =
  gaat niet mee). Het is een auteursbeslissing: subfase-meting als acceptatie aanvaarden en de
  patch toepassen, óf sluiten als "gemeten, end-to-end niet aantoonbaar".
- **Bewaard:** `~/gwsw-orox-helpers-onderzoek/2026-09-05-sessie3/70ab.patch` (volledig, incl.
  binaire pickles; `git apply --binary` op 971efc4), `70a.patch`, beide rapporten en alle ruwe
  benchmark-JSON's. Een zijtak pushen werd door de auto-mode-classifier geblokkeerd.
- **Les voor de meetstraat:** een effect van ~1 % op een pad van ~18 s is met "traagste
  experiment < snelste referentie" op deze machine niet aantoonbaar; toekomstige restposten-
  issues horen een subfase-acceptatie of een grotere n-met-mediaan-regel te krijgen.

### #71 — beloften bijstellen, gesloten routes, fasetabel, `CacheUitslag.graaf_seconden` (Substantieel; Opus 4.8 + Opus 4.8)

- **Landde:** (a) docstrings `cache.py` (module, `LuieGraaf`) en `docs/architectuur.md` op de
  huidige stand (graaf lui-maar-altijd; warm 9,9 → ~2,7 s sinds #59); (b) geen wijziging
  nodig: `clip/orkest.py` zegt sinds #61 al N+1 (met `bereikcontrole` N+2); (c)
  architectuur-sectie "Store is geen derde pad" met de cijfers uit de issue-body, CONSTRUCT-
  serialize als open noot, drifttest `"24.20"^^xsd:decimal` byte-gelijk door `schrijf_orox`
  (pyoxigraph schrijft de Turtle-korting `24.20`, lexicaal identiek); (d) herformuleerde
  lui-belofte in `docs/architectuur.md` en `clip/stroom.py`; (e) fork-bnode-alinea in de
  `rdfmotor`-docstring (pyoxigraph 0.5.9 uit `uv.lock`); (f) sectie "Wat gemeten is en bewust
  niet gedaan" (fork/spawn, Rust rang 18/19), zonder "release B"-taal (#73–#75 geschrapt);
  (g) `_faseklok`/`_schrijf_fasetabel` in `scripts/benchmark.py`, alleen onder
  `--profiel-map`, gewone meting ongewijzigd; (h) `CacheUitslag.graaf_seconden: float | None
  = None`, additief achteraan, gevuld via een callback uit `LuieGraaf` na de eerste
  graafaanraking (`object.__setattr__` op de frozen dataclass), pins in
  `tests/test_publieke_api.py` alleen uitgebreid, CHANGELOG-regel.
- **Fasetabel op de export (één run, informatief):** `bestand._parse` 12,08 s (n=2: dataset +
  ontologie), `GraafIndex.vul_uit` 10,77 s (n=2), `_stapel_ontologie` 0,33 s, `_read_nodes`
  2,22 s, `_read_conduits` 2,79 s, `_structural_diff` 0,45 s.
- **Review:** GOEDGEKEURD; één minor (ledger): `cache.py` noemt op twee plekken 7,7 resp.
  7,8 s voor dezelfde grootheid (de body zegt 7,7).
- **Open aanname:** de veldnaam `graaf_seconden` is het voorstel uit de body; de auteur
  bevestigt hem achteraf (§6).

### #72 — versie-juiste str-laag verbreed tot de zes graafvragen (Substantieel; Opus 4.8 + Opus 4.8)

- **Landde:** acht additieve methoden op `GwswDataset` in `model.py` (`houders`, `dragers`,
  `kenmerkinstanties`, `knopen_van`, `strengen_van`, `knopen_van_streng`, `valt_onder`,
  `typen_kort`), alle versie-juist via `self.termen`; `namen.korte_naam` publiek met `_short`
  als privé-alias (hetzelfde object). Geen wijziging aan `netwerk`/`inlezen`/`domein`/
  `dataset`; importrichting intact. `HANDTEKENINGEN` in `tests/test_publieke_api.py` alleen
  uitgebreid; fixture-acceptatie op `tests/fixtures/ttl17/mini_orox.ttl` (niet-nul waar het
  1.6-constanten-idioom nul leest) en de 1.6-controle (gelijk aan de oude weg).
  `docs/afnemers.md`: aanbevolen kern van 33 namen plus de "te vermijden"-lijst zonder
  verwijdering of release te beloven; `docs/architectuur.md`-alinea; CHANGELOG-regel.
- **nlriochecker-controle (§6, alleen gelezen):** de vereniging `houders ∪ dragers` is op één
  plek nodig (`nulbevinding.py`, `_insluitend`); conform regiebeslissing géén derde methode,
  de afnemer verenigt twee lijsten. `valt_onder` wijkt bewust af van de alfabetische
  `_soortnaam` bij de afnemer (`attributen.py`, `randvoorzieningen.py`): meest-specifiek,
  gelijk aan `beheerobjecttype`. Dat is een gedragsverschil voor de afnemer bij een
  toekomstige omzetting.
- **Meting:** geen perf-issue; geen meting.
- **Review:** GOEDGEKEURD MET MINORS. Beide minors waren docs-only in `docs/afnemers.md` en
  zijn door de regie vóór de commit gefixt: (1) de tekst claimde dat de rdflib-typed
  *methoden* op 1.7 stil nul lezen; dat doen alleen de geëxporteerde 1.6-constanten (de
  methoden leiden hun IRI's uit de gedetecteerde basis af, bewezen op de 1.7-fixture), dus de
  reden voor de str-laag is daar ergonomie, niet correctheid; (2) `graph_is_a` is een
  lidmaatschapstest en stond op `valt_onder` gekoppeld; nu een eigen rij.
- **Open aanname:** de precieze kernlijst (33 namen) is een documentatiekeuze voor de auteur.

## Release 0.2.3 — stap voor stap

Voorwaarde "deel 1 volledig groen": de regie las dat als *werkboom, poort en CI groen en elk
issue volgens zijn eigen protocol afgehandeld*; #70 bleef open op de meetregel die het issue
zelf stelt, wat de release niet blokkeert (restposten, ~2 %, geen contract). Wie dat anders
leest, kan PR #76 laten staan.

1. **Slotrapport-commit** b864404 (docs) vóór de bump, zodat de release hem draagt.
2. **Bump:** `uv version --bump patch` → 0.2.3 (`pyproject.toml`, `uv.lock`); `CHANGELOG.md`:
   `## [Unreleased]` → `## [0.2.3] - 2026-09-05` met een verse lege `## [Unreleased]` erboven.
3. **Poort op de bumpstand, alle zes stappen groen:** ruff check "All checks passed", ruff
   format "75 files already formatted", mypy "no issues found in 37 source files", pytest
   763 passed, dekking 98,91 % (≥ 95), `uv build` + `twine check` PASSED + `check-wheel-contents`
   OK (0.2.3-wheel en -sdist).
4. **Versiecommit** `Versie 0.2.3` = **9917590** (alleen `pyproject.toml`, `uv.lock`,
   `CHANGELOG.md`).
5. **Tag** `v0.2.3` (annotated, zoals `v0.2.2`; een eerste lichte tag werd door
   `--follow-tags` niet meegestuurd en is vóór de push vervangen door de annotated tag op
   dezelfde commit — er is dus maar één tag geweest op de remote) → `git push --follow-tags`:
   `465bca01…` → `refs/tags/v0.2.3`, op 9917590.
6. **PR #76** `dev` → `main` ("Versie 0.2.3"): de drie verplichte checks `poort (3.12)`,
   `poort (3.13)`, `poort (3.14)` groen; `mergeable: MERGEABLE`, `mergeStateStatus: UNSTABLE`
   omdat de niet-verplichte check `github-release` rood is. **Niet gemergd**: de opdracht zegt
   bij een rode release-run "niet forceren, vastleggen, stop daar".
7. **Release-run 33987225498** (`release.yml` op de tag): `poort` 3.12/3.13/3.14 groen,
   `controle` groen (tag = projectversie, build, twine, check-wheel-contents, rooktest van de
   wheel in een verse venv), **`github-release` rood**. Oorzaak uit de joblog: de job doet bewust
   geen checkout en `gh release create … --verify-tag` probeert de repo uit `.git` af te leiden:
   `failed to run git: fatal: not a git repository`. Er staat dus **geen** GitHub-Release
   `v0.2.3` (`gh release view v0.2.3` → "release not found") en geen assets.
8. **Fix, niet geverifieerd in CI:** commit **bc74401** op `dev` geeft `-R "$GITHUB_REPOSITORY"`
   mee aan `gh release create`, zodat `gh` alles via de API doet. Een workflow draait uit de
   getagde commit, dus deze fix helpt pas bij een nieuwe tagpush; een tweede tag was verboden.
9. **Bevestiging: er is géén PyPI- of TestPyPI-interactie geweest** — geen `twine upload`,
   geen `gh release create` met de hand, geen handmatig geüploade artefacten; `release.yml`
   bevat geen publish-job. De lokaal gebouwde `dist/` is direct na de controle verwijderd.

**Wat de auteur nog moet beslissen (in deze volgorde):**
- PR #76 mergen als merge-commit (`gh pr merge 76 --merge`), daarna `dev` gelijk aan `main`.
  De PR bevat nu ook bc74401 (de `release.yml`-fix).
- De tag `v0.2.3` staat op 9917590, vóór de fix. Om de release alsnog te laten lopen: de
  remote tag verwijderen en opnieuw zetten op de merge-commit (of op bc74401) en pushen — de
  workflow leest dan de gefixte `release.yml` — óf bumpen naar 0.2.4. Beide zijn een
  auteursbeslissing; de sessie heeft geen tweede tag gezet.

## Eindstand

- **`dev`** = bc74401 (`release.yml`-fix) ← 9917590 (`Versie 0.2.3`, tag `v0.2.3`) ← b864404
  (slotrapport) ← 931b176 (#72) ← 4667f91 (#71) ← 971efc4 (#69) ← 3977cb7 (start). Werkboom
  schoon. Laatste groene toets-CI op een issue-commit: 33986984317 (931b176); de dev-pushes
  9917590 en bc74401 draaien dezelfde poort (zie de checks op PR #76).
- **`main`** = d3ac97a (0.2.2), ongewijzigd; PR #76 open.
- **Poort op de eindstand** (gedraaid op 9917590; bc74401 raakt alleen `release.yml`): 763
  passed, dekking 98,91 %, packaging groen.
- **Uitgestelde minors (ledger):** #69: `None`-pickle raakt nu een `assert`; herdeclaratie
  vóórbij 8 KB blijft uiteenlopen (docstring "veilige kant" te optimistisch); `_parse` gooit op
  het herstelpad geen `InhoudError`. #70 (bewaarde code): pickle-inhoudstest alleen `len` +
  basis; `_graafindex_hash` bindt `_SnellePickler` niet. #71: 7,7 vs 7,8 s in twee docstrings
  van `cache.py`. #72: geen (beide docs-minors gefixt).
- **Open aannames voor de auteur:** naam `CacheUitslag.graaf_seconden` (#71 §6); de kernlijst
  van 33 namen in `docs/afnemers.md` (#72 §6); #70: subfase-acceptatie of sluiten; de
  release-afronding hierboven.
- **Blokkades van de auto-mode-classifier:** één keer, bij het pushen van een zijtak met de
  #70-code; niet herhaald, de patch staat lokaal in
  `~/gwsw-orox-helpers-onderzoek/2026-09-05-sessie3/`.

## Stavaza reeks #59–#72

| Issue | Onderwerp | Status |
|---|---|---|
| #59 | Cyclische GC stil om beide `pickle.load` in de cache: graaflading 7,7 → 2,75 s | ✅ sessie 1 |
| #60 | Invoerbuffers loslaten in `bestand._parse`, streamende weg bij zuivere UTF-8: piek load −17 % | ✅ sessie 1 |
| #61 | `clip_orox` laat de basisdetectie-stroom los vóór het plan: N+2 → N+1, piek −215 MiB | ✅ sessie 1 |
| #62 | Hybride binnencontainers in `GraafIndex`: piek load 1202 → 842 MiB | ✅ sessie 1 |
| #63 | Snelpad-pickler voor de graafcache via `dispatch_table`: 13–20 % van de graaflading weg | ✅ sessie 1 |
| #64 | Naad plan→stroom als positietabel | ✅ sessie 2 |
| #65 | `merge_orox`: positietabel uit de scanronde | ✅ sessie 2 |
| #66 | Hercodeerstroom bij terugvalcodering: 347 → 31 MiB per passage | ✅ sessie 2 |
| #67 | `dataset.py` hersneden in `model`, `laden`, `vulwaarden` | ✅ sessie 2 |
| #68 | `ontologie` leest zijn properties via `namen.termen_voor` | ✅ sessie 2 |
| #69 | Cache-opruiming: herstelpad, één herstelpad in `_geladen`, laatste `gwsw:`-declaratie | ✅ 971efc4 |
| #70 | Restposten koud laadpad (a)+(b) | ❌ open: end-to-end niet eenduidig in 2 reeksen; subfase −0,39 s; patch bewaard; auteursbeslissing |
| #71 | Beloften bijgesteld, gesloten routes, fasetabel, `CacheUitslag.graaf_seconden` | ✅ 4667f91 |
| #72 | Versie-juiste str-laag: acht graafvragen, `korte_naam`, aanbevolen kern (33) | ✅ 931b176 |
| Release 0.2.3 | tag + PR #76 + GitHub-Release | ❌ tag en PR staan; release-job rood (fix bc74401 op `dev`); geen PyPI |
