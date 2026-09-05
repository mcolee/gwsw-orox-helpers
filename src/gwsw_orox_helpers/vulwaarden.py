"""De vulwaarden-transformatie: `markeer_vulwaarden` (issue #67).

Een afgeleide leesbewerking die losstaat van de lader: de cache bewaart de ruwe parse, de
band is projectconfiguratie. `markeer_vulwaarden` leidt uit een `GwswDataset` een nieuwe af
en importeert daarom `model`; het weet van de lader (`laden`) niets. `dataset`
her-exporteert `markeer_vulwaarden` ongewijzigd.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from gwsw_orox_helpers.domein import Aspect, Conduit, Node, Vulwaarde
from gwsw_orox_helpers.model import GwswDataset


def markeer_vulwaarden(
    dataset: GwswDataset, kenmerken: Sequence[str], band_m: float
) -> GwswDataset:
    """Leest een hoogtekenmerk binnen de vulwaardeband als niet geregistreerd.

    Sommige exports schrijven 0,000 waar het kenmerk leeg hoort te zijn (De Wolden en Hoogeveen:
    een kwart van de BOB's). De checks zouden die nul als meting lezen en er duizenden
    hoogtefouten van maken. Deze stap zet zo'n kenmerk op `None` en onthoudt op het
    object dat en welke waarde er stond, zodat een attribuutcheck het een keer kan melden
    en de hoogtechecks het object overslaan en dat in hun toelichting zeggen.

    De stap staat los van het laden: de cache bewaart de ruwe parse, de band is
    projectconfiguratie. De meegegeven dataset blijft onaangeraakt; met een lege
    kenmerkenlijst is dit de identiteit.
    """
    if not kenmerken:
        return dataset
    gekozen = frozenset(kenmerken)

    def vulwaarde(aspect: Aspect | None) -> Vulwaarde | None:
        """De vulwaarde die dit kenmerk draagt, of None als het een meting is."""
        if aspect is None or aspect.kind not in gekozen:
            return None
        getal = aspect.number
        if getal is None or abs(getal) > band_m:
            return None
        return Vulwaarde(aspect.kind, getal)

    nodes: dict[str, Node] = {}
    for uri, node in dataset.nodes.items():
        maaiveld, deksel = vulwaarde(node.maaiveld_aspect), vulwaarde(node.deksel_aspect)
        gevonden = tuple(vul for vul in (maaiveld, deksel) if vul is not None)
        nodes[uri] = (
            replace(
                node,
                maaiveld_aspect=None if maaiveld is not None else node.maaiveld_aspect,
                deksel_aspect=None if deksel is not None else node.deksel_aspect,
                vulwaarden=gevonden,
            )
            if gevonden
            else node
        )

    conduits: dict[str, Conduit] = {}
    for uri, conduit in dataset.conduits.items():
        begin, eind = vulwaarde(conduit.bob_start_aspect), vulwaarde(conduit.bob_end_aspect)
        gevonden = tuple(vul for vul in (begin, eind) if vul is not None)
        conduits[uri] = (
            replace(
                conduit,
                bob_start_aspect=None if begin is not None else conduit.bob_start_aspect,
                bob_end_aspect=None if eind is not None else conduit.bob_end_aspect,
                vulwaarden=gevonden,
            )
            if gevonden
            else conduit
        )

    return replace(dataset, nodes=nodes, conduits=conduits)
