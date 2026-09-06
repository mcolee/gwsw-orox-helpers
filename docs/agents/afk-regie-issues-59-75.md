# AFK-regie: de Fable-archperf-reeks (#59–#75)

Aanvulling op het sjabloon `docs/agents/afk-regie.md`; dat blijft de lus, dit is wat deze
reeks anders maakt. De issues komen uit de architectuur- en performance-swarm van 04/05-09-2026
(`.claude/workflows/orox-fable-archperf.js`; rapport, plan.json en de prototypes van de
lenzen stonden in `~/gwsw-orox-helpers-onderzoek/2026-09-04-archperf/`; die map staat sinds
05-09 in de prullenbak, `~/.local/share/Trash/files/gwsw-orox-helpers-onderzoek/…` — kopieer
`prototypes/` naar je scratchpad en zet de `BRON`-paden er met `sed` op het exportpad
hieronder; zet niets terug). De auteur nam de beslissingen
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
| 1 | #59 → #60 → #61 → #62 → #63 | #63 ná #62 (picklevorm) — **af 05-09, dev=c7ea09b** |
| 2 | #64 → #65 → #66 → #67 → #68 | #65 ná #64 (positietabel-vorm) — **af 05-09** |
| 3 (headless) | #69 → #70 → #71 → #72, dan **release 0.2.3** als GitHub-Release (tag, merge-commit-PR naar `main`, géén PyPI) | #70 ná #62; opdracht in `afk-regie-sessie3-start.md`, gestart door `afk-regie-sessie3-start.sh` |

**Planwijziging van de auteur (05-09-2026, tijdens sessie 2).** De oorspronkelijke tabel had
release A na #73, een nlriochecker-migratiesessie, #74 (contractverwijdering) met release B, en
#75 (onderzoek tussenvorm). Dat is vervallen: **#73, #74 en #75 zijn verwijderd** uit de tracker,
er zijn geen tussenreleases en geen nlriochecker-migratie in deze reeks, en alles landt op `dev`.
Sessie 3 sluit af met de versiebump naar 0.2.3 en de merge naar `main`; publiceren is sinds
diezelfde dag een Harde regel in `CLAUDE.md`: **alleen een GitHub-Release met wheel en sdist,
nooit PyPI of TestPyPI** (`release.yml` is daarop omgebouwd, 1d94f86). Sessie 3 draait
**headless** (`claude -p`, auto-permissies) via het startscript; de auteur start dat script zelf
in een terminal, omdat de auto-mode-classifier het starten van zo'n sessie vanuit Claude
blokkeert. Het slotrapport van sessie 3 komt in `docs/agents/afk-regie-sessie3-slotrapport.md`.

Eén issue = commit + push + CI groen + comment + close vóór het volgende. Een issue dat niet
groen of niet aangetoond is, blijft open met een comment die de echte toestand beschrijft; ga
door met het volgende issue dat er niet op leunt.

## Wat de perf-issues extra eisen (#59–#66, #70)

- **Meetprotocol is een acceptatie-eis, geen suggestie.** Gepaard (referentie en experiment om
  en om), n ≥ 3, eenduidig (traagste experiment sneller dan snelste referentie), en byte-gelijke
  uitvoer (sha256) waar de schrijfweg geraakt wordt. Meetstraat: `scripts/benchmark.py` en de
  lens-scripts die het issue noemt (onder `prototypes/<lens>/` in de onderzoeksmap). Export:
  `~/Development/nlriochecker/data/gwsw_orox_ttl/dewoldenhoogeveen_orox.ttl` (sinds 05-09;
  `tests/conftest.py` en `scripts/benchmark.py` kennen dat pad, `GWSW_OROX_FIXTUREPAD`
  overschrijft het). **Niet aangetoond = melden
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
- Contract (was #74, **verwijderd 05-09**): de contractverwijdering is uit de reeks; de Harde
  regel geldt onverkort: raakt een issue een bestaand contract, dan stopt de agent.

## Drie aandachtspunten die de schrijvers vonden (staan in §6 van het issue)

- **#69 deel (c):** "één basisdetectie" door `_dataset_basis_uit_kop` te schrappen draait de
  gerichte-bundel-hash van #52 terug en maakt een bestaande test ongeldig. De agent kiest de
  conservatieve route uit het issue (cache neemt de laatste treffer) tenzij de auteur in een
  comment anders zegt.
- **#62:** `tests/test_dataset.py::_tripels` itereert over de objecten en moet mee met de hybride
  vorm; "slaagt vanzelf" uit het rapport klopt niet.
- **#74 (verwijderd):** `GraafLezer` heeft twee leden, `GwswDataset` gebruikt ook `subjects` en
  `heeft_subject`; het veld letterlijk naar `GraafLezer` zetten breekt mypy. Bewaard als
  aandachtspunt voor als de auteur de contractwijziging ooit oppakt.

## Slotrapport per sessie

Per issue: wat landde (commit), gemeten getal naast de voorspelling uit het issue (alle runs),
reviewoordeel, open aannames en uitgestelde minors. Dan: eindstand `dev`, poortresultaat, CI, en
de startprompt voor de volgende sessie met de volgende vijf issues.
