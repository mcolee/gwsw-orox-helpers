# Slotrapport AFK-regiesessie 3 (headless, 05-09-2026): #69–#72 en release 0.2.3

Regisseur: Fable 5.1 (hoofdsessie, `claude -p`). Implementers en reviewers: Opus 4.8 via
`subagent_type: opus48`. Dit bestand wordt na elke afronding overschreven met de actuele stand.

## Stand van zaken

| Issue | Onderwerp | Status |
|---|---|---|
| #69 | Klein onderhoud cache.py: herstelpad leest alleen de graaf, één herstelpad in `_geladen`, één basisdetectie (conservatieve route) | ✅ 971efc4; review GOEDGEKEURD (3 minors); poort 746 passed, dekking 98,95 %; CI-run 33980434158 groen; gesloten |
| #70 | Restposten koud laadpad: `_structural_diff`-houders hergebruiken (a), gebundelde ontologie als GraafIndex-pickle (b) | ❌ open gelaten: gebouwd, poort groen, review GOEDGEKEURD, maar end-to-end in twee onafhankelijke reeksen niet eenduidig (~0,1–0,2 s per deelstap op ~18 s, ruis 0,5–0,9 s); subfase wél eenduidig (≈ −0,39 s); auteursbeslissing; patch bewaard |
| #71 | Beloften bijstellen, gesloten routes vastleggen, fasetabel in benchmark.py, `CacheUitslag.graaf_seconden` (additief) | ✅ gecommit; review GOEDGEKEURD (1 minor); poort 749 passed, dekking 98,95 %; CI en close volgen direct na de push |
| #72 | Versie-juiste str-laag verbreden tot de zes graafvragen van de afnemer, plus aanbevolen kern in `docs/afnemers.md` | ⏳ wacht |
| Release 0.2.3 | GitHub-Release, geen PyPI | ⏳ wacht op deel 1 |

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

## Release 0.2.3

Nog niet gestart.

## Eindstand

Nog niet bereikt.
