"""Typebewijs voor `graaf.GraafLezer`: dit bestand draait niet, mypy leest het.

`graaf.GraafLezer` belooft dat `rdflib.Graph` én `graaf.GraafIndex` het leescontract van
de ontologielezers structureel vervullen. Die belofte is niet met een `assert` te toetsen
-- structurele subtypering bestaat alleen bij het typen -- dus staat het bewijs hier, in
een module die de poort meeneemt: `pyproject.toml` zet `tests/typecheck` in
`[tool.mypy] files`, dus `uv run mypy` checkt hem en `Success: no issues found` is het
bewijs. Er staat geen test in en pytest verzamelt hem niet (de naam begint niet met
`test_`); wie hem toch importeert, krijgt drie definities en twee no-ops.

Het bewijst twee kanten, en de tweede is de belangrijkste:

- **positief** -- `_neemt_een_lezer(Graph())` en `_neemt_een_lezer(GraafIndex())` mogen
  geen fout geven, en de vijf lezers van `ontologie` nemen allebei de vormen. Valt dat
  om, dan is het protocol te breed geworden (of heeft een rdflib-upgrade een handtekening
  veranderd) en is de laaggrens stuk;
- **negatief** -- `HalveGraaf` (alleen `value`) en `VerkeerdeGraaf` (`objects` levert
  tekst) horen te worden afgewezen. Dat staat er als `# type: ignore[arg-type]` en
  `pyproject.toml` zet `warn_unused_ignores = true`: verdwijnt de fout, dan wordt de
  `ignore` ongebruikt en valt mypy alsnog om. Zonder deze kant zou een protocol dat per
  ongeluk alles accepteert (bijvoorbeeld omdat rdflib zijn typen kwijtraakt en `Graph`
  `Any` wordt) er groen uitzien.
"""

from __future__ import annotations

from collections.abc import Iterator

from rdflib import Graph, URIRef
from rdflib.term import Node as RdfNode

from gwsw_orox_helpers.graaf import GraafIndex, GraafLezer
from gwsw_orox_helpers.namen import GWSW
from gwsw_orox_helpers.ontologie import (
    datatype_van_kenmerk,
    facetbereik,
    functie_van_klasse,
    kenmerkbereik,
    verwachte_property,
)


class HalveGraaf:
    """Kent `value` maar geen `objects`; vervult het protocol dus niet."""

    def value(self, subject: RdfNode, predicate: RdfNode) -> RdfNode | None:
        """Altijd niets."""
        return None


class VerkeerdeGraaf:
    """Kent allebei de namen, maar `objects` levert tekst in plaats van termen."""

    def value(self, subject: RdfNode, predicate: RdfNode) -> RdfNode | None:
        """Altijd niets."""
        return None

    def objects(self, subject: RdfNode, predicate: RdfNode) -> Iterator[str]:
        """Levert het verkeerde soort."""
        return iter(())


def _neemt_een_lezer(bron: GraafLezer) -> None:
    """Een parameter op het protocol; wat hierin past, past overal in de leeslaag."""
    bron.value(URIRef(GWSW + "Rioolput"), URIRef(GWSW + "hasAspect"))
    list(bron.objects(URIRef(GWSW + "Rioolput"), URIRef(GWSW + "hasAspect")))


def _bewijs() -> None:
    """De vier gevallen; alleen mypy voert dit uit, en dan nog alleen op papier."""
    kenmerk = URIRef(GWSW + "LengteLeiding")
    datatype = URIRef(GWSW + "Dt_LengteLeiding")

    # Positief: allebei de graafvormen vervullen het protocol structureel.
    _neemt_een_lezer(Graph())
    _neemt_een_lezer(GraafIndex())

    # Positief: en dus nemen de vijf lezers van `ontologie` ze allebei.
    for bron in (Graph(), GraafIndex()):
        facetbereik(bron, datatype)
        datatype_van_kenmerk(bron, kenmerk)
        kenmerkbereik(bron, kenmerk)
        verwachte_property(bron, kenmerk)
        functie_van_klasse(bron, kenmerk)

    # Negatief: een object zonder `objects`, en een met de verkeerde opbrengst.
    _neemt_een_lezer(HalveGraaf())  # type: ignore[arg-type]
    _neemt_een_lezer(VerkeerdeGraaf())  # type: ignore[arg-type]
    facetbereik(HalveGraaf(), datatype)  # type: ignore[arg-type]
