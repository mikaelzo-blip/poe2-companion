"""Suite-wide isolation: no test may touch the real runtime/ or the live GGG API."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_runtime(tmp_path_factory, monkeypatch):
    import companion.dashboard_api as dashboard_api
    import companion.dashboard_server as dashboard_server

    monkeypatch.setattr(dashboard_server, "RUNTIME_DIR", tmp_path_factory.mktemp("runtime"))
    monkeypatch.setattr(dashboard_api, "load_pob_mcp_modules", lambda *a, **k: None)
