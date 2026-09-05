# AFK-regie: de Fable-archperf-reeks (#59–#75)

Aanvulling op het sjabloon `docs/agents/afk-regie.md`; dat blijft de lus, dit is wat deze
reeks anders maakt. De issues komen uit de architectuur- en performance-swarm van 04/05-09-2026
(`.claude/workflows/orox-fable-archperf.js`; rapport, plan.json en de prototypes van de
lenzen in `~/gwsw-orox-helpers-onderzoek/2026-09-04-archperf/`). De auteur nam de beslissingen
op 05-09 in een grill; ze staan als kaart bovenaan elke issue-body en hieronder.

## Bezetting

- **Regisseur: de Fable-hoofdsessie**, vers gecleared, in `/home/martin/gwsw-orox-helpers`.
- **Implementers en reviewers: Opus 4.8** via `subagent_type: opus48`, voor elk issue van deze
  reeks. Alle issues raken cache, graaf, bestand, dataset of de cliplaag en zijn daarmee
  Substantieel; alleen #73 (CLAUDE.md-alinea) is docs-only. Meld bij elke dispatch het model.
- **Vijf issues per sessie**, dan een slotrapport en `/clear`. De staat leeft in git, de issues
  en het geheugen; er gaat niets verloren.

## Volgorde en sessies

| Sessie | Issues | Afhankelijkheden |
|---|---|---|
| 1 | #59 → #60 → #61 → #62 → #63 | #63 ná #62 (picklevorm) |
| 2 | #64 → #65 → #66 → #67 → #68 | #65 ná #64 (positietabel-vorm) |
| 3 | #69 → #70 → #71 → #72 → #73 | #70 ná #62; #73 is de laatste stap vóór release A |
| auteur | **release A = 0.2.3**: `uv version --bump patch`, CHANGELOG, tag `v0.2.3`, PR naar `main` | zie `CLAUDE.md`, Werkwijze |
| 4 | nlriochecker: tag-bump naar A + migratieclusters (issues daar nog aan te maken) | ná release A |
| 5 | #74 (verwijdering, contract) → release B (auteur; minor, want breuk in de publieke API vóór 1.0) → nlriochecker bumpt naar B | ná sessie 4 |
| los | #75 (onderzoek tussenvorm; rapport, geen merge) | past in elke sessie met ruimte |

Eén issue = commit + push + CI groen + comment + close vóór het volgende. Een issue dat niet
groen of niet aangetoond is, blijft open met een comment die de echte toestand beschrijft; ga
door met het volgende issue dat er niet op leunt.

## Wat de perf-issues extra eisen (#59–#66, #70)

- **Meetprotocol is een acceptatie-eis, geen suggestie.** Gepaard (referentie en experiment om
  en om), n ≥ 3, eenduidig (traagste experiment sneller dan snelste referentie), en byte-gelijke
  uitvoer (sha256) waar de schrijfweg geraakt wordt. Meetstraat: `scripts/benchmark.py` en de
  lens-scripts die het issue noemt (onder `prototypes/<lens>/` in de onderzoeksmap). Export:
  `~/nlriochecker/data/gwsw_orox_ttl/dewoldenhoogeveen_orox.ttl`. **Niet aangetoond = melden
  en open laten**, niet mergen.
- **Eén implementer tegelijk.** De machine heeft vier cores; twee metingen naast elkaar maken
  elkaars cijfers waardeloos. Dispatch nooit een tweede meetagent terwijl er een loopt.
- **De implementer plakt de ruwe metingen** (alle n runs, referentie en experiment) in zijn
  rapport én in de issue-comment; de regisseur controleert de eenduidigheid zelf op die cijfers.
- **#62 heeft een dubbele eis:** koud laden niet meetbaar slechter (+4% was gemeten) én het
  warme pad met de kleinere graafpickle gemeten sneller. Faalt een van de twee, dan sluit het
  issue zonder merge, met de cijfers.
- **#62 en #63 veranderen het cacheformaat** (graaf.py-hash respectievelijk `LADER_VERSIE`);
  eenmalige herbouw is bedoeld. Controleer dat de CHANGELOG-regel dat zegt.
- **De reviewer toetst ook de meting:** is ze gepaard, is ze eenduidig, klopt de ordegrootte met
  de voorspelling in het issue.

## Beslissingen van de auteur (05-09) die een agent niet heropent

- Tijd is het doel, geheugen bijvangst. Geen parallellisme (fork/spawn), geen Rust-dependency,
  geen LD1 (de bron in het geheugen). Deze routes zijn gemeten en staan in #71 als bewust niet
  gedaan; een agent stelt ze niet opnieuw voor.
- De lui-belofte wordt geherformuleerd, niet omgekeerd: de bron zelf komt nooit in het geheugen,
  het plan mag een positietabel van O(1) byte per quad dragen (#64, #65 zijn conform).
- GC uit als procesbreed neveneffect op het luie cachepad is akkoord (#59), gedocumenteerd in de
  docstrings van `LuieGraaf._geladen` en `laad_met_cache`.
- `CacheUitslag` krijgt een additief veld met default voor de graaflaadtijd (#71); de pin in
  `tests/test_publieke_api.py` groeit mee, met CHANGELOG-regel.
- Contract (#74): de rdflib-typed functies en álle 1.6-constanten (`GWSW`, `HAS_*`, `KLASSE_*`)
  gaan uit het publieke oppervlak zonder deprecatiefase, en `GwswDataset.graph` wordt een
  protocol; dat mag pas ná release A en ná de nlriochecker-migratie, met CHANGELOG en bump in
  beide repo's en `uv lock` aan de nlriochecker-kant. Tot #73 geland is geldt de Harde regel
  onverkort: raakt een issue eerder een bestaand contract, dan stopt de agent.

## Drie aandachtspunten die de schrijvers vonden (staan in §6 van het issue)

- **#69 deel (c):** "één basisdetectie" door `_dataset_basis_uit_kop` te schrappen draait de
  gerichte-bundel-hash van #52 terug en maakt een bestaande test ongeldig. De agent kiest de
  conservatieve route uit het issue (cache neemt de laatste treffer) tenzij de auteur in een
  comment anders zegt.
- **#62:** `tests/test_dataset.py::_tripels` itereert over de objecten en moet mee met de hybride
  vorm; "slaagt vanzelf" uit het rapport klopt niet.
- **#74:** `GraafLezer` heeft twee leden, `GwswDataset` gebruikt ook `subjects` en
  `heeft_subject`; het veld letterlijk naar `GraafLezer` zetten breekt mypy. Het issue beschrijft
  een breder protocol dat `GraafIndex` en `LuieGraaf` vervullen.

## Slotrapport per sessie

Per issue: wat landde (commit), gemeten getal naast de voorspelling uit het issue (alle runs),
reviewoordeel, open aannames en uitgestelde minors. Dan: eindstand `dev`, poortresultaat, CI, en
de startprompt voor de volgende sessie met de volgende vijf issues.
