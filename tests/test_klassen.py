"""De klassenamen-constanten van `klassen` (issue #68).

De wortelnamen die de lader gebruikt stonden deels nog als kale string naast hun
constante. Issue #68 trekt de laatste, `Putdeksel`, naar een constante `KLASSE_PUTDEKSEL`
naast `WORTEL_KNOOPPUNT`/`WORTEL_VERBINDING`, zodat een hernoeming van de klasse niet
langer stil langs een literal in `inlezen` en `laden` glipt. Deze bewaker pint zijn
waarde -- de korte klassenaam, net als bij `WORTEL_*`.
"""

from __future__ import annotations

from gwsw_orox_helpers import klassen


def test_klasse_putdeksel_is_de_korte_klassenaam() -> None:
    assert klassen.KLASSE_PUTDEKSEL == "Putdeksel"
