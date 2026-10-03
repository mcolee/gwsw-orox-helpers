---
name: onderhoud
description: Verwerkt de lessen van één onderdeel uit docs/lessen.md tot één issue, één branch en één PR met per les een rode test die groen wordt (begrensde zelfverbetering, principe 9 (voorstel) van manifesto.md). Gebruik bij "verwerk de lessen", "onderhoud <onderdeel>" of "/onderhoud". Niet voor een nieuwe functie zonder les: dat is een gewoon issue.
---

# Onderhoud: lessen verwerken

Uitvoering van principe 9 (voorstel) van `manifesto.md`: begrensde zelfverbetering, nooit een
gesloten lus. De lus wijzigt code en voegt tests toe; de eigenaar merget elke PR zelf.
Testcommando's, lint en beschermde paden staan in `.claude/cyclus.toml`; deze skill verwijst
ernaar. De PR gaat naar de basisbranch uit dat bestand (`dev`).

```text
les → rode test → wijziging → groen → volledige suite groen → PR → eigenaar merget
```

## 1. Onderdeel kiezen

Noemt de eigenaar geen onderdeel, vraag er één (AskUserQuestion), uit de koppen in
`docs/lessen.md` met minstens één les. Eén run raakt precies één onderdeel.

## 2. Open PR controleren

`gh pr list --state open --search "Onderhoud lessen: <onderdeel> in:title"`. Staat er al één
open, stop dan en meld die PR. Per onderdeel staat er maximaal één onderhouds-PR open.

## 3. Lezen

Eén keer volledig: de sectie `## <onderdeel>` in `docs/lessen.md`, `CLAUDE.md`,
`docs/architectuur.md` (bij een wijziging over meer dan één module), de module in
`src/gwsw_orox_helpers/`, en `tests/test_lessen_<onderdeel>.py` als dat bestaat.

## 4. Per les een route

Nieuwste les eerst. Kies per les één route:

- **Wijziging**: de les wijst een concrete aanpassing aan.
- **Geen wijziging**: al verwerkt, achterhaald of een eenmalig incident zonder structurele
  oorzaak. Noteer waarom.
- **Vraag aan de eigenaar**: dubbelzinnig, een keuze die de agent niet mag maken (principe 7),
  of de les raakt iets uit "Beschermd". Raakt de les een bestaand contract dat nlriochecker
  importeert, dan stopt de lus altijd hier (CLAUDE.md, Harde regels). Formuleer één gerichte
  vraag.

## 5. Issue en branch

1. `gh issue create --title "Onderhoud lessen: <onderdeel>" --label ready-for-agent`. Body: per
   les de route en de reden.
2. `git switch -c issue-<nr>-onderhoud-<onderdeel>`, vanaf de basisbranch.

## 6. Rood, wijzigen, groen

Per les met route "wijziging":

1. **Rood.** Een nieuwe testfunctie in `tests/test_lessen_<onderdeel>.py` (maak het bestand aan
   als het ontbreekt; vorm: een bestaand testbestand van dit onderdeel). Draai alleen die
   test: `uv run pytest tests/test_lessen_<onderdeel>.py::<test>`. Hij faalt, om de reden die de
   les noemt. Zonder rood bewijs weet niemand of de wijziging iets oplost.
2. **Wijzigen.** Alleen additief: nieuwe functies of nieuw gedrag achter een nieuwe parameter;
   nooit een bestaande signatuur, retourvorm of gedrag dat nlriochecker gebruikt.
3. **Groen.** Dezelfde test slaagt.
4. **Maximaal twee pogingen.** Niet groen na twee pogingen: draai de wijziging én de nieuwe test
   terug. De les wordt een "vraag aan de eigenaar", met de testcode in de vraag.

Na de laatste les: de testopdracht `test.volledig` en de opdrachten in `test.lint` uit
`.claude/cyclus.toml`. Geen andere test wordt rood; anders telt de veroorzakende les als
mislukte poging. Leest de package een andere uitkomst dan vroeger, regenereer dan de generator
die je raakt en commit het gegenereerde bestand mee (CLAUDE.md, Werkwijze).

## 7. Verdachte winst

Meld in de PR "verdacht, extra controle nodig" als één hiervan geldt:

- meer dan twee rode tests worden groen door één wijziging;
- een functie of bestand verliest meer dan een derde van zijn regels;
- de diff verwijdert een controle, guard of waarschuwing (bijvoorbeeld de `logging.warning` bij
  een onbekende GWSW-versie) of verlaagt de dekking.

Een grote sprong komt vaker van een uitgeholde regel dan van een betere uitkomst.

## 8. Lessen bijwerken

Haal uit `docs/lessen.md` elke les met route "wijziging" (groen) of "geen wijziging". Een
"vraag aan de eigenaar" blijft staan tot het antwoord er is. Een "niet bevestigde" les blijft
staan met `(toegepast, niet bevestigd)` erachter.

## 9. Commit en PR

1. Eén commit: code, nieuwe test, `docs/lessen.md`, een regel onder `## [Unreleased]` in
   `CHANGELOG.md`, zo nodig `CLAUDE.md`-documentatie van een nieuwe functie (alleen de
   beschrijving, nooit de werkregels). Geen versiebump: uitbrengen is handwerk van de auteur.
   Boodschap eindigt met `Closes #<nr>`.
2. `timeout 45 git push -u origin <branch>`; PR naar de basisbranch met titel "Onderhoud
   lessen: <onderdeel>". Body: `Closes #<nr>`; per les route, reden en testnaam (rood vóór,
   groen na); niet bevestigde lessen; verdachte winst; open vragen.
3. CI-keten uit `~/.claude/CLAUDE.md` (`gh run watch <id> --exit-status`).
4. Merge nooit zelf.

## Beschermd

De lus wijzigt deze nooit, ook niet als een les erom vraagt; zo'n les wordt een vraag aan de
eigenaar. De volledige lijst staat in `.claude/cyclus.toml` onder `[beschermd]`
(`generiek` en `domein`). In het kort:

- `manifesto.md`, `CLAUDE.md` (werkregels) en `.claude/skills/onderhoud/`: de lus wijzigt
  haar eigen regels niet.
- `.github/workflows/`, `tests/conftest.py` en elke bestaande testfunctie. Een nieuwe
  testfunctie in `tests/test_lessen_<onderdeel>.py` toevoegen mag.
- De meetlat van deze package: de gebundelde GWSW-ontologieën en -indexen, de publieke API
  die nlriochecker importeert, de dekkingsdrempel en de drifttests.
- Geen PyPI-interactie, nooit, en geen release of tag: dat is de auteur.

## Harde grenzen

| Verleidelijke gedachte | Tegenargument |
|---|---|
| "De PR is klein, ik merge hem zelf." | De eigenaar merget elke PR. |
| "Deze bestaande test is te streng; ik pas hem aan." | Dat is de eigen meetlat wijzigen. Vraag aan de eigenaar. |
| "Geen rode test, maar de fix is evident." | Zonder rood bewijs is de les "niet bevestigd". |
| "Ik neem ook de lessen van een ander onderdeel mee." | Eén run, één onderdeel. |
| "Dit is een kleine signatuurwijziging, nlriochecker merkt het niet." | nlriochecker mag nooit breken. Vraag aan de eigenaar. |
| "Ik bump de versie en tag meteen." | Uitbrengen is handwerk van de auteur. |
