"""Voortgang van de zware stappen, als protocol.

De pijplijn heeft stappen die minuten kosten: het inlezen van de TTL's (op de
De Wolden en Hoogeveen-export ruim drie minuten), het draaien van de checks en het wegschrijven
van de GeoPackage. Zonder terugkoppeling is er geen verschil te zien tussen
"rekent" en "hangt".

Wie deze package als library gebruikt geeft een eigen implementatie mee; de CLI
heeft er een op basis van `click.progressbar`. De standaardwaarde `NUL_VOORTGANG`
doet niets, zodat elke bestaande aanroep ongewijzigd blijft werken.

Voortgang is weergave, geen logica. Geen check leest hier state uit en geen aanroep
hier beinvloedt de uitkomst van een run. Wie hier iets aan toevoegt dat een check
kan lezen, haalt die eigenschap weg.

Wat dit protocol niet kan: voortgang binnen een enkel bestand. rdflib geeft geen
tussenstand tijdens het parsen, en juist het parsen van de dataset is de lange
stap -- een enkele aanroep die niets van zichzelf laat horen. De laadfase toont
daarom hoeveel bestanden klaar zijn en verzint geen percentage voor het bestand
dat loopt.
"""

from __future__ import annotations

from typing import Final, Protocol


class Voortgang(Protocol):
    """Ontvangt de voortgang van een langlopende stap."""

    def start_fase(self, naam: str, totaal: int | None) -> None:
        """Begint een fase; `totaal` is None als het aantal stappen onbekend is."""
        ...

    def stap(self, n: int = 1, label: str | None = None) -> None:
        """Meldt `n` afgeronde stappen, met een label voor wat er net klaar is."""
        ...

    def einde_fase(self) -> None:
        """Sluit de lopende fase af."""
        ...


class NulVoortgang:
    """Doet niets; de standaardwaarde overal waar voortgang optioneel is."""

    def start_fase(self, naam: str, totaal: int | None) -> None:
        """Doet niets."""

    def stap(self, n: int = 1, label: str | None = None) -> None:
        """Doet niets."""

    def einde_fase(self) -> None:
        """Doet niets."""


# Een enkele instantie: hij houdt geen state, en een nieuwe per aanroep maken zou
# alleen ruis zijn.
NUL_VOORTGANG: Final[Voortgang] = NulVoortgang()
