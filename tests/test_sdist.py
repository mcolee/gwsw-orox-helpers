"""Drifttest op de sdist: wat een release verscheept, ligt hier vast (issue #44).

De wheel was al schoon (36 bestanden), maar `pyproject.toml` had geen sdist-sectie, dus
de bron-tarbal nam agent-tooling en lokale paden mee: `.claude/`, `CLAUDE.md`, `uv.lock`,
`.github/`, `docs/agents/`, `.gitignore` en `manifesto.md`. Deze test bouwt de sdist in een
`tmp_path` en toetst zowel wat er *niet* in mag (die zeven) als wat er *wel* in hoort (de
gebundelde 1.6-ontologie, `README.md`, `LICENSE`, `pyproject.toml`).

De seam is het sdist-archief zoals `uv build --sdist` het aflevert -- de publieke grens van
wat naar PyPI gaat -- en niet de interne `only-include`-regel. Zo blijft de test staan als
de auteur ooit op een `exclude`-benadering overstapt.

`uv` wordt met `shutil.which` gezocht en de test slaat zichzelf over als het ontbreekt,
zodat hij `sys.executable`-onafhankelijk is en niet omvalt op een machine zonder uv.
"""

from __future__ import annotations

import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

WORTEL = Path(__file__).resolve().parents[1]

# Wat een release-tarbal nooit mag dragen. Een prefix (op `/`) dekt een hele boom
# (`.claude/`, `.github/`, `docs/agents/`); een kale naam dekt precies dat bestand.
#
# `.gitignore` staat hier bewust *niet* bij, ook al noemt issue #44 hem: hatchling (1.32)
# `force_include`t de projecteigen `.gitignore` onvoorwaardelijk in elke sdist en geen
# `pyproject.toml`-optie zet dat uit. Het is een gewoon, ongevaarlijk sdist-bestand (geen
# agent-tooling en geen lokaal pad), en de §3-controle van het issue
# (`\.claude|CLAUDE\.md|uv\.lock|\.github`) raakt hem niet. Zie de kanttekening bij
# `[tool.hatch.build.targets.sdist]` in `pyproject.toml`.
VERBODEN_BOMEN = (".claude/", ".github/", "docs/agents/")
VERBODEN_BESTANDEN = ("CLAUDE.md", "uv.lock", "manifesto.md")

# Wat er wel in hoort: de gebundelde leidende ontologie (groot, maar de package leest hem)
# en de drie bestanden die een PyPI-project herkenbaar maken.
VEREIST = (
    "src/gwsw_orox_helpers/data/gwsw_ontologie_totaal_16.ttl",
    "README.md",
    "LICENSE",
    "pyproject.toml",
)


def _sdist_leden(tmp_path: Path) -> set[str]:
    """Bouwt de sdist in `tmp_path` en levert de padnamen zonder de topmap-prefix.

    Een sdist-tarbal zet alles onder `gwsw_orox_helpers-<versie>/`; die ene topmap wordt
    weggestript zodat de paden overeenkomen met die in de repo-root.
    """
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv ontbreekt op deze machine; de sdist is niet te bouwen")
    subprocess.run(
        [uv, "build", "--sdist", "--out-dir", str(tmp_path)],
        cwd=WORTEL,
        check=True,
        capture_output=True,
    )
    (tarbal,) = tmp_path.glob("*.tar.gz")
    with tarfile.open(tarbal, "r:gz") as archief:
        namen = archief.getnames()
    leden: set[str] = set()
    for naam in namen:
        _, _, rest = naam.partition("/")
        if rest:
            leden.add(rest)
    return leden


def test_de_sdist_draagt_geen_agent_tooling_of_lokale_paden(tmp_path: Path) -> None:
    leden = _sdist_leden(tmp_path)
    lek = [
        naam
        for naam in leden
        if naam in VERBODEN_BESTANDEN or any(naam.startswith(boom) for boom in VERBODEN_BOMEN)
    ]
    assert lek == [], f"deze horen niet in de sdist: {sorted(lek)}"


def test_de_sdist_draagt_de_ontologie_en_de_pypi_bestanden(tmp_path: Path) -> None:
    leden = _sdist_leden(tmp_path)
    ontbreekt = [naam for naam in VEREIST if naam not in leden]
    assert ontbreekt == [], f"deze horen wel in de sdist: {ontbreekt}"
