# Slotrapport AFK-regiesessie 3 (headless, 05-09-2026): #69–#72 en release 0.2.3

Regisseur: Fable 5.1 (hoofdsessie, `claude -p`). Implementers en reviewers: Opus 4.8 via
`subagent_type: opus48`. Dit bestand wordt na elke afronding overschreven met de actuele stand.

## Stand van zaken

| Issue | Onderwerp | Status |
|---|---|---|
| #69 | Klein onderhoud cache.py: herstelpad leest alleen de graaf, één herstelpad in `_geladen`, één basisdetectie (conservatieve route) | ✅ gecommit; review GOEDGEKEURD (3 minors); poort 746 passed, dekking 98,95 %; CI en close volgen direct na de push |
| #70 | (perf) | ⏳ wacht |
| #71 | `CacheUitslag`-veld graaflaadtijd | ⏳ wacht |
| #72 | | ⏳ wacht |
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

## Release 0.2.3

Nog niet gestart.

## Eindstand

Nog niet bereikt.
