"""
ONBOARDING agent: triggered when a new member joins the project (Member Hook).
Creates a personalised welcome issue with Org Standards as the first section,
followed by a summary of active architectural decisions they need to know.
"""

import logging
from datetime import datetime, timezone

from legacy.core.gitlab_client import GitLabClient
from legacy.core.memory import MemoryStore

logger = logging.getLogger("cortex.onboarding")

ORG_STANDARDS = """## Section 1 — Non-Negotiable Org Standards

These rules apply to every line of code you commit, regardless of context. GUARDKEEPER enforces them automatically on every MR.

### Security
- **No secrets in source.** API keys, tokens, passwords — never hardcoded. Use environment variables or a secrets manager.
- **No SQL string concatenation.** Always use parameterised queries.
- **No `eval()` or `exec()` on untrusted input.** Dynamic code execution on user-supplied data is never acceptable.
- **No disabling auth checks.** Authentication and authorisation must never be bypassed.

### Reliability
- **No bare `except:` or `except Exception: pass`.** Silent exception swallowing hides bugs. Always log or re-raise.
- **No unbounded retry loops.** Every retry must have a maximum attempt cap.
- **No blocking network calls inside async handlers.** Use async I/O throughout.

### Process
- **No committed commented-out code blocks longer than 5 lines.** Delete it or put it in a PR description.
- **No `TODO`/`FIXME` without a ticket ID.** `# TODO: fix this` is not acceptable. Reference the ticket: `# TODO: PROJ-123`.

If GUARDKEEPER flags one of these on your MR, it is not optional — it must be fixed before merging.
"""


def _render_memory_section(memories: list[dict]) -> str:
    active = [m for m in memories if (m.get("status") or "").strip().lower() != "superseded"]
    if not active:
        return (
            "## Section 2 — Architectural Decisions\n\n"
            "No active architectural decisions have been recorded yet. "
            "As your team makes and documents decisions, they will appear here automatically for future onboarding.\n"
        )

    parts = [
        "## Section 2 — Architectural Decisions You Need to Know",
        "",
        f"Your team has **{len(active)} active decision(s)** stored in CORTEX institutional memory. "
        "GUARDKEEPER will enforce these on every MR you open.",
        "",
    ]
    for m in active:
        mem_id = m.get("id", "")
        decision = m.get("decision", "")
        rejected = m.get("rejected", "")
        reason = m.get("reason", "")
        governs = ", ".join(m.get("governs_files") or [])
        confidence = m.get("confidence", "")
        decided_by = " ".join(m.get("decided_by") or [])
        date = m.get("date", "")

        parts.append(f"### Memory #{mem_id}")
        if governs:
            parts.append(f"**Governs:** `{governs}`")
        parts.append(f"**Decision:** {decision}")
        if rejected:
            parts.append(f"**Rejected approach (do not reintroduce):** {rejected}")
        if reason:
            parts.append(f"**Why:** {reason}")
        meta_parts = []
        if confidence:
            meta_parts.append(f"Confidence: {confidence}")
        if decided_by:
            meta_parts.append(f"Decided by: {decided_by}")
        if date:
            meta_parts.append(f"Date: {date}")
        if meta_parts:
            parts.append(f"*{' | '.join(meta_parts)}*")
        parts.append("")

    return "\n".join(parts)


def _build_welcome_body(username: str, memories: list[dict], today_date: str) -> str:
    memory_section = _render_memory_section(memories)
    parts = [
        f"# 🧠 CORTEX — Welcome to the Team, @{username}",
        "",
        f"*Generated {today_date} by CORTEX ONBOARDING*",
        "",
        "CORTEX is the team's institutional memory system. It automatically captures "
        "architectural decisions from MR discussions and enforces them on future MRs via GUARDKEEPER.",
        "",
        "This issue is your orientation — read it before your first MR.",
        "",
        "---",
        "",
        ORG_STANDARDS.strip(),
        "",
        "---",
        "",
        memory_section.strip(),
        "",
        "---",
        "",
        "## How CORTEX Works",
        "",
        "- **When you open an MR:** GUARDKEEPER checks your diff against Org Standards and all relevant architectural decisions. If a conflict is found, it posts a comment before you merge.",
        "- **When a conflict is flagged:** Reply with `cortex: intentional — [your reasoning]` (to override and update institutional memory), `cortex: accidental` (to revise before merging), or `cortex: discuss` (to loop in original decision makers).",
        "- **When you merge:** CORTEXKEEPER reads your MR discussion and automatically captures any new decisions into institutional memory.",
        "",
        "*Questions? Reply to this issue — CORTEX is always watching.*",
    ]
    return "\n".join(parts)


async def run_onboarding(payload: dict) -> None:
    """
    Run ONBOARDING for a new project member. Creates a personalised welcome
    issue with Org Standards as Section 1 and active architectural decisions as Section 2.
    """
    username = None
    try:
        username = payload.get("user_username") or payload.get("user_name") or "new-member"
        access_level = payload.get("project_access") or payload.get("access_level") or ""
        today_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        gitlab = GitLabClient()
        memory_store = MemoryStore(gitlab)

        try:
            memories = memory_store.get_all_memories()
        except Exception as e:
            logger.warning("ONBOARDING: Could not fetch memories: %s. Proceeding with empty list.", e)
            memories = []

        body = _build_welcome_body(username, memories, today_date)
        access_str = f" ({access_level})" if access_level else ""
        created = gitlab.create_issue(
            title=f"🧠 CORTEX — Welcome @{username}{access_str}",
            description=body,
            labels=["cortex-onboarding"],
        )
        iid = created.get("iid")
        logger.info("ONBOARDING complete for @%s. Welcome issue created as #%s.", username, iid)

    except Exception as e:
        logger.error("ONBOARDING failed for @%s: %s", username, e, exc_info=True)
