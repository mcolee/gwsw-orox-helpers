"""De grenslaag: de GeoJSON-vlakken waarlangs geknipt wordt, en hun bestandsnaam.

Het tweede blad van het package: hij kent alleen `errors` en shapely. Het volledige verhaal
staat in de docstring van `gwsw_orox_helpers.clip`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from shapely.geometry import shape as _vorm
from shapely.geometry.base import BaseGeometry
from shapely.prepared import PreparedGeometry, prep

from gwsw_orox_helpers.errors import DatasetError


@dataclass(frozen=True)
class _Vlak:
    """Een vlak uit de grenslaag: zijn naam, zijn meetkunde en de voorbereide vorm."""

    naam: str
    meetkunde: BaseGeometry
    voorbereid: PreparedGeometry


def _lees_grenzen(grenzen: Path, sleutel: str) -> tuple[_Vlak, ...]:
    """Leest de GeoJSON-grenslaag als vlakken, in bestandsvolgorde."""
    try:
        rauw = json.loads(Path(grenzen).read_text(encoding="utf-8"))
    except OSError as fout:
        raise DatasetError(f"{grenzen}: grenslaag kan niet gelezen worden ({fout}).") from fout
    except (json.JSONDecodeError, UnicodeDecodeError) as fout:
        raise DatasetError(f"{grenzen}: geen leesbare GeoJSON ({fout}).") from fout

    kenmerken = rauw.get("features") if isinstance(rauw, dict) else None
    if not kenmerken:
        raise DatasetError(f"{grenzen}: geen features in de grenslaag; er valt niets te knippen.")

    vlakken: list[_Vlak] = []
    gezien: set[str] = set()
    for kenmerk in kenmerken:
        eigenschappen = kenmerk.get("properties") or {}
        if sleutel not in eigenschappen or eigenschappen[sleutel] is None:
            raise DatasetError(
                f"{grenzen}: een feature draagt geen {sleutel!r}; die property bepaalt de "
                f"uitvoernaam en moet op elk vlak staan."
            )
        naam = str(eigenschappen[sleutel])
        if naam in gezien:
            raise DatasetError(
                f"{grenzen}: {sleutel!r} is {naam!r} op meer dan een vlak; twee vlakken zouden "
                f"dan hetzelfde bestand schrijven."
            )
        gezien.add(naam)

        try:
            meetkunde = _vorm(kenmerk["geometry"])
        except (KeyError, TypeError, ValueError, AttributeError) as fout:
            raise DatasetError(
                f"{grenzen}: {naam!r} heeft geen leesbare geometrie ({fout})."
            ) from fout
        if meetkunde.geom_type not in ("Polygon", "MultiPolygon") or meetkunde.is_empty:
            raise DatasetError(
                f"{grenzen}: {naam!r} is een {meetkunde.geom_type} en geen (multi)vlak; "
                f"een clip verdeelt langs vlakken."
            )
        vlakken.append(_Vlak(naam=naam, meetkunde=meetkunde, voorbereid=prep(meetkunde)))
    return tuple(vlakken)


def _bestandsnaam(naam: str) -> str:
    """De naam van een vlak als bestandsnaamdeel; alles wat geen naam mag zijn wordt `_`."""
    veilig = re.sub(r"[^A-Za-z0-9._-]+", "_", naam).strip("._-")
    return veilig or "vlak"
