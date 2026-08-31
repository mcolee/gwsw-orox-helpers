# AFK-regie #36 → #37 → #32 → release 0.2.1 — ledger (git-ignored)

Start: 2026-08-31 ~09:50, dev @ 265a762 (na revert van de Opus 5-landing van #36 en gitignore-commit 05393f3).
Regie: Fable 5. Implementers/reviewers: `subagent_type: opus48` (claude-opus-4-8, lokale agentdefinitie).
Briefs/rapporten: scratchpad/afk/. Auteursbeslissingen vooraf:
- #36: spec §2 letterlijk (schrijven vóór de bewaker, op het object); invariant "object erin ⇔ ≥1 onleesbare literaal".
- Volgorde #36 → #37 → #32 (3 sequentiële agents voor #32: a bundels/index/bronnen, b detectie/namen/lagen, c fixtures/drift/CLAUDE.md/CHANGELOG).
- Release 0.2.1 als PATCH (auteur, expliciet), merge-commit-PR naar main. Review-swarm: niet (patch, geen goedkeuring gevraagd).

## Preflight-conflictscan
| paar | produceert/consumeert | bevinding |
|---|---|---|
| #36 ↔ #37 | beide raken `inlezen.py` (`_read_nodes`); #37 raakt `_orientations_of_class` | sequentieel; geen inhoudelijk conflict. Met §2-letterlijk is `geometry_errors` volgorde-onafhankelijk, `node.point` niet → #37 blijft nodig. |
| #37 ↔ #32 | #37 verandert welke orientatie "eerst" is; #32 genereert nieuwe 1.7-fixtures + baselines | #37 eerst, zodat de 1.7-baseline één keer met sorted() wordt vastgelegd. 1.6-fixtures: drift controleren in #37 (spec §6). |
| #36 ↔ #32 | #32 aanname: "#36 landt vóór deze issue en raakt inlezen.py" | klopt met de volgorde. |
| #32 intern | taak 3 (namen-resolver) vs Harde rand 1 (`dataset.GWSW` gepind) | resolver ernaast; pin blijft. Taak 1 (`maak_gwsw_index.py` prefixfilter uit constante) → moet basis uit de graaf halen (comment 2 van 31-08). |
Ruling: geen worktree — CLAUDE.md/afk-regie.md schrijven `dev` voor en er loopt geen tweede sessie; kost: geen.

## Status per issue
| # | status | commit | CI | meting vs voorspelling | minors (uitgesteld) |
|---|---|---|---|---|---|
| 36 | implementer DONE 30bac60 (556 passed, 99,37%, inlezen 100%); review opus48 loopt | 30bac60 | — | sleutels {PutC,L1} n=2 ✓; subset(alles)==bron ✓; sweep: 4 lezers alleen len()/bool ✓ | — |
| 36 | GESLOTEN | 30bac60 | 33371890938 groen (3.12+3.13) | zie boven; review Approved, 1 minor (point bij kapot-eerst = None → #37) | nlriochecker-tests test_toetsrun.py:504 / test_integration.py:193 tellen objecten i.p.v. orientaties zodra de dep bumpt — bij release melden |
Ruling (regie): #32 gesplitst in a (bundels/index/bronnen/CLAUDE.md-drift, taak 1+7-deels+8), b (1.7-fixtures + baselines, taak 6+7), c (detectie/namen/lagen/round-trip/CHANGELOG, taak 2-5+9). Volgorde a→b→c zodat c's tests de 1.7-fixtures hebben. Kost bij fout: c moet fixtures of baselines bijstellen.
Ruling (regie, 32c-ontwerp): basis meegeven via additief attribuut op GraafIndex i.p.v. handtekeningwijziging op de gepinde parts_of/aspects_of; `namen`-constanten blijven 1.6, termenset ernaast. Kost bij fout: agent meldt BLOCKED en het ontwerp wordt herzien.
| 37 | implementer DONE 132c389 (557 passed, 99,37%); review opus48 loopt | 132c389 | — | seeds 0-4 identiek met fix; zonder fix seed 3 wijkt af (point/orientatie) ✓; andere frozenset-lussen = membership ✓ | — |
| 37 | GESLOTEN | 132c389 | 33373088035 groen | zie boven; review Approved, 3 minors (fouttekst-determinisme breder dan gemeld; meting dekt dat geval niet; list vs frozenset in test) | — |
| 32a | implementer DONE c3596d2+fd87276 (566 passed, 99,37%); review opus48 loopt | c3596d2, fd87276 | — | 1.6-index 3316 termen, 1.7-index 3485 (+185/−16); 1.6-blokken byte-identiek; basis uit gwsw:-prefix; faalt bij 0 termen | rdflib-warning 'Invalid isoformat 20262-05-13' in 1.7-bundel (upstream, as-is) — melden aan auteur |
| 32a | review Approved (3 minors: fail-hard-paden generator ongetest/buiten cov; drifttests hardcoded ["1.6","1.7"] i.p.v. GEBUNDELDE_VERSIES; `_bundels() -> list` kaal); gepusht | fd87276 | 33374501115 groen | — | minors → slotrapport |
| 32b | implementer DONE dbe3fb9+a2682cf (585 passed, 99,37%); review opus48 loopt | dbe3fb9, a2682cf | — | 16 fixtures in ttl17 (alleen prefixregel anders), ttl/ byte-gelijk; 1.7: 66.664 tripels, 3485 eigen IRI's, 2167 klassen; REV/Infiltratiekoffer/Omhulling in, Infiltratiereservoir/Leidingomhulling uit | — |
| 32b | review Approved (3 minors: tautologie-assert test_dataset.py:239; IRI-telling 1.7 niet like-for-like met 1.6 (gedocumenteerd); baselines losse functies tot deel c); gepusht | a2682cf | 33375797838 groen | — | minors → slotrapport |
