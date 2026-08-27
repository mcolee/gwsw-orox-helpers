# Triage-labels

De skills spreken in vijf canonieke triagerollen. Dit bestand koppelt die rollen aan de
labelstrings die deze issuetracker daadwerkelijk gebruikt.

| Label in mattpocock/skills | Label in onze tracker | Betekenis                                          |
| -------------------------- | --------------------- | -------------------------------------------------- |
| `needs-triage`             | `needs-triage`        | De beheerder moet dit issue nog beoordelen          |
| `needs-info`               | `needs-info`          | Wacht op meer informatie van de melder              |
| `ready-for-agent`          | `ready-for-agent`     | Volledig gespecificeerd, klaar voor een AFK-agent   |
| `ready-for-human`          | `ready-for-human`     | Vraagt om implementatie door een mens               |
| `wontfix`                  | `wontfix`             | Wordt niet opgepakt                                 |

Noemt een skill een rol ("zet het AFK-klaar-label"), gebruik dan de labelstring uit de
rechterkolom.

In `mcolee/gwsw-orox-helpers` bestaan `ready-for-agent` en `wontfix` al; de drie andere maak je
aan zodra je ze voor het eerst nodig hebt (`gh label create <naam> --description "..."`).
Daarnaast kent dit repo één eigen label: **`geparkeerd`** — pas oppakken na een expliciet
startsein van de auteur. Een `geparkeerd`-issue pakt een AFK-agent nooit uit zichzelf op, ook
niet als het daarnaast `ready-for-agent` draagt.

Pas de rechterkolom aan zodra je een eigen vocabulaire gaat voeren.
