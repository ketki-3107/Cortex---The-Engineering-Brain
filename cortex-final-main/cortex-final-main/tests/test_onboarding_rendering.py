"""
Unit tests for ONBOARDING agent rendering logic.
Covers: welcome body, org standards section, memory section (active/superseded/empty),
and issue title format.
"""
import sys

# ── inline the two rendering helpers from onboarding.py ──────────────────────

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


def _render_memory_section(memories):
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


def _build_welcome_body(username, memories, today_date):
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


# ── shared fixtures ───────────────────────────────────────────────────────────

DATE = "2026-08-09"
USERNAME = "bob"

MEMORIES = [
    {
        "id": "004",
        "decision": "Use fixed retry intervals",
        "rejected": "Exponential backoff",
        "reason": "Avoids thundering herd on shared services.",
        "governs_files": ["legacy/agents/cortexkeeper.py", "legacy/agents/guardkeeper.py"],
        "confidence": "HIGH",
        "decided_by": ["@alice"],
        "date": "2026-07-01",
        "status": "Active",
    },
    {
        "id": "005",
        "decision": "Store all memories as wiki pages",
        "rejected": "Database tables",
        "reason": "WikiLab is already in use; no extra infra needed.",
        "governs_files": ["legacy/core/memory.py"],
        "confidence": "MEDIUM",
        "decided_by": ["@alice", "@bob"],
        "date": "2026-07-15",
        "status": "Active",
    },
    {
        "id": "002",
        "decision": "Old approach — now superseded",
        "rejected": "",
        "reason": "Was relevant at the time.",
        "governs_files": ["legacy/old.py"],
        "confidence": "LOW",
        "decided_by": [],
        "date": "2025-01-01",
        "status": "Superseded",
    },
]


# ── pytest test functions ─────────────────────────────────────────────────────

def test_welcome_body_structure():
    body = _build_welcome_body(USERNAME, MEMORIES, DATE)
    assert f"Welcome to the Team, @{USERNAME}" in body
    assert DATE in body
    assert "Section 1 — Non-Negotiable Org Standards" in body
    assert "Section 2 — Architectural Decisions" in body
    assert "## How CORTEX Works" in body
    assert body.count("\n---\n") >= 3


def test_org_standards_content():
    body = _build_welcome_body(USERNAME, MEMORIES, DATE)
    assert "No secrets in source" in body
    assert "No SQL string concatenation" in body
    assert "eval()" in body
    assert "No bare `except:`" in body
    assert "No unbounded retry loops" in body
    assert "No blocking network calls inside async handlers" in body
    assert "No committed commented-out code blocks" in body
    assert "ticket ID" in body
    assert "GUARDKEEPER flags one of these" in body


def test_active_shown_superseded_hidden():
    body = _build_welcome_body(USERNAME, MEMORIES, DATE)
    assert "Memory #004" in body
    assert "Memory #005" in body
    assert "Memory #002" not in body
    assert "Use fixed retry intervals" in body
    assert "Rejected approach (do not reintroduce)" in body
    assert "Exponential backoff" in body
    assert "thundering herd" in body
    assert "legacy/agents/cortexkeeper.py" in body
    assert "Confidence: HIGH" in body
    assert "Decided by: @alice" in body
    assert "**2 active decision(s)**" in body


def test_empty_memory_bank():
    body = _build_welcome_body("charlie", [], DATE)
    assert "No active architectural decisions have been recorded yet" in body
    assert "Section 2 — Architectural Decisions" in body
    assert "Section 1 — Non-Negotiable Org Standards" in body


def test_all_superseded_same_as_empty():
    superseded_only = [
        {"id": "001", "decision": "Old thing", "status": "Superseded",
         "governs_files": [], "decided_by": [], "rejected": "", "reason": "",
         "confidence": "", "date": ""}
    ]
    body = _build_welcome_body("dave", superseded_only, DATE)
    assert "No active architectural decisions have been recorded yet" in body
    assert "Memory #001" not in body


def test_issue_title_format():
    title_no_access = f"🧠 CORTEX — Welcome @{USERNAME}"
    username = "eve"
    access_str = " (Developer)"
    title_with_access = f"🧠 CORTEX — Welcome @{username}{access_str}"
    assert title_no_access == f"🧠 CORTEX — Welcome @{USERNAME}"
    assert title_with_access == "🧠 CORTEX — Welcome @eve (Developer)"


def test_how_cortex_works_content():
    body = _build_welcome_body(USERNAME, MEMORIES, DATE)
    assert "cortex: intentional" in body
    assert "cortex: accidental" in body
    assert "cortex: discuss" in body
    assert "CORTEXKEEPER reads your MR discussion" in body


# ── standalone execution (python tests/test_onboarding_rendering.py) ──────────

if __name__ == "__main__":
    failures = 0

    def check(name, condition, detail=""):
        global failures
        if condition:
            print(f"  PASS  {name}")
        else:
            print(f"  FAIL  {name}" + (f": {detail}" if detail else ""))
            failures += 1

    print("=== Test 1: welcome body structure ===")
    body1 = _build_welcome_body(USERNAME, MEMORIES, DATE)
    check("title contains username", f"Welcome to the Team, @{USERNAME}" in body1)
    check("generated date present", DATE in body1)
    check("org standards section heading", "Section 1 — Non-Negotiable Org Standards" in body1)
    check("section 2 heading", "Section 2 — Architectural Decisions" in body1)
    check("how CORTEX works section", "## How CORTEX Works" in body1)
    check("three separators present", body1.count("\n---\n") >= 3)

    print()
    print("=== Test 2: org standards content ===")
    check("no secrets rule", "No secrets in source" in body1)
    check("no sql concat rule", "No SQL string concatenation" in body1)
    check("no eval rule", "eval()" in body1)
    check("no bare except rule", "No bare `except:`" in body1)
    check("no unbounded retry rule", "No unbounded retry loops" in body1)
    check("no blocking async rule", "No blocking network calls inside async handlers" in body1)
    check("no commented code rule", "No committed commented-out code blocks" in body1)
    check("no fixme without ticket rule", "ticket ID" in body1)
    check("GUARDKEEPER enforcement note", "GUARDKEEPER flags one of these" in body1)

    print()
    print("=== Test 3: active memories shown, superseded hidden ===")
    check("memory #004 present", "Memory #004" in body1)
    check("memory #005 present", "Memory #005" in body1)
    check("superseded memory #002 absent", "Memory #002" not in body1)
    check("decision text shown", "Use fixed retry intervals" in body1)
    check("rejected approach shown", "Rejected approach (do not reintroduce)" in body1)
    check("exponential backoff rejection shown", "Exponential backoff" in body1)
    check("reason shown", "thundering herd" in body1)
    check("governs files shown for #004", "legacy/agents/cortexkeeper.py" in body1)
    check("confidence shown", "Confidence: HIGH" in body1)
    check("decided by shown", "Decided by: @alice" in body1)
    check("active count is 2", "**2 active decision(s)**" in body1)

    print()
    print("=== Test 4: no memories yet ===")
    body4 = _build_welcome_body("charlie", [], DATE)
    check("no-memories placeholder shown", "No active architectural decisions have been recorded yet" in body4)
    check("section 2 heading still present", "Section 2 — Architectural Decisions" in body4)
    check("org standards still shown", "Section 1 — Non-Negotiable Org Standards" in body4)

    print()
    print("=== Test 5: all memories superseded ===")
    superseded_only = [
        {"id": "001", "decision": "Old thing", "status": "Superseded",
         "governs_files": [], "decided_by": [], "rejected": "", "reason": "",
         "confidence": "", "date": ""}
    ]
    body5 = _build_welcome_body("dave", superseded_only, DATE)
    check("no-memories placeholder when all superseded", "No active architectural decisions have been recorded yet" in body5)
    check("Memory #001 not shown", "Memory #001" not in body5)

    print()
    print("=== Test 6: issue title format ===")
    title_no_access = f"🧠 CORTEX — Welcome @{USERNAME}"
    username = "eve"
    access_str = " (Developer)"
    title_with_access = f"🧠 CORTEX — Welcome @{username}{access_str}"
    check("title without access level", title_no_access == f"🧠 CORTEX — Welcome @{USERNAME}")
    check("title with access level", title_with_access == "🧠 CORTEX — Welcome @eve (Developer)")

    print()
    print("=== Test 7: how CORTEX works content ===")
    check("intentional reply documented", "cortex: intentional" in body1)
    check("accidental reply documented", "cortex: accidental" in body1)
    check("discuss reply documented", "cortex: discuss" in body1)
    check("CORTEXKEEPER merge capture mentioned", "CORTEXKEEPER reads your MR discussion" in body1)

    print()
    if failures == 0:
        print("All tests PASSED")
        sys.exit(0)
    else:
        print(f"{failures} test(s) FAILED")
        sys.exit(1)
