"""
Unit tests for MR webhook routing in legacy/main.py.
Imports _dispatch_mr directly to avoid FastAPI/config boot issues.
No live API calls — all agents are mocked.
"""

import asyncio
import sys
import types
from unittest.mock import AsyncMock, patch

import pytest


def _install_gitlab_stub():
    if "gitlab" in sys.modules and hasattr(sys.modules["gitlab"], "_cortex_stub"):
        return
    stub = types.ModuleType("gitlab")
    stub._cortex_stub = True
    exc_stub = types.ModuleType("gitlab.exceptions")
    for cls in ("GitlabAuthenticationError", "GitlabGetError", "GitlabCreateError",
                "GitlabUpdateError", "GitlabListError"):
        setattr(exc_stub, cls, type(cls, (Exception,), {}))
    stub.exceptions = exc_stub
    stub.Gitlab = lambda *a, **kw: None
    sys.modules["gitlab"] = stub
    sys.modules["gitlab.exceptions"] = exc_stub


_install_gitlab_stub()


def _mr_payload(action: str, mr_iid: int = 1) -> dict:
    return {
        "object_attributes": {
            "iid": mr_iid,
            "action": action,
            "title": "Test MR",
            "description": "",
            "url": "https://gitlab.example.com/project/-/merge_requests/1",
        },
        "user": {"username": "developer"},
    }


def _import_dispatch_mr():
    """Import _dispatch_mr with all agent modules stubbed out."""
    agent_mods = [
        "legacy.agents.cortexkeeper",
        "legacy.agents.guardkeeper",
        "legacy.agents.specforge",
        "legacy.agents.cortexcast",
        "legacy.agents.onboarding",
        "legacy.agents.orgkeeper",
        "legacy.core.gitlab_client",
        "legacy.core.memory",
        "legacy.core.claude_client",
    ]
    stubs = {}
    for mod in agent_mods:
        if mod not in sys.modules:
            stubs[mod] = types.ModuleType(mod)
            sys.modules[mod] = stubs[mod]

    # Ensure the dispatched functions exist as async no-ops on the stubs
    for name in ("run_cortexkeeper", "run_guardkeeper", "run_spec_compliance",
                 "run_specforge", "run_cortexcast", "run_onboarding",
                 "run_orgkeeper", "handle_spec_approval", "run_spec_compliance"):
        for mod_name, mod in sys.modules.items():
            if mod_name.startswith("legacy.agents") or mod_name.startswith("legacy.core"):
                if not hasattr(mod, name):
                    setattr(mod, name, AsyncMock())

    # Remove legacy.main so it re-imports cleanly
    sys.modules.pop("legacy.main", None)

    import legacy.main as main_mod
    return main_mod._dispatch_mr, main_mod


_dispatch_mr, _main_mod = _import_dispatch_mr()


# ── Test 1: "open" routes to GUARDKEEPER ────────────────────────────────────

@pytest.mark.asyncio
async def test_open_routes_to_guardkeeper():
    with (
        patch.object(_main_mod, "run_guardkeeper", new_callable=AsyncMock) as mock_gk,
        patch.object(_main_mod, "run_spec_compliance", new_callable=AsyncMock),
        patch.object(_main_mod, "run_cortexkeeper", new_callable=AsyncMock) as mock_ck,
    ):
        await _dispatch_mr(_mr_payload("open"))

    mock_gk.assert_awaited_once()
    mock_ck.assert_not_awaited()


# ── Test 2: "update" routes to GUARDKEEPER ──────────────────────────────────

@pytest.mark.asyncio
async def test_update_routes_to_guardkeeper():
    with (
        patch.object(_main_mod, "run_guardkeeper", new_callable=AsyncMock) as mock_gk,
        patch.object(_main_mod, "run_spec_compliance", new_callable=AsyncMock),
        patch.object(_main_mod, "run_cortexkeeper", new_callable=AsyncMock) as mock_ck,
    ):
        await _dispatch_mr(_mr_payload("update"))

    mock_gk.assert_awaited_once()
    mock_ck.assert_not_awaited()


# ── Test 3: "merge" routes to CORTEXKEEPER only ─────────────────────────────

@pytest.mark.asyncio
async def test_merge_routes_to_cortexkeeper_only():
    with (
        patch.object(_main_mod, "run_guardkeeper", new_callable=AsyncMock) as mock_gk,
        patch.object(_main_mod, "run_spec_compliance", new_callable=AsyncMock) as mock_sc,
        patch.object(_main_mod, "run_cortexkeeper", new_callable=AsyncMock) as mock_ck,
    ):
        await _dispatch_mr(_mr_payload("merge"))

    mock_ck.assert_awaited_once()
    mock_gk.assert_not_awaited()
    mock_sc.assert_not_awaited()


# ── Test 4: unknown action routes to nothing ─────────────────────────────────

@pytest.mark.asyncio
async def test_unknown_action_routes_to_nothing():
    with (
        patch.object(_main_mod, "run_guardkeeper", new_callable=AsyncMock) as mock_gk,
        patch.object(_main_mod, "run_spec_compliance", new_callable=AsyncMock) as mock_sc,
        patch.object(_main_mod, "run_cortexkeeper", new_callable=AsyncMock) as mock_ck,
    ):
        await _dispatch_mr(_mr_payload("close"))

    mock_gk.assert_not_awaited()
    mock_sc.assert_not_awaited()
    mock_ck.assert_not_awaited()


# ── Test 5: "update" payload forwarded unchanged to GUARDKEEPER ──────────────

@pytest.mark.asyncio
async def test_update_payload_forwarded_unchanged():
    """The exact payload dict is forwarded to run_guardkeeper without mutation."""
    payload = _mr_payload("update", mr_iid=7)
    captured = []

    async def fake_guardkeeper(p, reply_type=None):
        captured.append(p)

    with (
        patch.object(_main_mod, "run_guardkeeper", side_effect=fake_guardkeeper),
        patch.object(_main_mod, "run_spec_compliance", new_callable=AsyncMock),
    ):
        await _dispatch_mr(payload)

    assert len(captured) == 1
    assert captured[0]["object_attributes"]["iid"] == 7
    assert captured[0]["object_attributes"]["action"] == "update"


# ── Test 6: "open" also invokes SPEC_COMPLIANCE alongside GUARDKEEPER ─────────

@pytest.mark.asyncio
async def test_open_also_invokes_spec_compliance():
    with (
        patch.object(_main_mod, "run_guardkeeper", new_callable=AsyncMock),
        patch.object(_main_mod, "run_spec_compliance", new_callable=AsyncMock) as mock_sc,
        patch.object(_main_mod, "run_cortexkeeper", new_callable=AsyncMock),
    ):
        await _dispatch_mr(_mr_payload("open"))

    mock_sc.assert_awaited_once()


# ── Test 7: "update" also invokes SPEC_COMPLIANCE alongside GUARDKEEPER ──────

@pytest.mark.asyncio
async def test_update_also_invokes_spec_compliance():
    with (
        patch.object(_main_mod, "run_guardkeeper", new_callable=AsyncMock),
        patch.object(_main_mod, "run_spec_compliance", new_callable=AsyncMock) as mock_sc,
        patch.object(_main_mod, "run_cortexkeeper", new_callable=AsyncMock),
    ):
        await _dispatch_mr(_mr_payload("update"))

    mock_sc.assert_awaited_once()


# ── Test 8: "merge" payload forwarded unchanged to CORTEXKEEPER ───────────────

@pytest.mark.asyncio
async def test_merge_payload_forwarded_unchanged():
    """The exact payload dict is forwarded to run_cortexkeeper without mutation."""
    payload = _mr_payload("merge", mr_iid=42)
    captured = []

    async def fake_cortexkeeper(p):
        captured.append(p)

    with patch.object(_main_mod, "run_cortexkeeper", side_effect=fake_cortexkeeper):
        await _dispatch_mr(payload)

    assert len(captured) == 1
    assert captured[0]["object_attributes"]["iid"] == 42
    assert captured[0]["object_attributes"]["action"] == "merge"


# ── Test 9: "reopen" action routes to nothing (not treated as "open") ─────────

@pytest.mark.asyncio
async def test_reopen_action_routes_to_nothing():
    """'reopen' is a distinct GitLab action and must not match the 'open' branch."""
    with (
        patch.object(_main_mod, "run_guardkeeper", new_callable=AsyncMock) as mock_gk,
        patch.object(_main_mod, "run_spec_compliance", new_callable=AsyncMock) as mock_sc,
        patch.object(_main_mod, "run_cortexkeeper", new_callable=AsyncMock) as mock_ck,
    ):
        await _dispatch_mr(_mr_payload("reopen"))

    mock_gk.assert_not_awaited()
    mock_sc.assert_not_awaited()
    mock_ck.assert_not_awaited()
