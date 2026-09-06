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

from gwsw_orox_helpers.errors import BestandError, GrenslaagError


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
        raise BestandError(f"{grenzen}: grenslaag kan niet gelezen worden ({fout}).") from fout
    # `RecursionError` staat hier bij de onleesbare invoer en niet bij de fouten van ons:
    # diep genest GeoJSON (20000x `[`) laat de C-scanner van `json` hem gooien, en verderop
    # doet een even diepe `GeometryCollection` hetzelfde in shapely's `shape()`. Zonder deze
    # tak ontsnapt hij kaal uit de publieke `clip_orox`, die op dit hele pad `DatasetError`
    # belooft. `MemoryError` blijft er bewust buiten: die gaat niet over dit bestand maar
    # over het proces, en is niets om een afnemer als "onleesbare grenslaag" af te laten doen.
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as fout:
        raise GrenslaagError(f"{grenzen}: geen leesbare GeoJSON ({fout}).") from fout

    kenmerken = rauw.get("features") if isinstance(rauw, dict) else None
    if not kenmerken:
        raise GrenslaagError(f"{grenzen}: geen features in de grenslaag; er valt niets te knippen.")

    vlakken: list[_Vlak] = []
    gezien: set[str] = set()
    # Van gesaneerde bestandsnaam naar de ruwe naam die hem opleverde. `clip_orox` bouwt het
    # uitvoerpad via `_bestandsnaam(naam)`, dus twee verschillende ruwe namen die naar
    # dezelfde bestandsnaam saneren (`'a b'` en `'a/b'` -> `a_b`) zouden hetzelfde bestand
    # schrijven -- net zo stil als twee gelijke ruwe namen hierboven, en daarom net zo'n fout.
    gezien_bestandsnaam: dict[str, str] = {}
    for kenmerk in kenmerken:
        eigenschappen = kenmerk.get("properties") or {}
        if sleutel not in eigenschappen or eigenschappen[sleutel] is None:
            raise GrenslaagError(
                f"{grenzen}: een feature draagt geen {sleutel!r}; die property bepaalt de "
                f"uitvoernaam en moet op elk vlak staan."
            )
        naam = str(eigenschappen[sleutel])
        if naam in gezien:
            raise GrenslaagError(
                f"{grenzen}: {sleutel!r} is {naam!r} op meer dan een vlak; twee vlakken zouden "
                f"dan hetzelfde bestand schrijven."
            )
        bestandsnaam = _bestandsnaam(naam)
        botsende = gezien_bestandsnaam.get(bestandsnaam)
        if botsende is not None:
            raise GrenslaagError(
                f"{grenzen}: {botsende!r} en {naam!r} leveren allebei de bestandsnaam "
                f"{bestandsnaam!r} op; twee vlakken zouden dan hetzelfde bestand schrijven."
            )
        gezien.add(naam)
        gezien_bestandsnaam[bestandsnaam] = naam

        try:
            meetkunde = _vorm(kenmerk["geometry"])
        # `RecursionError` staat hier om dezelfde reden als hierboven bij `json.loads`.
        except (KeyError, TypeError, ValueError, AttributeError, RecursionError) as fout:
            raise GrenslaagError(
                f"{grenzen}: {naam!r} heeft geen leesbare geometrie ({fout})."
            ) from fout
        if meetkunde.geom_type not in ("Polygon", "MultiPolygon") or meetkunde.is_empty:
            raise GrenslaagError(
                f"{grenzen}: {naam!r} is een {meetkunde.geom_type} en geen (multi)vlak; "
                f"een clip verdeelt langs vlakken."
            )
        vlakken.append(_Vlak(naam=naam, meetkunde=meetkunde, voorbereid=prep(meetkunde)))
    return tuple(vlakken)


def _bestandsnaam(naam: str) -> str:
    """De naam van een vlak als bestandsnaamdeel; alles wat geen naam mag zijn wordt `_`."""
    veilig = re.sub(r"[^A-Za-z0-9._-]+", "_", naam).strip("._-")
    return veilig or "vlak"
