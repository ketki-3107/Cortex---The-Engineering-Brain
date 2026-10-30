"""
Unit tests for GUARDKEEPER conflict comment rendering logic.
Covers: org standard violations, memory conflicts, mixed, severity emoji mapping.
"""
import sys


def _get_memory_by_id(memories, memory_id):
    target = str(memory_id).strip().zfill(3)
    for m in memories:
        if str(m.get("id", "")).strip().zfill(3) == target:
            return m
    return {}


def render_conflict_comment(conflicts, memories, checked_memories, changed_files):
    org_violations = [c for c in conflicts if c.get("memory_id") == "ORG-STANDARDS"]
    memory_conflicts = [c for c in conflicts if c.get("memory_id") != "ORG-STANDARDS"]
    summary_parts = []
    if org_violations:
        summary_parts.append(f"{len(org_violations)} org standard violation(s)")
    if memory_conflicts:
        summary_parts.append(f"{len(memory_conflicts)} architectural decision conflict(s)")

    parts = [
        "🧠 CORTEX — GUARDKEEPER — ⚠️ Decision Conflict Detected",
        "",
        f"This MR has {' and '.join(summary_parts)}.",
        "",
    ]

    for c in conflicts:
        mem_id = c.get("memory_id", "")
        severity = c.get("severity", "MEDIUM")
        category = c.get("category", "architecture")
        conflict_type = c.get("conflict_type", "direct-contradiction")
        conflict_desc = c.get("conflict_description", "")
        code_location = c.get("conflicting_code_location", "")
        reasoning = c.get("reasoning", "")

        severity_emoji = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🔵"}.get(severity, "🟡")
        conflict_type_label = {
            "rejected-approach-reintroduced": "Rejected approach reintroduced",
            "chosen-approach-abandoned": "Chosen approach abandoned",
            "org-standard-violation": "Org standard violation",
            "direct-contradiction": "Direct contradiction",
        }.get(conflict_type, conflict_type)

        is_org_standard = mem_id == "ORG-STANDARDS"
        mem = {} if is_org_standard else _get_memory_by_id(memories, mem_id)

        parts.append("---")
        if is_org_standard:
            parts.append(f"### {severity_emoji} Org Standard Violation — {severity} severity")
        else:
            parts.append(f"### {severity_emoji} Conflict with Memory #{mem_id} — {severity} severity")
        parts.append(f"**Category:** `{category}` | **Type:** {conflict_type_label}")
        parts.append("")
        parts.append(f"**What conflicts:** {conflict_desc}")
        parts.append(f"**Where:** {code_location}")
        parts.append("")
        parts.append("**CORTEX's reasoning:**")
        parts.append(reasoning)
        parts.append("")
        if not is_org_standard:
            parts.append("**The original decision:**")
            parts.append(f"> {mem.get('decision', '')}")
            parts.append("")
            parts.append("**Why it was decided:**")
            parts.append(f"> {mem.get('reason', '')}")
            parts.append("")
            decided_by_str = " ".join(mem.get("decided_by") or [])
            parts.append(f"**Original decision makers:** {decided_by_str}")
            parts.append(f"**Original MR:** !{mem.get('source_mr_number', '')}")
        parts.append("---")
        parts.append("")

    return "\n".join(parts)


# ── shared fixtures ───────────────────────────────────────────────────────────

MEMORIES = [
    {
        "id": "004",
        "decision": "Use fixed retry intervals",
        "reason": "Avoids thundering herd",
        "decided_by": ["@alice"],
        "source_mr_number": "6",
    }
]


# ── pytest test functions ─────────────────────────────────────────────────────

def test_org_standard_violation_only():
    c1 = [
        {
            "memory_id": "ORG-STANDARDS",
            "category": "org-standards",
            "conflict_type": "org-standard-violation",
            "conflict_description": "Hardcoded API key found in config.py",
            "conflicting_code_location": "config.py line 12",
            "reasoning": 'Line 12 sets API_KEY = "sk-abc123" directly in source.',
            "severity": "HIGH",
        }
    ]
    out = render_conflict_comment(c1, MEMORIES, ["ORG-STANDARDS"], ["config.py"])
    assert "1 org standard violation" in out
    assert "🔴" in out
    assert "The original decision" not in out
    assert "Org Standard Violation" in out


def test_memory_conflict_rejected_approach():
    c2 = [
        {
            "memory_id": "004",
            "category": "reliability",
            "conflict_type": "rejected-approach-reintroduced",
            "conflict_description": "Exponential backoff reintroduced in retry handler",
            "conflicting_code_location": "legacy/agents/cortexkeeper.py line 45",
            "reasoning": "New code uses delay * 2 ** attempt — exponential backoff, the rejected approach.",
            "severity": "MEDIUM",
        }
    ]
    out = render_conflict_comment(c2, MEMORIES, ["004"], ["legacy/agents/cortexkeeper.py"])
    assert "1 architectural decision conflict" in out
    assert "🟡" in out
    assert "Rejected approach reintroduced" in out
    assert "Use fixed retry intervals" in out
    assert "!6" in out
    assert "Memory #004" in out


def test_memory_conflict_chosen_approach_abandoned():
    c3 = [
        {
            "memory_id": "004",
            "category": "reliability",
            "conflict_type": "chosen-approach-abandoned",
            "conflict_description": "Fixed retry removed entirely",
            "conflicting_code_location": "legacy/agents/cortexkeeper.py line 45",
            "reasoning": "The retry loop was deleted without replacement.",
            "severity": "HIGH",
        }
    ]
    out = render_conflict_comment(c3, MEMORIES, ["004"], ["legacy/agents/cortexkeeper.py"])
    assert "Chosen approach abandoned" in out
    assert "🔴" in out


def test_mixed_org_and_memory_conflict():
    c4 = [
        {
            "memory_id": "ORG-STANDARDS",
            "category": "reliability",
            "conflict_type": "org-standard-violation",
            "conflict_description": "Bare except swallows errors",
            "conflicting_code_location": "legacy/agents/cortexkeeper.py line 80",
            "reasoning": "except: pass silently drops all exceptions.",
            "severity": "HIGH",
        },
        {
            "memory_id": "004",
            "category": "reliability",
            "conflict_type": "chosen-approach-abandoned",
            "conflict_description": "Fixed retry removed entirely",
            "conflicting_code_location": "legacy/agents/cortexkeeper.py line 45",
            "reasoning": "The retry loop was deleted without replacement.",
            "severity": "HIGH",
        },
    ]
    out = render_conflict_comment(c4, MEMORIES, ["ORG-STANDARDS", "004"], ["legacy/agents/cortexkeeper.py"])
    assert "1 org standard violation" in out
    assert "1 architectural decision conflict" in out
    assert " and " in out
    assert out.count("### 🔴") == 2
    assert out.index("Org Standard Violation") < out.index("The original decision")


def test_severity_emoji_mapping():
    for sev, emoji in [("HIGH", "🔴"), ("MEDIUM", "🟡"), ("LOW", "🔵")]:
        c = [
            {
                "memory_id": "ORG-STANDARDS",
                "category": "org-standards",
                "conflict_type": "org-standard-violation",
                "conflict_description": "x",
                "conflicting_code_location": "x",
                "reasoning": "x",
                "severity": sev,
            }
        ]
        out = render_conflict_comment(c, [], ["ORG-STANDARDS"], [])
        assert emoji in out, f"severity {sev} should map to {emoji}"


def test_zero_conflicts():
    out = render_conflict_comment([], MEMORIES, ["004"], ["legacy/agents/cortexkeeper.py"])
    assert "---" not in out
    assert "This MR has ." in out


# ── standalone execution (python tests/test_guardkeeper_rendering.py) ──────────

if __name__ == "__main__":
    failures = 0

    def check(name, condition, detail=""):
        global failures
        if condition:
            print(f"  PASS  {name}")
        else:
            print(f"  FAIL  {name}" + (f": {detail}" if detail else ""))
            failures += 1

    print("=== Test 1: org standard violation only ===")
    c1 = [
        {
            "memory_id": "ORG-STANDARDS",
            "category": "org-standards",
            "conflict_type": "org-standard-violation",
            "conflict_description": "Hardcoded API key found in config.py",
            "conflicting_code_location": "config.py line 12",
            "reasoning": 'Line 12 sets API_KEY = "sk-abc123" directly in source.',
            "severity": "HIGH",
        }
    ]
    out1 = render_conflict_comment(c1, MEMORIES, ["ORG-STANDARDS"], ["config.py"])
    check("summary mentions org standard", "1 org standard violation" in out1)
    check("severity emoji RED", "🔴" in out1)
    check("no memory fields leaked", "The original decision" not in out1)
    check("org standard header", "Org Standard Violation" in out1)

    print()
    print("=== Test 2: memory conflict — rejected approach reintroduced ===")
    c2 = [
        {
            "memory_id": "004",
            "category": "reliability",
            "conflict_type": "rejected-approach-reintroduced",
            "conflict_description": "Exponential backoff reintroduced in retry handler",
            "conflicting_code_location": "legacy/agents/cortexkeeper.py line 45",
            "reasoning": "New code uses delay * 2 ** attempt — exponential backoff, the rejected approach.",
            "severity": "MEDIUM",
        }
    ]
    out2 = render_conflict_comment(c2, MEMORIES, ["004"], ["legacy/agents/cortexkeeper.py"])
    check("summary mentions architectural conflict", "1 architectural decision conflict" in out2)
    check("severity emoji YELLOW", "🟡" in out2)
    check("conflict type label", "Rejected approach reintroduced" in out2)
    check("original decision shown", "Use fixed retry intervals" in out2)
    check("original MR shown", "!6" in out2)
    check("memory_id in header", "Memory #004" in out2)

    print()
    print("=== Test 3: memory conflict — chosen approach abandoned ===")
    c3 = [
        {
            "memory_id": "004",
            "category": "reliability",
            "conflict_type": "chosen-approach-abandoned",
            "conflict_description": "Fixed retry removed entirely",
            "conflicting_code_location": "legacy/agents/cortexkeeper.py line 45",
            "reasoning": "The retry loop was deleted without replacement.",
            "severity": "HIGH",
        }
    ]
    out3 = render_conflict_comment(c3, MEMORIES, ["004"], ["legacy/agents/cortexkeeper.py"])
    check("chosen-approach-abandoned label", "Chosen approach abandoned" in out3)
    check("severity emoji RED", "🔴" in out3)

    print()
    print("=== Test 4: mixed — org violation + memory conflict ===")
    c4 = [
        {
            "memory_id": "ORG-STANDARDS",
            "category": "reliability",
            "conflict_type": "org-standard-violation",
            "conflict_description": "Bare except swallows errors",
            "conflicting_code_location": "legacy/agents/cortexkeeper.py line 80",
            "reasoning": "except: pass silently drops all exceptions.",
            "severity": "HIGH",
        },
        {
            "memory_id": "004",
            "category": "reliability",
            "conflict_type": "chosen-approach-abandoned",
            "conflict_description": "Fixed retry removed entirely",
            "conflicting_code_location": "legacy/agents/cortexkeeper.py line 45",
            "reasoning": "The retry loop was deleted without replacement.",
            "severity": "HIGH",
        },
    ]
    out4 = render_conflict_comment(c4, MEMORIES, ["ORG-STANDARDS", "004"], ["legacy/agents/cortexkeeper.py"])
    check("summary has org part", "1 org standard violation" in out4)
    check("summary has memory part", "1 architectural decision conflict" in out4)
    check("summary uses 'and'", " and " in out4)
    check("two conflict blocks", out4.count("### 🔴") == 2)
    check("org block has no memory fields", out4.index("Org Standard Violation") < out4.index("The original decision"))

    print()
    print("=== Test 5: severity emoji mapping ===")
    for sev, emoji in [("HIGH", "🔴"), ("MEDIUM", "🟡"), ("LOW", "🔵")]:
        c = [
            {
                "memory_id": "ORG-STANDARDS",
                "category": "org-standards",
                "conflict_type": "org-standard-violation",
                "conflict_description": "x",
                "conflicting_code_location": "x",
                "reasoning": "x",
                "severity": sev,
            }
        ]
        out = render_conflict_comment(c, [], ["ORG-STANDARDS"], [])
        check(f"severity {sev} maps to correct emoji", emoji in out)

    print()
    print("=== Test 6: zero conflicts (clean MR) ===")
    out6 = render_conflict_comment([], MEMORIES, ["004"], ["legacy/agents/cortexkeeper.py"])
    check("no --- separator in clean output", "---" not in out6)
    check("summary is empty string join", "This MR has ." in out6)

    print()
    if failures == 0:
        print("All tests PASSED")
        sys.exit(0)
    else:
        print(f"{failures} test(s) FAILED")
        sys.exit(1)
