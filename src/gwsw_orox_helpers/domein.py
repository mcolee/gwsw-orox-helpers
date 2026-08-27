"""De waardeobjecten van het domeinmodel: knopen, strengen en hun kenmerken.

Alles hier is bevroren en rekent alleen met wat het zelf draagt: geen graaf, geen
bestand, geen ontologie. Dat is wat `Node.bodem` en `Conduit.bob_verval` toetsbaar maakt
zonder een TTL te hoeven laden -- `tests/test_domeinmodel.py` bouwt ze met de hand -- en
het is de reden dat de cache ze kan picklen.

Wie deze objecten *uit een graaf* vult, staat in `inlezen`; wat de dataset eromheen
ermee kan, in `dataset`. De namen komen alle drie uit `dataset` naar buiten: dat is het
oppervlak dat nlriochecker kent en dat blijft zo (Harde regel in `CLAUDE.md`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from shapely.geometry import LineString, Point


@dataclass(frozen=True)
class Inwinning:
    """De inwinningsmetagegevens die aan een kenmerk kunnen hangen."""

    wijze: str | None = None
    datum: date | None = None

    def __bool__(self) -> bool:
        """Waar zodra er iets ingevuld is."""
        return self.wijze is not None or self.datum is not None


@dataclass(frozen=True)
class Aspect:
    """Een kenmerk van een object: een waarde of een verwijzing naar een GWSW-begrip.

    Het GWSW hangt kenmerken als `gwsw:hasAspect [ rdf:type gwsw:MateriaalLeiding ;
    gwsw:hasReference gwsw:Beton ]` aan een object. Waardekenmerken gebruiken
    `hasValue`, domeinlijstkenmerken `hasReference`.
    """

    kind: str
    value: str | None = None
    reference: str | None = None
    inwinning: Inwinning | None = None

    @property
    def number(self) -> float | None:
        """De waarde als getal, of None als die er niet is of niet numeriek is."""
        if self.value is None:
            return None
        try:
            return float(self.value)
        except ValueError:
            return None

    @property
    def date(self) -> date | None:
        """De waarde als datum (ISO of jaartal), of None."""
        return _as_date(self.value)


@dataclass(frozen=True)
class Vulwaarde:
    """Een hoogtekenmerk dat een vulwaarde droeg en bij het lezen als ontbrekend geldt."""

    kind: str
    value: float


class _MetAspecten:
    """Toegang tot de kenmerken van een object, per GWSW-klassenaam."""

    aspects: tuple[Aspect, ...]

    def aspect(self, kind: str) -> Aspect | None:
        """Het eerste kenmerk van deze soort, of None."""
        for aspect in self.aspects:
            if aspect.kind == kind:
                return aspect
        return None

    def number(self, kind: str) -> float | None:
        """De numerieke waarde van dit kenmerk, of None."""
        aspect = self.aspect(kind)
        return aspect.number if aspect is not None else None

    def reference(self, kind: str) -> str | None:
        """De domeinlijstverwijzing van dit kenmerk (korte naam), of None."""
        aspect = self.aspect(kind)
        return aspect.reference if aspect is not None else None

    def date(self, kind: str) -> date | None:
        """De datumwaarde van dit kenmerk, of None."""
        aspect = self.aspect(kind)
        return aspect.date if aspect is not None else None


@dataclass(frozen=True)
class Node(_MetAspecten):
    """Een knooppunt in het netwerk: een put, gemaal of lozingspunt."""

    uri: str
    label: str
    types: frozenset[str]
    orientation: str | None
    orientation_types: frozenset[str]
    point: Point | None
    z: float | None
    parents: tuple[str, ...]
    aspects: tuple[Aspect, ...] = ()
    maaiveld_aspect: Aspect | None = None
    maaiveld_inwinning: Inwinning | None = None
    deksel_aspect: Aspect | None = None
    deksel_inwinning: Inwinning | None = None
    multipart: bool = False
    vulwaarden: tuple[Vulwaarde, ...] = ()

    @property
    def maaiveld(self) -> float | None:
        """De maaiveldhoogte bij dit knooppunt, in m NAP."""
        return self.maaiveld_aspect.number if self.maaiveld_aspect is not None else None

    @property
    def dekselniveau(self) -> float | None:
        """Het putdekselniveau, in m NAP."""
        return self.deksel_aspect.number if self.deksel_aspect is not None else None

    @property
    def bovenkant(self) -> float | None:
        """Het bovenkantniveau: het dekselniveau, of anders het maaiveld.

        Het register spreekt bij HGT-004, HGT-012 en HGT-018 over de dekselhoogte.
        Ontbreekt die, dan is de maaiveldhoogte de dichtstbijzijnde benadering; welke
        van de twee gebruikt is, hoort in de bevinding te staan.
        """
        return self.dekselniveau if self.dekselniveau is not None else self.maaiveld

    @property
    def hoogte_m(self) -> float | None:
        """De hoogte van de put in meters; het GWSW noteert die in millimeters."""
        waarde = self.number("HoogtePut")
        return waarde / 1000 if waarde is not None else None

    @property
    def bodem(self) -> float | None:
        """Het putbodemniveau, afgeleid uit bovenkant minus puthoogte.

        Het GWSW kent geen kenmerk `Putbodemniveau`; de bodem volgt uit het
        dekselniveau en `HoogtePut`. Ontbreekt een van beide, dan is de bodem
        onbekend en mag er niet op getoetst worden.
        """
        boven, hoogte = self.bovenkant, self.hoogte_m
        if boven is None or hoogte is None:
            return None
        return boven - hoogte


@dataclass(frozen=True)
class Conduit(_MetAspecten):
    """Een streng: een leiding met een begin- en eindpunt."""

    uri: str
    label: str
    types: frozenset[str]
    line: LineString | None
    start_node: str | None
    end_node: str | None
    bob_start_aspect: Aspect | None = None
    bob_end_aspect: Aspect | None = None
    aspects: tuple[Aspect, ...] = ()
    multipart: bool = False
    z_values: tuple[float | None, ...] = ()
    vulwaarden: tuple[Vulwaarde, ...] = ()

    @property
    def z_start(self) -> float | None:
        """De z-waarde van het eerste lijnpunt, als de geometrie er een heeft."""
        return self.z_values[0] if self.z_values else None

    @property
    def z_end(self) -> float | None:
        """De z-waarde van het laatste lijnpunt, als de geometrie er een heeft."""
        return self.z_values[-1] if self.z_values else None

    @property
    def bob_start(self) -> float | None:
        """De binnenonderkant buis aan het beginpunt, in m NAP."""
        return self.bob_start_aspect.number if self.bob_start_aspect is not None else None

    @property
    def bob_end(self) -> float | None:
        """De binnenonderkant buis aan het eindpunt, in m NAP."""
        return self.bob_end_aspect.number if self.bob_end_aspect is not None else None

    @property
    def bob_verval(self) -> float | None:
        """Het verval van de bodem over de streng, in meters.

        Positief als de bodem van het administratieve beginpunt naar het eindpunt
        daalt. Ontbreekt een van beide BOB's, dan valt er niets te zeggen.
        """
        if self.bob_start is None or self.bob_end is None:
            return None
        return self.bob_start - self.bob_end

    @property
    def breedte_mm(self) -> float | None:
        """De breedte (bij een rond profiel: de diameter) in millimeters."""
        return self.number("BreedteLeiding")

    @property
    def hoogte_mm(self) -> float | None:
        """De hoogte van het profiel in millimeters."""
        return self.number("HoogteLeiding")

    @property
    def lengte_m(self) -> float | None:
        """De administratieve lengte in meters."""
        return self.number("LengteLeiding")

    @property
    def materiaal(self) -> str | None:
        """Het leidingmateriaal als korte GWSW-naam."""
        return self.reference("MateriaalLeiding")

    @property
    def vorm(self) -> str | None:
        """De profielvorm als korte GWSW-naam."""
        return self.reference("VormLeiding")

    @property
    def begindatum_jaar(self) -> int | None:
        """Het jaartal uit de begindatum (GWSW-kenmerk `Begindatum`)."""
        datum = self.date("Begindatum")
        return datum.year if datum is not None else None


@dataclass(frozen=True)
class Koppelingsherstel:
    """Hoeveel `hasConnection`-doelen de lader op naamstam naar een hulpstuk herleid heeft.

    De BrutIS-export van De Wolden en Hoogeveen koppelt élk leidingeinde dat op een
    hulpstuk uitkomt aan `<hulpstuk>_put`, een URI zonder type of aspect, terwijl de
    orientatie `<hulpstuk>_put<n>` heet. Zonder herstel ziet de engine bij alle 1054
    T-stukken nul leidingen en hangen 3024 strengeinden aan niets. Het herstel is
    bewust smal (alleen een onbekend doel, alleen als de stam een hulpstukknoop is) en
    wordt hier geteld, zodat het rapport de aanlevering blijft aanwijzen in plaats van
    het gebrek stilletjes op te ruimen (issue #60).
    """

    koppelingen: int = 0
    hulpstukken: int = 0


ISO_DATUM = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
JAARTAL = re.compile(r"^(\d{4})$")


def _as_date(waarde: str | None) -> date | None:
    """Leest een GWSW-datumwaarde; een kaal jaartal telt als 1 januari."""
    if waarde is None:
        return None
    match = ISO_DATUM.match(waarde)
    if match is not None:
        try:
            return date(int(match[1]), int(match[2]), int(match[3]))
        except ValueError:
            return None
    jaar = JAARTAL.match(waarde.strip())
    if jaar is not None:
        try:
            return date(int(jaar[1]), 1, 1)
        except ValueError:
            return None
    return None
