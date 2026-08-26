"""Tests voor de plaats van de cachemap.

Deze staan los van `test_cache.py`. De naam van de map is juist het soort ding dat
stilzwijgend fout gaat: wijst hij naar een map die niet bestaat, dan leest elke run
de dataset opnieuw in (ruim drie minuten) zonder ooit te klagen.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gwsw_orox_helpers.cache import standaard_cachemap


def test_cachemap_draagt_de_packagenaam(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/huis/iemand")))

    assert standaard_cachemap() == Path("/huis/iemand/.cache/gwsw-orox-helpers")


def test_cachemap_volgt_xdg_cache_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", "/elders/cache")

    assert standaard_cachemap() == Path("/elders/cache/gwsw-orox-helpers")
