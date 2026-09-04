"""Tests voor de projectmetadata in `pyproject.toml` (`[project]`).

De wheel-METADATA is de visitekaart van de package op PyPI: `authors`, `keywords`,
`classifiers` en de projectlinks reizen mee in elke wheel en vullen de projectpagina. Deze
drifttest leest `pyproject.toml` met `tomllib` en legt vast dát die velden aanwezig zijn en
dat de `description` het schrijven en clippen niet meer als toekomst ("later") aankondigt --
allebei sinds 0.2.0 geleverd. Er wordt hier bewust **geen** wheel gebouwd: dat is te traag
voor de poort; de METADATA-meting zelf staat in de issue-notitie, buiten de tests.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

WORTEL = Path(__file__).resolve().parents[1]

VERWACHTE_CLASSIFIERS = {
    "Development Status :: 4 - Beta",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Programming Language :: Python :: 3.14",
    "Typing :: Typed",
    "Topic :: Scientific/Engineering :: GIS",
    "Operating System :: OS Independent",
}

VERWACHTE_KEYWORDS = ["gwsw", "orox", "riolering", "rdf", "turtle"]

VERWACHTE_URL_SLEUTELS = {"Homepage", "Repository", "Changelog", "Issues"}


def _project() -> dict[str, Any]:
    pyproject = tomllib.loads((WORTEL / "pyproject.toml").read_text(encoding="utf-8"))
    return pyproject["project"]


def test_authors_noemt_de_auteur() -> None:
    authors = _project()["authors"]
    assert {"name": "Martin Colee", "email": "martin@colee.nl"} in authors


def test_keywords_staan_er() -> None:
    assert _project()["keywords"] == VERWACHTE_KEYWORDS


def test_classifiers_zijn_volledig() -> None:
    classifiers = set(_project()["classifiers"])
    ontbrekend = VERWACHTE_CLASSIFIERS - classifiers
    assert not ontbrekend, f"ontbrekende classifiers: {sorted(ontbrekend)}"


def test_project_urls_wijzen_naar_de_repo() -> None:
    urls = _project()["urls"]
    assert VERWACHTE_URL_SLEUTELS <= set(urls)
    basis = "https://github.com/mcolee/gwsw-orox-helpers"
    assert urls["Homepage"] == basis
    assert urls["Repository"] == basis
    assert urls["Changelog"] == f"{basis}/blob/main/CHANGELOG.md"
    assert urls["Issues"] == f"{basis}/issues"


def test_description_kondigt_schrijven_en_clippen_niet_meer_aan_als_later() -> None:
    description = _project()["description"]
    assert "later" not in description.lower()
