"""
Unit tests for cross-project organisational memory (Part 2 of CORTEX demo).
No live API calls — all GitLab interactions are mocked.

The real `gitlab` package's `exceptions` submodule is unavailable in the test
environment, so we stub out the entire `gitlab` import for tests that need to
import legacy.core.gitlab_client or legacy.core.memory.
"""

import sys
import types
from unittest.mock import MagicMock, patch

import pytest


# ── Shared stub for the `gitlab` package ────────────────────────────────────

def _install_gitlab_stub():
    """
    Install a minimal stub for the `gitlab` package so that
    `from gitlab import exceptions as gitlab_exc` succeeds.
    Only call this once per process; subsequent calls are idempotent.
    """
    if "gitlab" in sys.modules and hasattr(sys.modules["gitlab"], "_cortex_stub"):
        return

    stub = types.ModuleType("gitlab")
    stub._cortex_stub = True

    exc_stub = types.ModuleType("gitlab.exceptions")

    class GitlabAuthenticationError(Exception):
        pass

    class GitlabGetError(Exception):
        pass

    class GitlabCreateError(Exception):
        pass

    class GitlabUpdateError(Exception):
        pass

    class GitlabListError(Exception):
        pass

    exc_stub.GitlabAuthenticationError = GitlabAuthenticationError
    exc_stub.GitlabGetError = GitlabGetError
    exc_stub.GitlabCreateError = GitlabCreateError
    exc_stub.GitlabUpdateError = GitlabUpdateError
    exc_stub.GitlabListError = GitlabListError

    stub.exceptions = exc_stub
    stub.Gitlab = MagicMock()

    sys.modules["gitlab"] = stub
    sys.modules["gitlab.exceptions"] = exc_stub


_install_gitlab_stub()


# ── Shared org memory wiki page content ─────────────────────────────────────

ORG_MEMORY_CONTENT = (
    "cortex Memory #001\n"
    "Source MR: !1 — Initial decision\n"
    "Date: 2026-01-01\n"
    "Governs files: src/api/auth.py\n"
    "Decision: Use fixed retry intervals.\n"
    "Rejected: exponential backoff\n"
    "Reason: predictable behaviour\n"
    "Future implication: all retry logic must use retry_fixed()\n"
    "Decided by: @alice\n"
    "Confidence: HIGH\n"
    "Status: Active\n"
    "Supersedes: \n"
    "Scope: ORGANISATION\n"
    "Source project: project-a\n"
    "Promoted by: @alice\n"
)


# ── Test 1 ──────────────────────────────────────────────────────────────────

def test_gitlab_client_uses_explicit_project_id():
    """GitLabClient(project_id=99999) must call projects.get(99999), not GITLAB_PROJECT_ID."""
    # Ensure our stub is in place before importing
    _install_gitlab_stub()

    # Remove cached module so it re-imports cleanly against our stub
    for key in list(sys.modules):
        if key in ("legacy.core.gitlab_client",):
            del sys.modules[key]

    from legacy.core.gitlab_client import GitLabClient

    mock_gl_instance = MagicMock()
    mock_gl_instance.projects.get.return_value = MagicMock()
    sys.modules["gitlab"].Gitlab.return_value = mock_gl_instance

    GitLabClient(project_id=99999)

    mock_gl_instance.projects.get.assert_called_once_with(99999)


# ── Test 2 ──────────────────────────────────────────────────────────────────

def _make_mock_org_gitlab(slugs: list[str], pages: dict[str, str]):
    mock = MagicMock()
    mock.list_wiki_pages.return_value = slugs
    mock.get_wiki_page.side_effect = lambda slug: pages.get(slug)
    return mock


def test_get_all_org_memories_filters_only_org_slugs():
    """get_all_org_memories() must load CORTEX-ORG-MEMORY-* only, not CORTEX-MEMORY-*."""
    _install_gitlab_stub()
    for key in list(sys.modules):
        if key in ("legacy.core.memory", "legacy.core.gitlab_client"):
            del sys.modules[key]

    slugs = [
        "CORTEX-MEMORY-001",
        "CORTEX-ORG-MEMORY-001",
        "CORTEX-ORG-MEMORY-002",
        "CORTEX-INDEX",
    ]
    pages = {
        "CORTEX-ORG-MEMORY-001": ORG_MEMORY_CONTENT,
        "CORTEX-ORG-MEMORY-002": ORG_MEMORY_CONTENT.replace("Memory #001", "Memory #002"),
    }
    mock_org_gitlab = _make_mock_org_gitlab(slugs, pages)

    from legacy.core.memory import MemoryStore
    store = MemoryStore(MagicMock())
    results = store.get_all_org_memories(mock_org_gitlab)

    assert len(results) == 2, f"Expected 2 org memories, got {len(results)}"
    ids = [r.get("id") for r in results]
    assert "001" in ids
    assert "002" in ids
    for r in results:
        assert r.get("scope") == "ORGANISATION"
        assert r.get("source_project") == "project-a"

    # CORTEX-MEMORY-001 (project level) must never have been fetched
    fetched = [call.args[0] for call in mock_org_gitlab.get_wiki_page.call_args_list]
    assert "CORTEX-MEMORY-001" not in fetched


# ── Test 3 ──────────────────────────────────────────────────────────────────

def test_past_decisions_block_includes_org_memories():
    """
    The past_decisions_parts loop in guardkeeper Mode 1 must label org memories
    as [ORG] and include Source project when present.
    This test replicates the loop logic inline to avoid importing guardkeeper.
    """
    project_mem = {
        "id": "042",
        "decision": "Use SQLAlchemy ORM.",
        "rejected": "raw SQL strings",
        "reason": "injection risk",
        "future_implication": "no raw SQL",
        "governs_files": ["src/db.py"],
        "scope": "",
        "source_project": "",
    }
    org_mem = {
        "id": "001",
        "decision": "Use fixed retry intervals.",
        "rejected": "exponential backoff",
        "reason": "predictable behaviour",
        "future_implication": "all retry logic must use retry_fixed()",
        "governs_files": ["src/api/auth.py"],
        "scope": "ORGANISATION",
        "source_project": "project-a",
    }
    all_memories = [project_mem, org_mem]

    # Replicate the Step 5 loop from guardkeeper.py
    parts = []
    for m in all_memories:
        governs = ", ".join(m.get("governs_files") or [])
        is_org = m.get("scope", "").upper() == "ORGANISATION"
        scope_label = "ORG" if is_org else "PROJECT"
        source_project = m.get("source_project", "")
        source_line = f"Source project: {source_project}\n" if source_project else ""
        parts.append(
            f"---\n"
            f"Memory #{m.get('id', '')} [{scope_label}]\n"
            f"Decision: {m.get('decision', '')}\n"
            f"Rejected: {m.get('rejected', '')}\n"
            f"Reason: {m.get('reason', '')}\n"
            f"Future implication: {m.get('future_implication', '')}\n"
            f"Governs files: {governs}\n"
            f"{source_line}"
            f"Memory ID: {m.get('id', '')}\n"
            f"---"
        )
    block = "\n\n".join(parts)

    assert "Memory #042 [PROJECT]" in block
    assert "Memory #001 [ORG]" in block
    assert "Source project: project-a" in block
    # Project memory block must appear before the Source project line
    assert block.index("Memory #042 [PROJECT]") < block.index("Source project:")


# ── Test 4 ──────────────────────────────────────────────────────────────────

def test_cortex_org_project_id_fallback(monkeypatch):
    """
    When CORTEX_ORG_PROJECT_ID env var is unset, CORTEX_ORG_PROJECT_ID must equal
    GITLAB_PROJECT_ID. When set, it must use the configured value.
    """
    import importlib
    from unittest.mock import patch

    monkeypatch.setenv("GITLAB_TOKEN", "dummy-token")
    monkeypatch.setenv("GITLAB_PROJECT_ID", "111")
    monkeypatch.delenv("CORTEX_ORG_PROJECT_ID", raising=False)

    # Also need ANTHROPIC_API_KEY to satisfy config validation when provider=anthropic
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-key")
    monkeypatch.setenv("CLAUDE_PROVIDER", "anthropic")

    import legacy.config as cfg_mod
    # Suppress load_dotenv so the .env file cannot override our monkeypatched values.
    # Must patch at the dotenv source since reload re-imports the name before calling it.
    with patch("dotenv.load_dotenv", return_value=None):
        importlib.reload(cfg_mod)

    assert cfg_mod.CORTEX_ORG_PROJECT_ID == 111
    assert cfg_mod.CORTEX_ORG_PROJECT_ID == cfg_mod.GITLAB_PROJECT_ID

    # Scenario B: env var set — must use that value
    monkeypatch.setenv("CORTEX_ORG_PROJECT_ID", "222")
    with patch("dotenv.load_dotenv", return_value=None):
        importlib.reload(cfg_mod)
    assert cfg_mod.CORTEX_ORG_PROJECT_ID == 222
    assert cfg_mod.GITLAB_PROJECT_ID == 111

    # Restore
    monkeypatch.delenv("CORTEX_ORG_PROJECT_ID", raising=False)
    with patch("dotenv.load_dotenv", return_value=None):
        importlib.reload(cfg_mod)


# ── Test 5 ──────────────────────────────────────────────────────────────────

def test_org_memory_source_project_parsed_correctly():
    """
    _parse_memory + org-field parsing must correctly extract Scope, Source project,
    and Promoted by from a real org memory wiki page string.
    """
    _install_gitlab_stub()
    for key in list(sys.modules):
        if key in ("legacy.core.memory", "legacy.core.gitlab_client"):
            del sys.modules[key]

    from legacy.core.memory import MemoryStore

    store = MemoryStore(MagicMock())
    mem = store._parse_memory(ORG_MEMORY_CONTENT)

    # Apply the same org-specific field parsing used in get_all_org_memories
    for line in ORG_MEMORY_CONTENT.strip().split("\n"):
        line = line.strip()
        if line.startswith("Scope:"):
            mem["scope"] = line.replace("Scope:", "").strip()
        elif line.startswith("Source project:"):
            mem["source_project"] = line.replace("Source project:", "").strip()
        elif line.startswith("Promoted by:"):
            mem["promoted_by"] = line.replace("Promoted by:", "").strip()
    mem.setdefault("scope", "ORGANISATION")
    mem.setdefault("source_project", "")
    mem.setdefault("promoted_by", "")

    assert mem["id"] == "001"
    assert mem["scope"] == "ORGANISATION"
    assert mem["source_project"] == "project-a"
    assert mem["promoted_by"] == "@alice"
    assert mem["decision"] == "Use fixed retry intervals."


# ── helpers shared by Tests 6 / 9 / 10 ─────────────────────────────────────

def _install_guardkeeper_stubs(org_project_id: int = 1) -> None:
    """
    Install minimal stubs for every module that guardkeeper.py imports at the
    top level, so the module can be imported without real GitLab/Claude clients.
    Idempotent: safe to call multiple times.
    """
    sys.modules.pop("legacy.agents.guardkeeper", None)

    cfg_stub = types.ModuleType("legacy.config")
    cfg_stub.CORTEX_ORG_PROJECT_ID = org_project_id
    sys.modules["legacy.config"] = cfg_stub

    gc_stub = types.ModuleType("legacy.core.gitlab_client")
    gc_stub.GitLabClient = MagicMock()
    sys.modules["legacy.core.gitlab_client"] = gc_stub

    cc_stub = types.ModuleType("legacy.core.claude_client")
    cc_stub.ClaudeClient = MagicMock()
    sys.modules["legacy.core.claude_client"] = cc_stub

    ms_stub = types.ModuleType("legacy.core.memory")
    ms_stub.MemoryStore = MagicMock()
    sys.modules["legacy.core.memory"] = ms_stub


def _remove_guardkeeper_stubs() -> None:
    """
    Remove stubs injected by _install_guardkeeper_stubs so that tests that
    rely on real module imports (e.g. test_guardkeeper_local.py) are unaffected.
    """
    for key in (
        "legacy.agents.guardkeeper",
        "legacy.config",
        "legacy.core.gitlab_client",
        "legacy.core.claude_client",
        "legacy.core.memory",
    ):
        sys.modules.pop(key, None)


# ── Test 6: _parse_conflict_memory_ids_from_discussions — org flag ───────────

def test_parse_conflict_memory_ids_org_flag():
    """
    _parse_conflict_memory_ids_from_discussions must return is_org=True for
    'Organisation Memory #12' and is_org=False for 'Memory #42'.
    """
    _install_guardkeeper_stubs()
    try:
        from legacy.agents.guardkeeper import _parse_conflict_memory_ids_from_discussions
    finally:
        _remove_guardkeeper_stubs()

    # Only "Organisation Memory #12" → is_org=True
    body_org = (
        "🧠 CORTEX — GUARDKEEPER — ⚠️ Decision Conflict Detected\n\n"
        "### 🟡 Conflict with Organisation Memory #12 — MEDIUM severity\n"
        "**Source project:** group/project-a\n"
    )
    result = _parse_conflict_memory_ids_from_discussions([{"body": body_org}])
    assert result == [("12", True)], f"Expected [('12', True)], got {result}"

    # Only "Memory #42" → is_org=False
    body_proj = (
        "🧠 CORTEX — GUARDKEEPER — ⚠️ Decision Conflict Detected\n\n"
        "### 🟡 Conflict with Memory #42 — MEDIUM severity\n"
    )
    result = _parse_conflict_memory_ids_from_discussions([{"body": body_proj}])
    assert result == [("42", False)], f"Expected [('42', False)], got {result}"

    # Mixed body — both types present
    body_mixed = (
        "🧠 CORTEX — GUARDKEEPER — ⚠️ Decision Conflict Detected\n\n"
        "### 🟡 Conflict with Organisation Memory #12 — MEDIUM severity\n"
        "### 🔴 Conflict with Memory #42 — HIGH severity\n"
    )
    result = _parse_conflict_memory_ids_from_discussions([{"body": body_mixed}])
    assert ("12", True) in result
    assert ("42", False) in result
    assert len(result) == 2


# ── Test 7: update_org_memory_status — happy path ────────────────────────────

def test_update_org_memory_status_happy_path():
    """
    update_org_memory_status must find the correct CORTEX-ORG-MEMORY-* slug by
    matching the internal id, patch Status: in-place, and preserve Scope:,
    Source project:, and Promoted by: fields.
    """
    _install_gitlab_stub()
    for key in list(sys.modules):
        if key in ("legacy.core.memory", "legacy.core.gitlab_client"):
            del sys.modules[key]

    from legacy.core.memory import MemoryStore

    org_content = ORG_MEMORY_CONTENT  # id=001, Status: Active
    updated_pages: dict[str, str] = {}

    mock_org_gitlab = MagicMock()
    mock_org_gitlab.list_wiki_pages.return_value = ["CORTEX-ORG-MEMORY-001"]
    mock_org_gitlab.get_wiki_page.side_effect = lambda slug: (
        org_content if slug == "CORTEX-ORG-MEMORY-001" else None
    )
    mock_org_gitlab.update_wiki_page.side_effect = lambda slug, content: updated_pages.__setitem__(slug, content)

    store = MemoryStore(MagicMock())
    store.update_org_memory_status(mock_org_gitlab, "1", "Superseded", append_note="override reasoning")

    assert "CORTEX-ORG-MEMORY-001" in updated_pages, "update_wiki_page was not called"
    saved = updated_pages["CORTEX-ORG-MEMORY-001"]

    # Status must be updated
    assert "Status: Superseded" in saved
    assert "Status: Active" not in saved

    # Org-specific fields must be preserved
    assert "Scope: ORGANISATION" in saved
    assert "Source project: project-a" in saved
    assert "Promoted by: @alice" in saved

    # Reason must include the override note
    assert "override reasoning" in saved


# ── Test 8: update_org_memory_status — not found ─────────────────────────────

def test_update_org_memory_status_not_found():
    """update_org_memory_status must raise RuntimeError when no matching org memory exists."""
    _install_gitlab_stub()
    for key in list(sys.modules):
        if key in ("legacy.core.memory", "legacy.core.gitlab_client"):
            del sys.modules[key]

    from legacy.core.memory import MemoryStore
    import pytest

    mock_org_gitlab = MagicMock()
    mock_org_gitlab.list_wiki_pages.return_value = ["CORTEX-ORG-MEMORY-001"]
    mock_org_gitlab.get_wiki_page.return_value = ORG_MEMORY_CONTENT  # id=001

    store = MemoryStore(MagicMock())
    with pytest.raises(RuntimeError, match="not found"):
        store.update_org_memory_status(mock_org_gitlab, "99", "Superseded")


# ── Test 9: intentional handler — org memory routes to org project ────────────

def test_intentional_handler_routes_org_memory_to_org_project():
    """
    When the conflict comment contains 'Organisation Memory #12', the intentional
    handler must call update_org_memory_status (not update_memory_status), and
    must NOT raise. The acknowledgement comment must still be posted.
    """
    from unittest.mock import patch, MagicMock as MM
    import asyncio

    _install_guardkeeper_stubs(org_project_id=42)
    try:
        import legacy.agents.guardkeeper as gk_mod
    finally:
        _remove_guardkeeper_stubs()

    conflict_body = (
        "🧠 CORTEX — GUARDKEEPER — ⚠️ Decision Conflict Detected\n\n"
        "### 🟡 Conflict with Organisation Memory #12 — MEDIUM severity\n"
        "**Source project:** group/project-a\n"
    )

    mock_gitlab = MM()
    mock_gitlab.get_mr_discussions.return_value = [{"body": conflict_body}]
    mock_gitlab.post_mr_comment.return_value = None

    update_org_calls: list = []

    mock_store = MM()
    mock_store.update_memory_status.side_effect = AssertionError(
        "update_memory_status must NOT be called for an org memory"
    )
    mock_store.update_org_memory_status.side_effect = lambda *a, **kw: update_org_calls.append((a, kw))

    payload = {
        "merge_request": {"iid": 5},
        "object_attributes": {"note": "cortex: intentional — cross-project override"},
        "user": {"username": "bob"},
    }

    with (
        patch.object(gk_mod, "GitLabClient", return_value=mock_gitlab),
        patch.object(gk_mod, "MemoryStore", return_value=mock_store),
        patch.object(gk_mod, "CORTEX_ORG_PROJECT_ID", 42),
    ):
        asyncio.get_event_loop().run_until_complete(gk_mod.run_guardkeeper(payload, reply_type="intentional"))

    # update_org_memory_status must have been called with mid="12"
    assert len(update_org_calls) == 1, f"Expected 1 org update call, got {update_org_calls}"
    call_args = update_org_calls[0][0]
    assert call_args[1] == "12", f"Expected memory id '12', got {call_args[1]}"
    assert call_args[2] == "Superseded"

    # Acknowledgement comment must have been posted
    mock_gitlab.post_mr_comment.assert_called_once()
    comment_text = mock_gitlab.post_mr_comment.call_args[0][1]
    assert "Acknowledged" in comment_text
    assert "#12" in comment_text


# ── Test 10: intentional handler — project memory uses project store ───────────

def test_intentional_handler_routes_project_memory_to_project_store():
    """
    When the conflict comment contains 'Conflict with Memory #42' (not 'Organisation Memory'),
    the intentional handler must call update_memory_status, not update_org_memory_status.
    """
    from unittest.mock import patch, MagicMock as MM
    import asyncio

    _install_guardkeeper_stubs(org_project_id=42)
    try:
        import legacy.agents.guardkeeper as gk_mod
    finally:
        _remove_guardkeeper_stubs()

    conflict_body = (
        "🧠 CORTEX — GUARDKEEPER — ⚠️ Decision Conflict Detected\n\n"
        "### 🔴 Conflict with Memory #42 — HIGH severity\n"
    )

    mock_gitlab = MM()
    mock_gitlab.get_mr_discussions.return_value = [{"body": conflict_body}]
    mock_gitlab.post_mr_comment.return_value = None

    update_status_calls: list = []

    mock_store = MM()
    mock_store.update_memory_status.side_effect = lambda *a, **kw: update_status_calls.append((a, kw))
    mock_store.update_org_memory_status.side_effect = AssertionError(
        "update_org_memory_status must NOT be called for a project-local memory"
    )

    payload = {
        "merge_request": {"iid": 5},
        "object_attributes": {"note": "cortex: intentional — was deliberate"},
        "user": {"username": "alice"},
    }

    with (
        patch.object(gk_mod, "GitLabClient", return_value=mock_gitlab),
        patch.object(gk_mod, "MemoryStore", return_value=mock_store),
        patch.object(gk_mod, "CORTEX_ORG_PROJECT_ID", 42),
    ):
        asyncio.get_event_loop().run_until_complete(gk_mod.run_guardkeeper(payload, reply_type="intentional"))

    assert len(update_status_calls) == 1, f"Expected 1 project update call, got {update_status_calls}"
    call_args = update_status_calls[0][0]
    assert call_args[0] == "42", f"Expected memory id '42', got {call_args[0]}"
    assert call_args[1] == "Superseded"

    mock_gitlab.post_mr_comment.assert_called_once()


# ── Test 11: parser dedup — same id as org and plain in same comment ──────────

def test_parse_conflict_memory_ids_dedup_org_wins():
    """
    When the conflict comment contains both 'Organisation Memory #12' (in the section
    header) and plain 'Memory #12' (in Claude's reasoning text), the parser must
    deduplicate to a single ('12', True) entry — org classification wins.
    This prevents the intentional handler from also calling update_memory_status
    for an org memory ID.
    """
    _install_guardkeeper_stubs()
    try:
        from legacy.agents.guardkeeper import _parse_conflict_memory_ids_from_discussions
    finally:
        _remove_guardkeeper_stubs()

    # Realistic conflict comment: org header + reasoning that mentions plain "Memory #12"
    body = (
        "🧠 CORTEX — GUARDKEEPER — ⚠️ Decision Conflict Detected\n\n"
        "### 🟡 Conflict with Organisation Memory #12 — MEDIUM severity\n"
        "**Source project:** group/project-a\n\n"
        "**CORTEX's reasoning:**\n"
        "This change conflicts with Memory #12 which mandates fixed retry intervals.\n\n"
        "**The original decision:**\n"
        "> Use fixed retry intervals.\n"
    )

    result = _parse_conflict_memory_ids_from_discussions([{"body": body}])

    # Must contain exactly one entry for id 12, and it must be is_org=True
    assert len(result) == 1, f"Expected 1 deduplicated entry, got {result}"
    assert result[0] == ("12", True), f"Expected ('12', True), got {result[0]}"
