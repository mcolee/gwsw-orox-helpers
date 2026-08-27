# Security

## Kwetsbaarheid melden

Meld een kwetsbaarheid vertrouwelijk via GitHub's **private vulnerability reporting**:
[Security → Report a vulnerability](https://github.com/mcolee/gwsw-orox-helpers/security/advisories/new).
Gebruik geen openbaar issue; details worden pas gedeeld als er een fix is.

Je krijgt binnen 7 dagen een eerste reactie. Meld erbij: de versie of commit, een
minimale reproductie (bij voorkeur een klein TTL-/GeoJSON-bestand) en de impact die
je ziet.

## Ondersteunde versies

Pre-1.0 wordt alleen de laatste release ondersteund; fixes landen op `dev` en
komen met de eerstvolgende versie mee.

## Reikwijdte

Deze bibliotheek parseert TTL- en GeoJSON-bestanden die van derden afkomstig kunnen
zijn; fouten waarbij een geprepareerd invoerbestand meer doet dan een nette
`DatasetError`/`GeometryError` (crash buiten de foutcontracten, padescape bij het
schrijven, buitensporig geheugengebruik) zijn in scope. De bibliotheek doet zelf
geen netwerk-I/O en voert geen code uit invoerbestanden uit.
