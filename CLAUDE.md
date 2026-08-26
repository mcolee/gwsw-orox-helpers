# Project: gwsw-orox-helpers

Leeslaag voor GWSW-OroX (TTL): grafmodel, geometrie, klassenhierarchie, cache.
Eerste afnemer: nlriochecker. Nederlandse identifiers, GWSW-conform.

## Harde regels
- **Leidende GWSW-versie: 1.6**, uit de gebundelde
  `src/gwsw_orox_helpers/data/Ontologie_GWSW_Totaal.ttl` (`owl:versionInfo`:
  *"Deelmodel Totaal, filter op CoFs BAS DMO EN HYD LDR MDS NLCS PLI RRB TOP,
  versie=1.6 (2025-11-18T14:53:33)"*). Dit is de enige plek waar het nummer als
  projectafspraak staat; `test_indexversie_staat_in_claude_md` leest het `versie=`-deel
  hier terug. Upgraden is handwerk van de auteur: hij levert een nieuw ontologiebestand
  en dan trekt de package bij. Draai daarbij `uv run python scripts/maak_gwsw_index.py`
  (herschrijft de gebundelde index) en werk deze regel bij; de drifttests bewaken
  beide richtingen.
- De publieke API is wat nlriochecker importeert; breken mag tot 1.0 maar alleen
  met een CHANGELOG-regel en een versiebump.
- Geen nlriochecker-begrippen in deze package: vulwaardenlijsten, encodingkeuzes
  en checkconfiguratie zijn parameters, geen constanten.

## Werkwijze
- Python 3.12+, src-layout, uv; poort: ruff check, ruff format, mypy, pytest,
  dekking >= 95% (`uv run --with pytest-cov pytest --cov=gwsw_orox_helpers`).
