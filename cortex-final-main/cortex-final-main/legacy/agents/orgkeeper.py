"""
ORGKEEPER agent: triggered by "cortex: promote-to-org" on a MR or issue note.
Promotes a project-level memory to the org-wide memory layer.

Org memory pages live at CORTEX-ORG-MEMORY-{NNN}; the index at CORTEX-ORG-INDEX.
Org memories carry two extra fields:
  Source project: <project_path>
  Promoted by: @<username>
and the original project memory gains:
  Scope: ORGANISATION
"""

import logging
import re
from datetime import datetime, timezone

from legacy.config import (
    CORTEX_ORG_INDEX_SLUG,
    MEMORY_SLUG_PREFIX,
    ORG_MEMORY_SLUG_PREFIX,
)
from legacy.core.gitlab_client import GitLabClient
from legacy.core.memory import MemoryStore, _zero_pad_id
from legacy.core.claude_client import ClaudeClient

logger = logging.getLogger("cortex.orgkeeper")

_MEMORY_REF_RE = re.compile(r"(?:memory\s*#?|#|cortex-memory-)(\d{1,3})", re.IGNORECASE)


def _extract_project_path(payload: dict) -> str:
    """Pull a human-readable project path from the webhook payload."""
    proj = payload.get("project") or {}
    return proj.get("path_with_namespace") or proj.get("name") or ""


def _extract_noteable_info(payload: dict) -> tuple[str, int | None]:
    """Return (noteable_type, noteable_iid) from a Note Hook payload."""
    obj = payload.get("object_attributes") or {}
    noteable_type = obj.get("noteable_type", "")
    noteable_iid = obj.get("noteable_iid") or obj.get("noteable_id")
    try:
        noteable_iid = int(noteable_iid)
    except (TypeError, ValueError):
        noteable_iid = None
    return noteable_type, noteable_iid


def _parse_org_index(content: str) -> dict[str, list[str]]:
    """Parse CORTEX-ORG-INDEX markdown table: file_path -> list of org memory ids."""
    index: dict[str, list[str]] = {}
    for line in content.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 3 and parts[1].lower() not in ("file path", "---", ""):
            path = parts[1]
            ids_str = parts[2]
            ids = [i.strip() for i in ids_str.replace(" ", "").split(",") if i.strip()]
            if path and ids:
                index[path] = ids
    return index


def _serialize_org_memory(memory: dict, project_path: str, promoted_by: str) -> str:
    """Render an org memory page in the CORTEX wiki format."""
    governs = ", ".join(memory.get("governs_files") or [])
    decided_by = ", ".join(memory.get("decided_by") or [])
    return (
        f"cortex Memory #{memory.get('id', '')}\n"
        f"Source MR: !{memory.get('source_mr_number', '')} — {memory.get('source_mr_title', '')}\n"
        f"Date: {memory.get('date', '')}\n"
        f"Governs files: {governs}\n"
        f"Decision: {memory.get('decision', '')}\n"
        f"Rejected: {memory.get('rejected', '')}\n"
        f"Reason: {memory.get('reason', '')}\n"
        f"Future implication: {memory.get('future_implication', '')}\n"
        f"Decided by: {decided_by}\n"
        f"Confidence: {memory.get('confidence', '')}\n"
        f"Status: {memory.get('status', '')}\n"
        f"Scope: ORGANISATION\n"
        f"Source project: {project_path}\n"
        f"Promoted by: @{promoted_by}\n"
    )


def _next_org_memory_number(gitlab: GitLabClient) -> str:
    """Return the next zero-padded 3-digit org memory id."""
    slugs = gitlab.list_wiki_pages()
    org_slugs = [s for s in slugs if s.startswith(ORG_MEMORY_SLUG_PREFIX)]
    if not org_slugs:
        return "001"
    nums = []
    for s in org_slugs:
        suffix = s.replace(ORG_MEMORY_SLUG_PREFIX, "")
        if suffix.isdigit():
            nums.append(int(suffix))
    return f"{max(nums) + 1:03d}" if nums else "001"


def _ensure_org_index(gitlab: GitLabClient) -> None:
    """Create CORTEX-ORG-INDEX wiki page if it does not exist."""
    existing = gitlab.get_wiki_page(CORTEX_ORG_INDEX_SLUG)
    if existing is None:
        initial = "# CORTEX Org Index\n\n| File Path | Org Memory IDs |\n| --- | --- |\n"
        gitlab.create_wiki_page(CORTEX_ORG_INDEX_SLUG, CORTEX_ORG_INDEX_SLUG, initial)


def _update_org_index(gitlab: GitLabClient, org_memory_id: str, file_paths: list[str]) -> None:
    """Add org_memory_id -> file_paths mapping to CORTEX-ORG-INDEX."""
    _ensure_org_index(gitlab)
    content = gitlab.get_wiki_page(CORTEX_ORG_INDEX_SLUG) or ""
    index = _parse_org_index(content)
    pad = _zero_pad_id(org_memory_id)
    for path in file_paths:
        path = path.strip()
        if not path:
            continue
        if path not in index:
            index[path] = []
        if pad not in index[path]:
            index[path].append(pad)
    lines = ["# CORTEX Org Index", "", "| File Path | Org Memory IDs |", "| --- | --- |"]
    for path in sorted(index.keys()):
        ids_str = ", ".join(sorted(index[path]))
        lines.append(f"| {path} | {ids_str} |")
    gitlab.update_wiki_page(CORTEX_ORG_INDEX_SLUG, "\n".join(lines) + "\n")


def _find_duplicate(org_index: dict[str, list[str]], file_paths: list[str], gitlab: GitLabClient) -> str | None:
    """
    Return the org memory id of an existing org memory that governs the same files,
    or None if no overlap found.
    """
    candidate_ids: set[str] = set()
    for path in file_paths:
        for oid in org_index.get(path, []):
            candidate_ids.add(oid)
    for oid in candidate_ids:
        pad = _zero_pad_id(oid)
        slug = f"{ORG_MEMORY_SLUG_PREFIX}{pad}"
        content = gitlab.get_wiki_page(slug)
        if content:
            return oid
    return None


def _identify_memory_id_fast(note_body: str, memories: list[dict]) -> str | None:
    """
    Try to identify the target memory id directly from the note text, without
    calling Claude. Returns the memory id string or None if ambiguous.
    """
    matches = _MEMORY_REF_RE.findall(note_body)
    if matches:
        candidate = str(int(matches[0]))
        for m in memories:
            if str(int(m.get("id", "0") or "0")) == candidate:
                return m["id"]
    if len(memories) == 1:
        return memories[0]["id"]
    return None


async def _identify_memory_id_via_claude(note_body: str, memories: list[dict]) -> tuple[str, str]:
    """
    Ask Claude to identify which memory the commenter wants to promote.
    Returns (memory_id, reasoning).
    """
    claude = ClaudeClient()
    prompt = claude.load_prompt("orgkeeper")
    memories_summary = "\n".join(
        f"  id={m.get('id')} | decision={m.get('decision', '')[:80]} | governs={', '.join((m.get('governs_files') or [])[:3])}"
        for m in memories
    )
    full_prompt = (
        f"{prompt}\n\n"
        f"note_body: {note_body}\n\n"
        f"project_memories:\n{memories_summary}"
    )
    result = claude.call(full_prompt)
    if isinstance(result, dict):
        return result.get("memory_id", ""), result.get("reasoning", "")
    import json
    try:
        parsed = json.loads(result)
        return parsed.get("memory_id", ""), parsed.get("reasoning", "")
    except Exception:
        return "", "Claude response could not be parsed."


def _build_confirmation_comment(
    memory: dict,
    org_memory_id: str,
    project_path: str,
    promoted_by: str,
    today_date: str,
) -> str:
    """Render the confirmation comment posted back on the MR/issue."""
    governs = ", ".join(f"`{f}`" for f in (memory.get("governs_files") or []))
    lines = [
        "## 🌐 CORTEX — Memory Promoted to Org Layer",
        "",
        f"**Memory #{memory.get('id')}** has been promoted to the organisation-wide memory layer.",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| Org Memory ID | CORTEX-ORG-MEMORY-{_zero_pad_id(org_memory_id)} |",
        f"| Decision | {memory.get('decision', '')} |",
        f"| Governs | {governs or '—'} |",
        f"| Confidence | {memory.get('confidence', '—')} |",
        f"| Promoted by | @{promoted_by} |",
        f"| Source project | {project_path} |",
        f"| Promoted on | {today_date} |",
        "",
        "The original project memory has been updated with `Scope: ORGANISATION`.",
        "The org-wide index (`CORTEX-ORG-INDEX`) has been updated.",
        "",
        "*CORTEX ORGKEEPER — org memory promotion agent*",
    ]
    return "\n".join(lines)


def _build_conflict_comment(memory: dict, conflicting_org_id: str) -> str:
    """Comment posted when a duplicate org memory is detected."""
    lines = [
        "## ⚠️ CORTEX — Org Promotion Blocked: Duplicate Detected",
        "",
        f"**Memory #{memory.get('id')}** could not be promoted because an existing org memory "
        f"already governs the same files.",
        "",
        f"**Conflicting org memory:** CORTEX-ORG-MEMORY-{_zero_pad_id(conflicting_org_id)}",
        "",
        "If the new decision supersedes the existing org memory, first update that org memory's "
        "status to `Superseded`, then re-run `cortex: promote-to-org`.",
        "",
        "*CORTEX ORGKEEPER — org memory promotion agent*",
    ]
    return "\n".join(lines)


def _build_ambiguous_comment() -> str:
    """Comment posted when ORGKEEPER cannot identify which memory to promote."""
    return (
        "## ❓ CORTEX — Promotion Request Unclear\n\n"
        "ORGKEEPER could not determine which memory you want to promote.\n\n"
        "Please re-comment with an explicit reference, e.g.:\n\n"
        "```\ncortex: promote-to-org #004\n```\n\n"
        "*CORTEX ORGKEEPER — org memory promotion agent*"
    )


async def run_orgkeeper(payload: dict) -> None:
    """
    Main ORGKEEPER entrypoint. Called when a Note Hook contains "cortex: promote-to-org".
    """
    obj = payload.get("object_attributes") or {}
    note_body = obj.get("note") or ""
    noteable_type, noteable_iid = _extract_noteable_info(payload)
    username = (
        (payload.get("user") or {}).get("username")
        or (payload.get("user") or {}).get("name")
        or "unknown"
    )
    project_path = _extract_project_path(payload)
    today_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    gitlab = GitLabClient()
    memory_store = MemoryStore(gitlab)

    def post_comment(body: str) -> None:
        if noteable_type == "MergeRequest" and noteable_iid:
            gitlab.post_mr_comment(noteable_iid, body)
        elif noteable_type == "Issue" and noteable_iid:
            gitlab.post_issue_comment(noteable_iid, body)

    try:
        memories = memory_store.get_all_memories()
    except Exception as e:
        logger.error("ORGKEEPER: Could not fetch project memories: %s", e, exc_info=True)
        post_comment(
            "## ❌ CORTEX — ORGKEEPER Error\n\n"
            "Could not read project memories. Please try again later."
        )
        return

    # Step 1 — identify which memory to promote
    memory_id = _identify_memory_id_fast(note_body, memories)
    reasoning = "Identified from explicit reference in note."

    if memory_id is None:
        memory_id, reasoning = await _identify_memory_id_via_claude(note_body, memories)
        logger.info("ORGKEEPER: Claude identification — id=%s reason=%s", memory_id, reasoning)

    if not memory_id:
        logger.warning("ORGKEEPER: Could not identify target memory from note.")
        post_comment(_build_ambiguous_comment())
        return

    # Step 2 — fetch the target project memory
    target_memory = memory_store.get_memory(memory_id)
    if target_memory is None:
        post_comment(
            f"## ❌ CORTEX — Memory #{memory_id} Not Found\n\n"
            f"No project memory with id `{memory_id}` exists. Please check the id and retry."
        )
        return

    logger.info(
        "ORGKEEPER: promoting Memory #%s ('%s') requested by @%s",
        memory_id, target_memory.get("decision", "")[:60], username,
    )

    # Step 3 — read org index and check for duplicates
    _ensure_org_index(gitlab)
    org_index_content = gitlab.get_wiki_page(CORTEX_ORG_INDEX_SLUG) or ""
    org_index = _parse_org_index(org_index_content)

    conflicting_id = _find_duplicate(org_index, target_memory.get("governs_files") or [], gitlab)
    if conflicting_id:
        logger.warning(
            "ORGKEEPER: promotion blocked — org memory %s already governs same files.", conflicting_id
        )
        post_comment(_build_conflict_comment(target_memory, conflicting_id))
        return

    # Step 4 — determine next org memory number and write org memory page
    org_id = _next_org_memory_number(gitlab)
    org_slug = f"{ORG_MEMORY_SLUG_PREFIX}{org_id}"
    org_content = _serialize_org_memory(target_memory, project_path, username)

    existing_org_page = gitlab.get_wiki_page(org_slug)
    if existing_org_page is None:
        gitlab.create_wiki_page(org_slug, org_slug, org_content)
    else:
        gitlab.update_wiki_page(org_slug, org_content)
    logger.info("ORGKEEPER: wrote org memory page %s", org_slug)

    # Step 5 — update CORTEX-ORG-INDEX
    _update_org_index(gitlab, org_id, target_memory.get("governs_files") or [])
    logger.info("ORGKEEPER: updated CORTEX-ORG-INDEX with id %s", org_id)

    # Step 6 — patch original project memory with Scope: ORGANISATION
    pad = _zero_pad_id(memory_id)
    proj_slug = f"{MEMORY_SLUG_PREFIX}{pad}"
    proj_content = gitlab.get_wiki_page(proj_slug)
    if proj_content is not None:
        if "Scope:" not in proj_content:
            proj_content = proj_content.rstrip() + f"\nScope: ORGANISATION\n"
        else:
            proj_content = re.sub(r"(?m)^Scope:.*$", "Scope: ORGANISATION", proj_content)
        gitlab.update_wiki_page(proj_slug, proj_content)
        logger.info("ORGKEEPER: patched project memory %s with Scope: ORGANISATION", proj_slug)

    # Step 7 — post confirmation
    confirmation = _build_confirmation_comment(
        target_memory, org_id, project_path, username, today_date
    )
    post_comment(confirmation)
    logger.info("ORGKEEPER: promotion complete for Memory #%s -> %s", memory_id, org_slug)
